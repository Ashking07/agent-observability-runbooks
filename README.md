# Agent Observability + Runbook Validation (MVP)

**Store agent traces as structured runs/steps, then validate them against a YAML “runbook” spec.**  
This gives you *observability + testability* for AI agents: you can ingest events in real time, view runs, and deterministically validate whether a run followed the expected workflow, tool policy, and budgets.

## What this does

- **Ingest** agent execution events (`run.start`, `step.start`, `step.end`, `run.end`)
- **Persist** runs/steps to Postgres
- **Handle out-of-order events** (e.g. `step.end` before `step.start`) with warnings instead of hidden 500s
- **Read APIs** to list runs, view a run + steps, list projects, and show project summary
- **Validate** a run against a YAML runbook spec and **persist validations** to DB
- **Idempotent validations** via `input_hash` (same runbook + same run state returns existing validation)

---

## Why it matters

Teams building AI agents need two things:
1) **Replayable traces** with consistent structure (runs/steps/tools/inputs/outputs)  
2) **Runbook-based assertions** (“this tool is allowed”, “these steps must occur”, “don’t exceed budgets”)  

This project provides both, forming the foundation for dashboards, alerts, regressions, and CI “agent tests”.

---

## Quickstart

### Requirements
- Docker + Docker Compose

### Run locally
```bash
cd backend
docker compose up -d --build

Health check
curl http://localhost:8000/health
# {"status":"ok","db":"ok"}

Auth
All endpoints require an API key header:
-H "x-api-key: dev-key"
You can change it in backend/app/settings.py (or via env vars if you wire them).


Core Concepts
Event model

Run: one execution of an agent workflow

Step: a single tool call / action inside a run


Event types:

run.start (create/update run)

step.start (create/update step)

step.end (complete step metrics/output)

run.end (complete run totals)


Runbook validation

A runbook is YAML that defines:

allowed_tools: tool allow-list

required_steps: ordered subsequence by step name

budgets: max tokens / max cost


API Overview
Ingest events

POST /v1/events

Returns:

ingested: number successfully applied

failed: number failed

errors: list of {index, reason}

warnings: list of out-of-order tolerances, placeholders, etc.

Example:

curl -X POST "http://localhost:8000/v1/events" \
  -H "Content-Type: application/json" \
  -H "x-api-key: dev-key" \
  -d '{
    "events": [
      {
        "type": "run.start",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "project_id": "demo",
        "runbook": "example_runbook",
        "ts": "2026-01-21T00:00:00Z"
      },
      {
        "type": "step.start",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "step_id": "22222222-2222-2222-2222-222222222222",
        "index": 0,
        "name": "shorten",
        "tool": "httpx.post",
        "input": {"originalUrl": "https://example.com"},
        "ts": "2026-01-21T00:00:01Z"
      },
      {
        "type": "step.end",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "step_id": "22222222-2222-2222-2222-222222222222",
        "output": {"status_code": 200},
        "latency_ms": 12,
        "tokens": 5,
        "cost_usd": 0.001,
        "status": "ok",
        "ts": "2026-01-21T00:00:02Z"
      },
      {
        "type": "run.end",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "totals": {"tokens": 5, "cost_usd": 0.001},
        "ts": "2026-01-21T00:00:03Z"
      }
    ]
  }' | python -m json.tool



List runs (with pagination + latest validation)

GET /v1/runs?project_id=demo&limit=20&offset=0

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/runs?project_id=demo&limit=20&offset=0" \
  | python -m json.tool


Get run detail (includes steps + latest validation)

GET /v1/runs/{run_id}

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/runs/11111111-1111-1111-1111-111111111111" \
  | python -m json.tool


Validate a run (and persist result)

POST /v1/runs/{run_id}/validate

curl -s -X POST \
  -H "x-api-key: dev-key" \
  -H "Content-Type: application/json" \
  "http://localhost:8000/v1/runs/11111111-1111-1111-1111-111111111111/validate" \
  -d '{
    "runbook_yaml": "allowed_tools:\n  - httpx.post\nrequired_steps:\n  - name: \"shorten\"\nbudgets:\n  max_total_tokens: 100\n  max_total_cost_usd: 1.0\n"
  }' | python -m json.tool


List validations for a run

GET /v1/runs/{run_id}/validations?limit=10

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/runs/11111111-1111-1111-1111-111111111111/validations?limit=10" \
  | python -m json.tool


List projects

GET /v1/projects

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/projects" \
  | python -m json.tool


Project summary

GET /v1/projects/{project_id}/summary?limit=100

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/projects/demo/summary?limit=100" \
  | python -m json.tool


Project runs (optional convenience route)

GET /v1/projects/{project_id}/runs?limit=10&offset=0

curl -s -H "x-api-key: dev-key" \
  "http://localhost:8000/v1/projects/demo/runs?limit=10&offset=0" \
  | python -m json.tool



Database Schema (high level)

runs

id, project_id, runbook, status, started_at, ended_at, totals


steps

id, run_id (nullable for placeholders), index, name, tool, input_json, output_json, metrics

Unique index on (run_id, index) only when run_id is not null


run_validations

id, run_id, status, created_at, reasons_json, summary_json, runbook_yaml, input_hash

Unique index on (run_id, input_hash) for idempotency


Runbook YAML Spec (current)
allowed_tools:
  - httpx.post
required_steps:
  - name: "shorten"
budgets:
  max_total_tokens: 100
  max_total_cost_usd: 1.0



SDK (planned / in progress)

Goal: make ingestion + validation trivial.

Target Python usage
from obs_sdk import ObsClient

client = ObsClient(base_url="http://localhost:8000", api_key="dev-key", project_id="demo")

with client.run(runbook="shortify") as run:
    with run.step(name="shorten", tool="httpx.post", input={"originalUrl":"https://example.com"}) as s:
        # call your tool
        s.set_output({"status_code": 200})

    run.set_totals(tokens=123, cost_usd=0.01)

client.validate_run(run.run_id, runbook_yaml="...")


Roadmap
Next (high value)

Python SDK + TypeScript SDK (batching, retries, run context, failure hooks)

Frontend dashboard (Runs list/detail, validation history, project summary)

Runbook enhancements:

tool allow/deny + patterns

step constraints (tool per step, latency budgets, required outputs)

richer “diff” output for failures

Alerts / webhooks on failed validations

Multi-tenant auth model (API keys per project/org)


Longer term

Streaming ingestion + tailing runs live

CI integration (“agent tests”)

Comparison/regression across runs (before/after prompt/tool changes)

Hosted SaaS

Development Notes
Alembic migrations

Migrations run on container boot. If you create a migration:

docker compose run --rm api alembic -c /app/alembic.ini revision --autogenerate -m "your_message"
docker compose up -d --build


License

MIT 
