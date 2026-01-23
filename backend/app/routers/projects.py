from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db import get_db
from ..settings import settings
from ..models import Run, RunValidation

router = APIRouter(prefix="/v1", tags=["projects"])

def require_api_key(x_api_key: str | None):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@router.get("/projects")
def list_projects(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    # distinct project_id list
    rows = db.execute(
        select(Run.project_id).distinct().order_by(Run.project_id.asc())
    ).all()

    return {"projects": [r[0] for r in rows]}


@router.get("/projects/{project_id}/summary")
def project_summary(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    # 1) Total runs + latest run timestamp (over ALL runs for this project)
    total_runs = db.scalar(
        select(func.count()).select_from(Run).where(Run.project_id == project_id)
    ) or 0

    last_run_at = db.scalar(
        select(func.max(Run.started_at)).where(Run.project_id == project_id)
    )

    # 2) Status counts over the most recent `limit` runs (so dashboard stays fast)
    recent_runs_sq = (
        select(Run.status)
        .where(Run.project_id == project_id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
        .subquery()
    )

    rows = db.execute(
        select(recent_runs_sq.c.status, func.count())
        .group_by(recent_runs_sq.c.status)
    ).all()

    status_counts = {str(status): int(count) for status, count in rows}

    # 3) Latest validation across runs in this project (pick newest run; within that run, newest validation)
    latest_val = db.execute(
        select(
            RunValidation.id,
            RunValidation.status,
            RunValidation.created_at,
            RunValidation.run_id,
        )
        .select_from(RunValidation)
        .join(Run, Run.id == RunValidation.run_id)
        .where(Run.project_id == project_id)
        .order_by(Run.started_at.desc(), RunValidation.created_at.desc())
        .limit(1)
    ).first()

    latest_validation_id = str(latest_val.id) if latest_val else None
    latest_validation_status = str(latest_val.status) if latest_val else None
    latest_validation_at = latest_val.created_at.isoformat().replace("+00:00", "Z") if latest_val else None
    latest_validation_run_id = str(latest_val.run_id) if latest_val else None

    return {
        "project_id": project_id,
        "total_runs": int(total_runs),
        "last_run_at": last_run_at.isoformat().replace("+00:00", "Z") if last_run_at else None,
        "status_counts": status_counts,  # counts over most recent `limit` runs
        "latest_validation_id": latest_validation_id,
        "latest_validation_status": latest_validation_status,
        "latest_validation_at": latest_validation_at,
        "latest_validation_run_id": latest_validation_run_id,
        "window_limit": limit,
    }
