from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict

from .utils import now_iso_z, coerce_dict


EventType = Literal["run.start", "run.end", "step.start", "step.end"]


class Event(TypedDict, total=False):
    type: EventType
    ts: str

    # run fields
    run_id: str
    project_id: str
    runbook: str
    totals: Dict[str, Any]

    # step fields
    step_id: str
    index: int
    name: str
    tool: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    latency_ms: int
    tokens: int
    cost_usd: float
    status: str


def run_start(*, run_id: str, project_id: str, runbook: str, ts: Optional[str] = None) -> Event:
    return {
        "type": "run.start",
        "run_id": run_id,
        "project_id": project_id,
        "runbook": runbook,
        "ts": ts or now_iso_z(),
    }


def run_end(*, run_id: str, totals: Optional[Dict[str, Any]] = None, ts: Optional[str] = None) -> Event:
    e: Event = {
        "type": "run.end",
        "run_id": run_id,
        "ts": ts or now_iso_z(),
    }
    if totals is not None:
        e["totals"] = totals
    return e


def step_start(
    *,
    run_id: str,
    step_id: str,
    index: int,
    name: str,
    tool: str,
    input: Optional[Dict[str, Any]] = None,
    ts: Optional[str] = None,
) -> Event:
    return {
        "type": "step.start",
        "run_id": run_id,
        "step_id": step_id,
        "index": index,
        "name": name,
        "tool": tool,
        "input": coerce_dict(input),
        "ts": ts or now_iso_z(),
    }


def step_end(
    *,
    run_id: str,
    step_id: str,
    output: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[int] = None,
    tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    status: str = "ok",
    ts: Optional[str] = None,
) -> Event:
    e: Event = {
        "type": "step.end",
        "run_id": run_id,
        "step_id": step_id,
        "output": coerce_dict(output),
        "status": status,
        "ts": ts or now_iso_z(),
    }
    if latency_ms is not None:
        e["latency_ms"] = int(latency_ms)
    if tokens is not None:
        e["tokens"] = int(tokens)
    if cost_usd is not None:
        e["cost_usd"] = float(cost_usd)
    return e
