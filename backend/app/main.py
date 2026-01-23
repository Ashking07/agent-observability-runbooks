from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .settings import settings
from .db import SessionLocal
from .routers.events import router as events_router
from .routers.runs import router as runs_router
from .routers.projects import router as projects_router


app = FastAPI(title="Agent Observability API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router)
app.include_router(runs_router)
app.include_router(projects_router)

@app.get("/health")
def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except SQLAlchemyError as e:
        # Keep it beginner-friendly: return a clear status without a stack trace.
        return {"status": "degraded", "db": "down", "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass
