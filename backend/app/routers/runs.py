from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, case
from sqlalchemy.orm import Session
from typing import Any, Optional
from pydantic import BaseModel
import yaml
from uuid import UUID
import hashlib
import json
from fastapi import Response

from ..db import get_db
from ..schemas import RunOut, RunDetailOut, StepOut, RunValidationOut, RunValidationListOut
from ..models import Run, Step, RunValidation
from ..settings import settings

router = APIRouter(prefix="/v1", tags=["runs"])


def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
class ValidateRunIn(BaseModel):
    # If omitted, we will use Run.runbook (if present)
    runbook_yaml: Optional[str] = None


class ValidationReason(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ValidateRunOut(BaseModel):
    status: str  # "passed" or "failed"
    reasons: list[ValidationReason]
    summary: dict[str, Any]



@router.get("/runs", response_model=list[RunOut])
def list_runs(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),  # add offset if you want (optional)
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    latest_val = (
        select(
            RunValidation.run_id.label("run_id"),
            RunValidation.id.label("latest_validation_id"),
            RunValidation.status.label("latest_validation_status"),
            RunValidation.created_at.label("latest_validation_at"),
        )
        .distinct(RunValidation.run_id)
        .order_by(RunValidation.run_id, RunValidation.created_at.desc())
    ).subquery()


    q = (
        select(
            Run,
            latest_val.c.latest_validation_id,
            latest_val.c.latest_validation_status,
            latest_val.c.latest_validation_at,
        )
        .outerjoin(latest_val, latest_val.c.run_id == Run.id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
        .offset(offset)
    )

    if project_id:
        q = q.where(Run.project_id == project_id)

    rows = db.execute(q).all()

    out: list[RunOut] = []
    for r, vid, vstatus, vat in rows:
        out.append(
            RunOut(
                id=r.id,
                project_id=r.project_id,
                runbook=r.runbook,
                status=r.status,
                started_at=r.started_at,
                ended_at=r.ended_at,
                total_tokens=r.total_tokens,
                total_cost_usd=float(r.total_cost_usd or 0),
                latest_validation_id=vid,
                latest_validation_status=vstatus,
                latest_validation_at=vat,
            )
        )
    return out


@router.get("/runs/{run_id}", response_model=RunDetailOut, dependencies=[Depends(require_api_key)])
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    # Placeholders (index < 0) go last; real steps (index >= 0) ordered ascending.
    placeholder_last = case((Step.index < 0, 1), else_=0)

    steps = db.scalars(
        select(Step)
        .where(Step.run_id == run_id)
        .order_by(placeholder_last.asc(), Step.index.asc(), Step.started_at.asc(), Step.id.asc())
    ).all()

    latest_val = db.scalars(
    select(RunValidation)
    .where(RunValidation.run_id == run_id)
    .order_by(RunValidation.created_at.desc())
    .limit(1)
    ).first()


    return RunDetailOut(
        id=r.id,
        project_id=r.project_id,
        runbook=r.runbook,
        status=r.status,
        started_at=r.started_at,
        ended_at=r.ended_at,
        total_tokens=r.total_tokens,
        total_cost_usd=float(r.total_cost_usd or 0),
        latest_validation_id=str(latest_val.id) if latest_val else None,
        latest_validation_status=latest_val.status if latest_val else None,
        latest_validation_at=latest_val.created_at if latest_val else None,
        steps=[
            StepOut(
                id=s.id,
                index=s.index,
                name=s.name,
                tool=s.tool,
                status=s.status,
                latency_ms=s.latency_ms,
                tokens=s.tokens,
                cost_usd=float(s.cost_usd or 0),
                input_json=s.input_json or {},
                output_json=s.output_json or {},
                started_at=s.started_at,
                ended_at=s.ended_at,
            )
            for s in steps
        ],
    )

@router.get("/runs/{run_id}/validations", response_model=RunValidationListOut)
def list_run_validations(
    run_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    # Confirm the run exists (better error)
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    vals = db.scalars(
        select(RunValidation)
        .where(RunValidation.run_id == run_id)
        .order_by(RunValidation.created_at.desc())
        .limit(limit)
    ).all()

    return RunValidationListOut(
        validations=[
            RunValidationOut(
                id=v.id,
                run_id=v.run_id,
                status=v.status,
                created_at=v.created_at,
                reasons_json=v.reasons_json or [],
                summary_json=v.summary_json or {},
            )
            for v in vals
        ]
    )


@router.post(
    "/runs/{run_id}/validate",
    response_model=ValidateRunOut,
    dependencies=[Depends(require_api_key)],
)
def validate_run(
    run_id: UUID,
    payload: ValidateRunIn,
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # 1) Load steps first (deterministic order)
    placeholder_last = case((Step.index < 0, 1), else_=0)
    steps = db.scalars(
        select(Step)
        .where(Step.run_id == run_id)
        .order_by(
            placeholder_last.asc(),
            Step.index.asc(),
            Step.started_at.asc(),
            Step.id.asc(),
        )
    ).all()

    # 2) Compute totals (prefer Run totals; else compute from steps)
    total_tokens = int(run.total_tokens or 0)
    total_cost = float(run.total_cost_usd or 0.0)
    if total_tokens == 0 and total_cost == 0.0:
        total_tokens = sum(int(s.tokens or 0) for s in steps)
        total_cost = sum(float(s.cost_usd or 0.0) for s in steps)

    # 3) Load runbook text (request body > stored run.runbook)
    runbook_text = (payload.runbook_yaml or (run.runbook or "")).strip()
    if not runbook_text:
        return ValidateRunOut(
            status="failed",
            reasons=[
                ValidationReason(
                    code="runbook_missing",
                    message="No runbook provided. Supply runbook_yaml or store one on run.start.",
                )
            ],
            summary={"run_id": str(run_id)},
        )

    # 4) Parse YAML
    try:
        runbook = yaml.safe_load(runbook_text) or {}
        if not isinstance(runbook, dict):
            raise ValueError("Runbook must be a YAML mapping/object at the top level.")
    except Exception as e:
        return ValidateRunOut(
            status="failed",
            reasons=[
                ValidationReason(
                    code="runbook_parse_error",
                    message="Failed to parse runbook YAML.",
                    details={"error": str(e)},
                )
            ],
            summary={"run_id": str(run_id)},
        )

    # 5) Build deterministic signature + input_hash (NOW all vars exist)
    signature = {
        "run_id": str(run_id),
        "runbook_yaml": runbook_text,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "steps": [
            {
                "id": str(s.id),
                "index": s.index,
                "name": s.name,
                "tool": s.tool,
                "status": s.status,
                "tokens": int(s.tokens or 0),
                "cost_usd": float(s.cost_usd or 0.0),
                "ended_at": (s.ended_at.isoformat() if s.ended_at else None),
            }
            for s in steps
        ],
    }
    input_hash = hashlib.sha256(
        json.dumps(signature, sort_keys=True).encode("utf-8")
    ).hexdigest()

    # 6) Idempotency: return existing validation if same input_hash
    existing = db.scalars(
        select(RunValidation)
        .where(
            RunValidation.run_id == run_id,
            RunValidation.input_hash == input_hash,
        )
        .limit(1)
    ).first()

    if existing:
        summary = (existing.summary_json or {"run_id": str(run_id)})
        summary["validation_id"] = str(existing.id)

        if run.status != "error":
            run.status = existing.status
            db.commit()

        return ValidateRunOut(
            status=existing.status,
            reasons=[ValidationReason(**x) for x in (existing.reasons_json or [])],
            summary=summary,
        )

    # 7) Evaluate rules
    reasons: list[ValidationReason] = []

    # Rule 1: allowed_tools
    allowed_tools = runbook.get("allowed_tools")
    if isinstance(allowed_tools, list):
        allowed_set = set(str(x) for x in allowed_tools)
        for s in steps:
            if s.tool and s.tool != "unknown" and s.tool not in allowed_set:
                reasons.append(
                    ValidationReason(
                        code="tool_not_allowed",
                        message=f"Step tool '{s.tool}' is not allowed.",
                        details={"step_id": str(s.id), "tool": s.tool, "index": s.index},
                    )
                )

    # Rule 2: required_steps subsequence by name
    required_steps = runbook.get("required_steps")
    if isinstance(required_steps, list):
        required_names = [
            str(x.get("name"))
            for x in required_steps
            if isinstance(x, dict) and x.get("name")
        ]
        observed_names = [s.name for s in steps if s.name]

        j = 0
        for name in observed_names:
            if j < len(required_names) and name == required_names[j]:
                j += 1
        if j < len(required_names):
            reasons.append(
                ValidationReason(
                    code="required_steps_missing_or_out_of_order",
                    message="Required steps missing or out of order.",
                    details={
                        "required_sequence": required_names,
                        "missing_suffix": required_names[j:],
                        "observed": observed_names,
                    },
                )
            )

    # Rule 3: budgets
    budgets = runbook.get("budgets") if isinstance(runbook.get("budgets"), dict) else {}
    max_tokens = budgets.get("max_total_tokens")
    max_cost = budgets.get("max_total_cost_usd")

    if max_tokens is not None:
        try:
            if total_tokens > int(max_tokens):
                reasons.append(
                    ValidationReason(
                        code="budget_tokens_exceeded",
                        message="Token budget exceeded.",
                        details={"total_tokens": total_tokens, "max_total_tokens": int(max_tokens)},
                    )
                )
        except Exception:
            reasons.append(
                ValidationReason(
                    code="runbook_invalid_budget_tokens",
                    message="Invalid max_total_tokens in runbook.",
                    details={"value": max_tokens},
                )
            )

    if max_cost is not None:
        try:
            if total_cost > float(max_cost):
                reasons.append(
                    ValidationReason(
                        code="budget_cost_exceeded",
                        message="Cost budget exceeded.",
                        details={"total_cost_usd": total_cost, "max_total_cost_usd": float(max_cost)},
                    )
                )
        except Exception:
            reasons.append(
                ValidationReason(
                    code="runbook_invalid_budget_cost",
                    message="Invalid max_total_cost_usd in runbook.",
                    details={"value": max_cost},
                )
            )

    status = "passed" if len(reasons) == 0 else "failed"

    # 8) Persist
    reasons_payload = [reason.model_dump() for reason in reasons]
    summary_payload = {
        "run_id": str(run_id),
        "project_id": run.project_id,
        "steps_count": len(steps),
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
    }

    # Reflect validation result onto the Run itself (simple MVP behavior).
    # Keep "error" as highest priority (don't overwrite it).
    if run.status != "error":
        run.status = "passed" if status == "passed" else "failed"

    # Persist validation row (idempotent)
    val = RunValidation(
        run_id=run_id,
        status=status,
        input_hash=input_hash,
        reasons_json=reasons_payload,
        summary_json=summary_payload,
        runbook_yaml=runbook_text,
    )
    db.add(val)

    try:
        db.commit()
        db.refresh(val)
    except IntegrityError:
        db.rollback()
        val = db.scalars(
            select(RunValidation).where(
                RunValidation.run_id == run_id,
                RunValidation.input_hash == input_hash,
            )
        ).first()
        if not val:
            raise

    # Reflect onto Run (single commit)
    if run.status != "error":
        run.status = "passed" if val.status == "passed" else "failed"
        db.commit()

    summary_payload["validation_id"] = str(val.id)
    return ValidateRunOut(status=val.status, reasons=reasons, summary=summary_payload)



@router.delete(
    "/runs/{run_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    db.delete(run)
    db.commit()

    # 204 No Content
    return Response(status_code=204)