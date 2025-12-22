from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .routers.events import router as events_router
from .routers.runs import router as runs_router

app = FastAPI(title="Agent Observability API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router)
app.include_router(runs_router)

@app.get("/health")
def health():
    return {"status": "ok"}
