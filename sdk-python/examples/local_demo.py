import logging
import os
from pathlib import Path

from veriops_sdk import ObsClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

HERE = Path(__file__).parent
RUNBOOK_YAML = (HERE / "runbook_shortify_v1.yaml").read_text(encoding="utf-8")

BASE_URL = os.getenv("OBS_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("OBS_API_KEY", "dev-key")
PROJECT_ID = os.getenv("OBS_PROJECT_ID", "shortify")


def main() -> None:
    client = ObsClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        project_id=PROJECT_ID,
        flush_interval_events=50,
        max_batch_events=100,
        max_retries=5,
        raise_on_flush_error=False,  # do not crash host app
        on_result=lambda data: logging.getLogger("obs_sdk.hook").info("ingest result: %s", data),
        on_error=lambda e: logging.getLogger("obs_sdk.hook").warning("ingest error: %s", e),
    )

    try:
        long_url = "https://example.com/some/long/url"

        with client.run(runbook="shortify_v1") as run:
            with run.step(name="expand_url", tool="requests.get", input={"url": long_url}) as s:
                # Simulate work
                html_bytes = 42_000
                s.set_output({"bytes": html_bytes})

            with run.step(name="summarize", tool="openai.chat.completions", input={"chars": 42_000}) as s:
                # Simulate LLM
                summary = "This is a short summary."
                s.set_output({"summary": summary})
                s.set_tokens_cost(tokens=220, cost_usd=0.0023)

            run.set_totals(tokens=220, cost_usd=0.0023)

        print(f"run_id: {run.run_id}")

        validation = client.validate_run(run.run_id, runbook_yaml=RUNBOOK_YAML)
        print("validation:", validation)

    finally:
        client.close()


if __name__ == "__main__":
    main()
