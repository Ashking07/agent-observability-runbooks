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

    for ev in payload.events:
        if ev.type == "run.start":
            crud.upsert_run_start(db, ev.run_id, ev.project_id, ev.runbook, ev.ts)
        elif ev.type == "step.start":
            crud.upsert_step_start(db, ev.run_id, ev.step_id, ev.index, ev.name, ev.tool, ev.input, ev.ts)
        elif ev.type == "step.end":
            crud.apply_step_end(db, ev.step_id, ev.output, ev.latency_ms, ev.tokens, float(ev.cost_usd), ev.status, ev.ts)
        elif ev.type == "run.end":
            crud.apply_run_end(db, ev.run_id, ev.totals, ev.ts)

    db.commit()
    return {"status": "ok", "ingested": len(payload.events)}
