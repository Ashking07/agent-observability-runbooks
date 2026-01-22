from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, case
from sqlalchemy.orm import Session
import json
from typing import Any, Optional
from pydantic import BaseModel
import yaml
from uuid import UUID

from ..db import get_db
from ..settings import settings
from ..models import Run, Step
from ..schemas import RunOut, RunDetailOut, StepOut

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



@router.get("/runs", response_model=list[RunOut], dependencies=[Depends(require_api_key)])
def list_runs(
    project_id: str = Query(..., description="Project identifier (required)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        select(Run)
        .where(Run.project_id == project_id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
        .offset(offset)
    )

    runs = db.scalars(q).all()

    return [
        RunOut(
            id=r.id,
            project_id=r.project_id,
            runbook=r.runbook,
            status=r.status,
            started_at=r.started_at,
            ended_at=r.ended_at,
            total_tokens=r.total_tokens,
            total_cost_usd=float(r.total_cost_usd or 0),
        )
        for r in runs
    ]


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

    return RunDetailOut(
        id=r.id,
        project_id=r.project_id,
        runbook=r.runbook,
        status=r.status,
        started_at=r.started_at,
        ended_at=r.ended_at,
        total_tokens=r.total_tokens,
        total_cost_usd=float(r.total_cost_usd or 0),
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
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get steps in deterministic order (same ordering logic as get_run)
    placeholder_last = case((Step.index < 0, 1), else_=0)
    steps = db.scalars(
        select(Step)
        .where(Step.run_id == run_id)
        .order_by(placeholder_last.asc(), Step.index.asc(), Step.started_at.asc(), Step.id.asc())
    ).all()

    # Load runbook YAML: prefer request body, else stored run.runbook
    runbook_text = (payload.runbook_yaml or (r.runbook or "")).strip()
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

    reasons: list[ValidationReason] = []

    # ---- Rule 1: allowed_tools ----
    allowed_tools = runbook.get("allowed_tools")
    if isinstance(allowed_tools, list):
        allowed_set = set(str(x) for x in allowed_tools)
        for s in steps:
            # ignore placeholders with unknown tool
            if s.tool and s.tool != "unknown" and s.tool not in allowed_set:
                reasons.append(
                    ValidationReason(
                        code="tool_not_allowed",
                        message=f"Step tool '{s.tool}' is not allowed.",
                        details={"step_id": str(s.id), "tool": s.tool, "index": s.index},
                    )
                )

    # ---- Rule 2: required_steps (subsequence by name) ----
    required_steps = runbook.get("required_steps")
    if isinstance(required_steps, list):
        required_names = [str(x.get("name")) for x in required_steps if isinstance(x, dict) and x.get("name")]
        observed_names = [s.name for s in steps if s.name]

        # Check subsequence order
        j = 0
        for name in observed_names:
            if j < len(required_names) and name == required_names[j]:
                j += 1
        if j < len(required_names):
            missing = required_names[j:]
            reasons.append(
                ValidationReason(
                    code="required_steps_missing_or_out_of_order",
                    message="Required steps missing or out of order.",
                    details={"required_sequence": required_names, "missing_suffix": missing, "observed": observed_names},
                )
            )

    # ---- Rule 3: budgets ----
    budgets = runbook.get("budgets") if isinstance(runbook.get("budgets"), dict) else {}
    max_tokens = budgets.get("max_total_tokens")
    max_cost = budgets.get("max_total_cost_usd")

    # Prefer Run totals if set; otherwise compute from steps
    total_tokens = int(r.total_tokens or 0)
    total_cost = float(r.total_cost_usd or 0.0)
    if total_tokens == 0 and total_cost == 0.0:
        total_tokens = sum(int(s.tokens or 0) for s in steps)
        total_cost = sum(float(s.cost_usd or 0.0) for s in steps)

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
    return ValidateRunOut(
        status=status,
        reasons=reasons,
        summary={
            "run_id": str(run_id),
            "project_id": r.project_id,
            "steps_count": len(steps),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
        },
    )
