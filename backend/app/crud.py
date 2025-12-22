from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Run, Step


def get_run(db: Session, run_id: UUID) -> Run | None:
    return db.scalar(select(Run).where(Run.id == run_id))


def upsert_run_start(
    db: Session,
    run_id: UUID,
    project_id: str,
    runbook: str | None,
    ts: datetime,
) -> Run:
    run = get_run(db, run_id)
    if run is None:
        run = Run(
            id=run_id,
            project_id=project_id,
            runbook=runbook,
            status="running",
            started_at=ts,
        )
        db.add(run)
    else:
        run.project_id = project_id
        run.runbook = runbook
        if not run.started_at:
            run.started_at = ts
        if run.status == "error":
            run.status = "running"
    return run


def apply_run_end(
    db: Session,
    run_id: UUID,
    totals: dict,
    ts: datetime,
) -> Run:
    run = get_run(db, run_id)
    if run is None:
        # tolerate out-of-order run.end
        run = Run(
            id=run_id,
            project_id="unknown",
            status="running",
            started_at=ts,
        )
        db.add(run)

    run.ended_at = ts

    if "tokens" in totals:
        run.total_tokens = int(totals.get("tokens") or 0)
    if "cost_usd" in totals:
        run.total_cost_usd = float(totals.get("cost_usd") or 0.0)

    # Phase 2: no runbook validation yet, mark completed
    if run.status == "running":
        run.status = "passed"

    return run


def upsert_step_start(
    db: Session,
    run_id: UUID,
    step_id: UUID,
    index: int,
    name: str,
    tool: str,
    input_obj: dict,
    ts: datetime,
) -> Step:
    step = db.scalar(select(Step).where(Step.id == step_id))
    if step is None:
        step = Step(
            id=step_id,
            run_id=run_id,
            index=index,
            name=name,
            tool=tool,
            input_json=input_obj or {},
            status="ok",
            started_at=ts,
        )
        db.add(step)
    else:
        step.run_id = run_id
        step.index = index
        step.name = name
        step.tool = tool
        step.input_json = input_obj or {}
        step.started_at = ts
    return step


def apply_step_end(
    db: Session,
    step_id: UUID,
    output_obj: dict,
    latency_ms: int,
    tokens: int,
    cost_usd: float,
    status: str,
    ts: datetime,
) -> Step:
    step = db.scalar(select(Step).where(Step.id == step_id))
    if step is None:
        # For MVP: require step.start first to know run_id/index/name/tool.
        raise ValueError(f"step.end received for unknown step_id={step_id}. Send step.start first.")

    step.output_json = output_obj or {}
    step.latency_ms = int(latency_ms or 0)
    step.tokens = int(tokens or 0)
    step.cost_usd = float(cost_usd or 0.0)
    step.status = status
    step.ended_at = ts

    return step
