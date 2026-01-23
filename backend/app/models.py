import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    DateTime,
    Integer,
    Numeric,
    ForeignKey,
    JSON,
    Enum,
    CheckConstraint,
    Index,
    Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

RunStatus = Enum("running", "passed", "failed", "error", name="run_status")
StepStatus = Enum("ok", "error", name="step_status")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(String, index=True)
    runbook: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(RunStatus, default="running", index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    steps: Mapped[list["Step"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    validations: Mapped[list["RunValidation"]] = relationship(
    back_populates="run",
    cascade="all, delete-orphan",
    passive_deletes=True,
    )


    __table_args__ = (
        CheckConstraint("total_tokens >= 0", name="ck_runs_total_tokens_nonneg"),
        CheckConstraint("total_cost_usd >= 0", name="ck_runs_total_cost_nonneg"),
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # IMPORTANT: align typing with nullable=True
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    index: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    tool: Mapped[str] = mapped_column(String, index=True)

    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(StepStatus, default="ok")

    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["Run"] = relationship(back_populates="steps")

    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="ck_steps_latency_nonneg"),
        CheckConstraint("tokens >= 0", name="ck_steps_tokens_nonneg"),
        CheckConstraint("cost_usd >= 0", name="ck_steps_cost_nonneg"),

        # Unique (run_id, index) ONLY when run_id is not null.
        # This allows placeholders created by step.end-first (run_id NULL).
        Index(
            "uq_steps_run_id_index_notnull",
            "run_id",
            "index",
            unique=True,
            postgresql_where=(run_id.isnot(None)),
        ),
    )


class RunValidation(Base):
    __tablename__ = "run_validations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    run: Mapped["Run"] = relationship(back_populates="validations")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    # Keep status as string for MVP to avoid Postgres ENUM migration complexity
    status: Mapped[str] = mapped_column(String, index=True)  # "passed" | "failed"

    # Store the computed output so dashboard/history can show reasons
    reasons_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Store the runbook text used for this validation (useful for audit / debugging)
    runbook_yaml: Mapped[str] = mapped_column(Text, default="") # Store as text for simplicity: modified by own.
