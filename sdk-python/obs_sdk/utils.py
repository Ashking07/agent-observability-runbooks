from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def now_iso_z() -> str:
    # RFC3339-ish UTC with Z suffix
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_dumps_compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def stable_hash_sha256_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def backoff_sleep_seconds(
    attempt: int,
    base: float,
    cap: float,
    jitter: float,
) -> float:
    """
    Exponential backoff: min(cap, base * 2^attempt) with +/- jitter fraction.
    jitter=0.2 means random factor in [0.8, 1.2].
    """
    raw = min(cap, base * (2 ** attempt))
    if jitter <= 0:
        return raw
    factor = random.uniform(max(0.0, 1.0 - jitter), 1.0 + jitter)
    return raw * factor


def safe_str(e: BaseException) -> str:
    return f"{e.__class__.__name__}: {e}"


def coerce_dict(v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}
