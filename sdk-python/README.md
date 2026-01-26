# obs-sdk (Python)

Python SDK for an agent observability backend:
- Batch ingest events to `POST /v1/events`
- Run/Step context managers that emit:
  - `run.start`, `step.start`, `step.end`, `run.end`
- Validate a runbook against a run via `POST /v1/runs/{run_id}/validate`

## Install (local dev)

From the `sdk-python/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .


pip install veriOps-sdk
from veriops_sdk import ObsClient