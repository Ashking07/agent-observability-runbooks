from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .types import run_end, run_start, step_end, step_start
from .utils import safe_str, coerce_dict

logger = logging.getLogger("obs_sdk")


@dataclass
class RunContext:
    client: Any  # ObsClient, but avoid circular import typing
    runbook: str
    project_id: str
    run_id: str = ""
    _step_index: int = 0
    _totals: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = str(uuid.uuid4())

    def __enter__(self) -> "RunContext":
        self.client.enqueue(
            run_start(run_id=self.run_id, project_id=self.project_id, runbook=self.runbook)
        )
        # flush early so run appears quickly
        self.client.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Always emit run.end; host app exceptions should not be swallowed by default.
        self.client.enqueue(run_end(run_id=self.run_id, totals=self._totals))
        self.client.flush()
        return False  # do not suppress exceptions

    def step(
        self,
        *,
        name: str,
        tool: str,
        input: Optional[Dict[str, Any]] = None,
    ) -> "StepContext":
        idx = self._step_index
        self._step_index += 1
        return StepContext(
            run=self,
            index=idx,
            name=name,
            tool=tool,
            input=coerce_dict(input),
        )

    def set_totals(self, *, tokens: Optional[int] = None, cost_usd: Optional[float] = None, **extra: Any) -> None:
        totals: Dict[str, Any] = {}
        if tokens is not None:
            totals["tokens"] = int(tokens)
        if cost_usd is not None:
            totals["cost_usd"] = float(cost_usd)
        for k, v in extra.items():
            totals[k] = v
        self._totals = totals


@dataclass
class StepContext:
    run: RunContext
    index: int
    name: str
    tool: str
    input: Dict[str, Any]
    step_id: str = ""
    _t0: float = 0.0
    _output: Dict[str, Any] = None
    _tokens: Optional[int] = None
    _cost_usd: Optional[float] = None
    _status: str = "ok"

    def __post_init__(self) -> None:
        if not self.step_id:
            self.step_id = str(uuid.uuid4())
        if self._output is None:
            self._output = {}

    def __enter__(self) -> "StepContext":
        self._t0 = time.perf_counter()
        self.run.client.enqueue(
            step_start(
                run_id=self.run.run_id,
                step_id=self.step_id,
                index=self.index,
                name=self.name,
                tool=self.tool,
                input=self.input,
            )
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        latency_ms = int(max(0.0, (time.perf_counter() - self._t0) * 1000.0))

        output = dict(self._output or {})
        status = self._status

        if exc is not None:
            status = "error"
            # Keep error payload compact and safe.
            output.setdefault("error", safe_str(exc))

        self.run.client.enqueue(
            step_end(
                run_id=self.run.run_id,
                step_id=self.step_id,
                output=output,
                latency_ms=latency_ms,
                tokens=self._tokens,
                cost_usd=self._cost_usd,
                status=status,
            )
        )

        # Do not swallow app exceptions
        return False

    def set_output(self, output: Dict[str, Any]) -> None:
        self._output = coerce_dict(output)

    def set_tokens_cost(self, *, tokens: Optional[int] = None, cost_usd: Optional[float] = None) -> None:
        if tokens is not None:
            self._tokens = int(tokens)
        if cost_usd is not None:
            self._cost_usd = float(cost_usd)

    def set_status(self, status: str) -> None:
        # "ok" or "error" are typical; backend stores as string.
        self._status = str(status)
