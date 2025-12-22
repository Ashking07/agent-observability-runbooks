from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID

from ..db import get_db
from ..settings import settings
from ..models import Run, Step
from ..schemas import RunOut, RunDetailOut, StepOut

router = APIRouter(prefix="/v1", tags=["runs"])

def require_api_key(x_api_key: str | None):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@router.get("/runs", response_model=list[RunOut])
def list_runs(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    q = select(Run).order_by(Run.started_at.desc()).limit(limit)
    if project_id:
        q = q.where(Run.project_id == project_id)

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

@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = db.scalars(
        select(Step).where(Step.run_id == run_id).order_by(Step.index.asc())
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
