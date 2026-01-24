from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import httpx

from .utils import backoff_sleep_seconds, json_dumps_compact, safe_str


logger = logging.getLogger("obs_sdk")


HookOnResult = Callable[[Dict[str, Any]], None]
HookOnError = Callable[[BaseException], None]


@dataclass(frozen=True)
class ObsClientConfig:
    base_url: str
    api_key: str
    project_id: str

    # batching
    max_batch_events: int = 100
    flush_interval_events: int = 50  # auto-flush when buffer reaches this size

    # retry policy (flush)
    timeout_s: float = 10.0
    max_retries: int = 5
    backoff_base_s: float = 0.3
    backoff_cap_s: float = 5.0
    backoff_jitter: float = 0.2

    # behavior
    raise_on_flush_error: bool = False


@dataclass
class FlushResult:
    ok: bool
    status: str
    ingested: int = 0
    failed: int = 0
    errors: List[Any] = None  # server-provided list
    warnings: List[Any] = None  # server-provided list
    exception: Optional[str] = None  # string form
    http_status: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "ingested": self.ingested,
            "failed": self.failed,
            "errors": self.errors or [],
            "warnings": self.warnings or [],
            "exception": self.exception,
            "http_status": self.http_status,
        }


class ObsClient:
    """
    Thread-safe event buffer + flush to POST /v1/events with retries.
    Provides run() context manager via obs_sdk.run.RunContext.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        project_id: str,
        *,
        max_batch_events: int = 100,
        flush_interval_events: int = 50,
        timeout_s: float = 10.0,
        max_retries: int = 5,
        backoff_base_s: float = 0.3,
        backoff_cap_s: float = 5.0,
        backoff_jitter: float = 0.2,
        raise_on_flush_error: bool = False,
        on_result: Optional[HookOnResult] = None,
        on_error: Optional[HookOnError] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.config = ObsClientConfig(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            project_id=project_id,
            max_batch_events=max_batch_events,
            flush_interval_events=flush_interval_events,
            timeout_s=timeout_s,
            max_retries=max_retries,
            backoff_base_s=backoff_base_s,
            backoff_cap_s=backoff_cap_s,
            backoff_jitter=backoff_jitter,
            raise_on_flush_error=raise_on_flush_error,
        )
        self._on_result = on_result
        self._on_error = on_error

        self._lock = threading.Lock()
        self._buffer: List[Dict[str, Any]] = []

        self._client = http_client or httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_s,
            headers={
                "x-api-key": self.config.api_key,
                "content-type": "application/json",
            },
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def enqueue(self, event: Dict[str, Any]) -> Optional[FlushResult]:
        """
        Add an event to the buffer. Auto-flush when buffer reaches flush_interval_events.
        Returns a FlushResult only if an auto-flush occurred.
        """
        flush_now = False
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self.config.flush_interval_events:
                flush_now = True

        if flush_now:
            return self.flush()
        return None

    def flush(self) -> FlushResult:
        """
        Flush buffered events in batches. Retries on network/timeouts/5xx.
        Returns aggregated FlushResult.
        """
        # Drain buffer quickly under lock
        with self._lock:
            if not self._buffer:
                return FlushResult(ok=True, status="ok", ingested=0, failed=0, errors=[], warnings=[])
            events = self._buffer
            self._buffer = []

        total_ingested = 0
        total_failed = 0
        all_errors: List[Any] = []
        all_warnings: List[Any] = []

        try:
            for chunk in _chunks(events, self.config.max_batch_events):
                r = self._post_events_with_retries(chunk)
                total_ingested += r.ingested
                total_failed += r.failed
                all_errors.extend(r.errors or [])
                all_warnings.extend(r.warnings or [])

                if not r.ok:
                    # Stop early; push remaining events back into buffer? That can cause duplication.
                    # Prefer "at least once" semantics: we already popped from buffer.
                    # Caller can choose raise_on_flush_error to fail fast.
                    if self.config.raise_on_flush_error:
                        raise RuntimeError(f"flush failed: {r.to_dict()}")
                    return FlushResult(
                        ok=False,
                        status=r.status,
                        ingested=total_ingested,
                        failed=total_failed,
                        errors=all_errors,
                        warnings=all_warnings,
                        exception=r.exception,
                        http_status=r.http_status,
                    )

            return FlushResult(
                ok=True,
                status="ok",
                ingested=total_ingested,
                failed=total_failed,
                errors=all_errors,
                warnings=all_warnings,
            )

        except BaseException as e:
            # Non-fatal by default; optionally raise
            if self._on_error:
                try:
                    self._on_error(e)
                except Exception:
                    logger.exception("obs_sdk on_error hook raised")

            logger.warning("obs_sdk flush exception: %s", safe_str(e))
            if self.config.raise_on_flush_error:
                raise

            return FlushResult(
                ok=False,
                status="error",
                ingested=total_ingested,
                failed=total_failed + len(events),
                errors=all_errors,
                warnings=all_warnings,
                exception=safe_str(e),
            )

    def validate_run(self, run_id: str, *, runbook_yaml: str) -> Dict[str, Any]:
        """
        Calls POST /v1/runs/{run_id}/validate with {"runbook_yaml": "..."}.
        Returns parsed JSON. Raises for non-2xx responses.
        """
        path = f"/v1/runs/{run_id}/validate"
        resp = self._client.post(path, json={"runbook_yaml": runbook_yaml})
        resp.raise_for_status()
        return resp.json()

    def run(self, *, runbook: str):
        """
        Returns a RunContext that emits run/step events.
        """
        from .run import RunContext

        return RunContext(client=self, runbook=runbook, project_id=self.config.project_id)

    def _post_events_with_retries(self, events: Sequence[Dict[str, Any]]) -> FlushResult:
        payload = {"events": list(events)}
        last_exc: Optional[BaseException] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                resp = self._client.post("/v1/events", json=payload)
                http_status = resp.status_code

                # Retry on 5xx
                if 500 <= http_status <= 599:
                    raise httpx.HTTPStatusError(
                        f"server {http_status}",
                        request=resp.request,
                        response=resp,
                    )

                # For 4xx, do not retry: log details and fail
                if 400 <= http_status <= 499:
                    logger.error("obs_sdk ingest HTTP %s: %s", http_status, resp.text)
                    resp.raise_for_status()

                resp.raise_for_status()


                data = resp.json() if resp.content else {}
                if self._on_result:
                    try:
                        self._on_result(data)
                    except Exception:
                        logger.exception("obs_sdk on_result hook raised")

                # Respect your backend response envelope
                return FlushResult(
                    ok=(data.get("status") == "ok"),
                    status=str(data.get("status", "ok")),
                    ingested=int(data.get("ingested", 0) or 0),
                    failed=int(data.get("failed", 0) or 0),
                    errors=list(data.get("errors", []) or []),
                    warnings=list(data.get("warnings", []) or []),
                    http_status=http_status,
                )

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_exc = e
                if attempt >= self.config.max_retries:
                    break
                sleep_s = backoff_sleep_seconds(
                    attempt=attempt,
                    base=self.config.backoff_base_s,
                    cap=self.config.backoff_cap_s,
                    jitter=self.config.backoff_jitter,
                )
                logger.info(
                    "obs_sdk flush retrying in %.2fs (attempt %d/%d): %s",
                    sleep_s,
                    attempt + 1,
                    self.config.max_retries,
                    safe_str(e),
                )
                import time as _time

                _time.sleep(sleep_s)

            except BaseException as e:
                # Unknown error: do not retry by default
                last_exc = e
                break

        if self._on_error and last_exc is not None:
            try:
                self._on_error(last_exc)
            except Exception:
                logger.exception("obs_sdk on_error hook raised")

        return FlushResult(
            ok=False,
            status="error",
            ingested=0,
            failed=len(events),
            errors=[],
            warnings=[],
            exception=safe_str(last_exc) if last_exc else "unknown error",
        )


def _chunks(items: Sequence[Dict[str, Any]], chunk_size: int) -> List[List[Dict[str, Any]]]:
    if chunk_size <= 0:
        return [list(items)]
    out: List[List[Dict[str, Any]]] = []
    buf: List[Dict[str, Any]] = []
    for x in items:
        buf.append(x)
        if len(buf) >= chunk_size:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out
