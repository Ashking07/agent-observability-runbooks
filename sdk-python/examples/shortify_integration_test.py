import os
import httpx
from obs_sdk import ObsClient

OBS_BASE_URL = os.getenv("OBS_BASE_URL", "http://localhost:8000")
OBS_API_KEY = os.getenv("OBS_API_KEY", "dev-key")
OBS_PROJECT_ID = os.getenv("OBS_PROJECT_ID", "shortify")

SHORTIFY_BASE_URL = os.getenv("SHORTIFY_BASE_URL", "http://localhost:5000")
SHORTIFY_JWT = os.getenv("SHORTIFY_JWT", "")  # REQUIRED

# Updated to match your Shortify app mounting: POST /api/shorten
SHORTIFY_SHORTEN_PATH = os.getenv("SHORTIFY_SHORTEN_PATH", "/api/shorten")
SHORTIFY_URL_KEY = os.getenv("SHORTIFY_URL_KEY", "originalUrl")

RUNBOOK_YAML = """\
allowed_tools:
  - httpx.post
required_steps:
  - shorten
budgets:
  max_tokens: 2000
  max_cost_usd: 1.0
"""

def main() -> None:
    if not SHORTIFY_JWT:
        raise SystemExit("Set SHORTIFY_JWT env var to a valid Bearer token.")

    client = ObsClient(
        base_url=OBS_BASE_URL,
        api_key=OBS_API_KEY,
        project_id=OBS_PROJECT_ID,
    )

    original_url = "https://example.com/some/long/url"

    with client.run(runbook="shortify_real") as run:
        with run.step(
            name="shorten",
            tool="httpx.post",
            input={SHORTIFY_URL_KEY: original_url, "path": SHORTIFY_SHORTEN_PATH},
        ) as s:
            r = httpx.post(
                f"{SHORTIFY_BASE_URL}{SHORTIFY_SHORTEN_PATH}",
                json={SHORTIFY_URL_KEY: original_url},
                headers={"Authorization": f"Bearer {SHORTIFY_JWT}"},
                timeout=20,
            )
            s.set_output({"status_code": r.status_code, "body": r.text[:1000]})
            r.raise_for_status()

        run.set_totals(tokens=0, cost_usd=0.0)

    print("run_id:", run.run_id)
    v = client.validate_run(run.run_id, runbook_yaml=RUNBOOK_YAML)
    print("validation:", v)

if __name__ == "__main__":
    main()
