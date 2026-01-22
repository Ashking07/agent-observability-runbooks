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
        return step

    # If this step was a placeholder created by step.end-first, fill in missing fields.
    # If the step already has real values, we still allow updates (idempotent retries),
    # but we avoid overwriting timestamps that already exist.
    step.run_id = run_id
    step.index = index
    step.name = name
    step.tool = tool

    # Only set input_json if it's empty / placeholder-like.
    if not step.input_json:
        step.input_json = input_obj or {}

    # "No time travel": don't overwrite started_at once it is set.
    if step.started_at is None:
        step.started_at = ts

    return step


def apply_step_end(
    db: Session,
    run_id: UUID,
    step_id: UUID,
    output_obj: dict,
    latency_ms: int,
    tokens: int,
    cost_usd: float,
    status: str,
    ts: datetime,
) -> tuple[Step, bool]:
    """
    Returns: (step, created_placeholder)
    created_placeholder=True means we received step.end before step.start.
    """
    step = db.scalar(select(Step).where(Step.id == step_id))
    created_placeholder = False

    if step is None:
        created_placeholder = True
        step = Step(
            id=step_id,
            run_id=run_id,      # <-- key change: attach to the run immediately
            index=-1,
            name="unknown",
            tool="unknown",
            input_json={},
            status=status,
            started_at=ts,
        )
        db.add(step)
    else:
        # If this step was previously created as a placeholder with run_id NULL,
        # we can attach it now. If it already has a run_id, we do NOT overwrite it.
        if step.run_id is None:
            step.run_id = run_id
        elif step.run_id != run_id:
            # Defensive: same step_id should not belong to a different run.
            raise ValueError(
                f"step_id={step_id} is already associated with run_id={step.run_id}, "
                f"cannot apply step.end for run_id={run_id}"
            )

    # If retries happen, do not erase prior data with empty dicts.
    if output_obj:
        step.output_json = output_obj

    # "No time travel": don't overwrite ended_at once set.
    if step.ended_at is None:
        step.ended_at = ts

    step.latency_ms = int(latency_ms or 0)
    step.tokens = int(tokens or 0)
    step.cost_usd = float(cost_usd or 0.0)
    step.status = status

    return step, created_placeholder
