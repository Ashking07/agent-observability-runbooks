from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, case
from sqlalchemy.orm import Session
from uuid import UUID

from ..db import get_db
from ..settings import settings
from ..models import Run, Step
from ..schemas import RunOut, RunDetailOut, StepOut

router = APIRouter(prefix="/v1", tags=["runs"])


def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


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
