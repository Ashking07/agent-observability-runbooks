from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..settings import settings
from ..schemas import EventsIn
from .. import crud

router = APIRouter(prefix="/v1", tags=["events"])


def require_api_key(x_api_key: str | None):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/events")
def ingest_events(
    payload: EventsIn,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    require_api_key(x_api_key)

    ingested = 0
    failed = 0
    errors: list[dict] = []
    warnings: list[dict] = []

    for i, ev in enumerate(payload.events):
        try:
            if ev.type == "run.start":
                crud.upsert_run_start(db, ev.run_id, ev.project_id, ev.runbook, ev.ts)

            elif ev.type == "step.start":
                crud.upsert_step_start(
                    db,
                    ev.run_id,
                    ev.step_id,
                    ev.index,
                    ev.name,
                    ev.tool,
                    ev.input,
                    ev.ts,
                )

            elif ev.type == "step.end":
                _step, created_placeholder = crud.apply_step_end(
                    db,
                    ev.step_id,
                    ev.output,
                    ev.latency_ms,
                    ev.tokens,
                    float(ev.cost_usd),
                    ev.status,
                    ev.ts,
                )
                if created_placeholder:
                    warnings.append(
                        {
                            "index": i,
                            "type": "step.end",
                            "step_id": str(ev.step_id),
                            "warning": "step_end_before_step_start_placeholder_created",
                        }
                    )

            elif ev.type == "run.end":
                crud.apply_run_end(db, ev.run_id, ev.totals, ev.ts)

            db.commit()
            ingested += 1

        except Exception as e:
            db.rollback()
            failed += 1
            errors.append(
                {
                    "index": i,
                    "type": getattr(ev, "type", None),
                    "run_id": str(getattr(ev, "run_id", "")),
                    "step_id": str(getattr(ev, "step_id", "")) if hasattr(ev, "step_id") else None,
                    "error": str(e),
                }
            )

    return {
        "status": "ok" if failed == 0 else "partial",
        "ingested": ingested,
        "failed": failed,
        "errors": errors,
        "warnings": warnings,
    }
