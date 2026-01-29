from __future__ import annotations

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Annotated, Literal, Optional, Union



# ----- Event input models -----

EventType = Literal["run.start", "run.end", "step.start", "step.end"]


class BaseEvent(BaseModel):
    type: EventType
    run_id: UUID
    ts: datetime


class RunStartEvent(BaseEvent):
    type: Literal["run.start"]
    project_id: str
    runbook: Optional[str] = None


class RunEndEvent(BaseEvent):
    type: Literal["run.end"]
    totals: dict = Field(default_factory=dict)  # e.g. {"tokens": 123, "cost_usd": 0.01}


class StepStartEvent(BaseEvent):
    type: Literal["step.start"]
    step_id: UUID
    index: int
    name: str
    tool: str
    input: dict = Field(default_factory=dict)


class StepEndEvent(BaseEvent):
    type: Literal["step.end"]
    step_id: UUID
    output: dict = Field(default_factory=dict)
    latency_ms: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    cost_usd: float = 0.0
    status: Literal["ok", "error"] = "ok"


Event = Annotated[
    Union[RunStartEvent, RunEndEvent, StepStartEvent, StepEndEvent],
    Field(discriminator="type"),
]


class EventsIn(BaseModel):
    events: list[Event]


# ----- Output models -----

class RunOut(BaseModel):
    id: UUID
    project_id: str
    runbook: Optional[str]
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    total_tokens: int
    total_cost_usd: float

    # NEW (latest validation info)
    latest_validation_id: Optional[UUID] = None
    latest_validation_status: Optional[str] = None
    latest_validation_at: Optional[datetime] = None


class StepOut(BaseModel):
    id: UUID
    index: int
    name: str
    tool: str
    status: str
    latency_ms: int
    tokens: int
    cost_usd: float
    input_json: dict
    output_json: dict
    started_at: datetime
    ended_at: Optional[datetime]


class RunDetailOut(RunOut):
    steps: list[StepOut]

class RunValidationOut(BaseModel):
    id: UUID
    run_id: UUID
    status: str  # "passed" | "failed"
    created_at: datetime
    reasons_json: list[dict]
    summary_json: dict

class RunValidationListOut(BaseModel):
    validations: list[RunValidationOut]


class PolicyCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    runbook_yaml: str

class PolicyUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    runbook_yaml: Optional[str] = None
    is_active: Optional[bool] = None

class PolicyOut(BaseModel):
    id: UUID
    project_id: str
    name: str
    description: Optional[str] = None
    runbook_yaml: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # pydantic v2; for v1 use orm_mode=True