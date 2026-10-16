"""Disk cache and daily call counter shared by the chat and embedding wrappers.

Cache entries are JSON files under data/cache/llm/<kind>/<2-char shard>/<sha256>.json,
keyed by a hash of model + prompt + input. The counter lives in
data/cache/llm/calls/<UTC date>.json and counts uncached calls per kind; each kind
stops at LLM_DAILY_CALL_CAP. Cached results never count.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lore.config import LLM_CACHE_DIR, get_settings

_lock = threading.Lock()


class CallCapExceeded(RuntimeError):
    """Raised before an uncached call once today's count has reached LLM_DAILY_CALL_CAP."""


def cache_key(model: str, prompt: str, input: Any) -> str:
    blob = json.dumps({"model": model, "prompt": prompt, "input": input}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path(kind: str, key: str, root: Path) -> Path:
    return root / kind / key[:2] / f"{key}.json"


def cache_get(kind: str, key: str, root: Path = LLM_CACHE_DIR) -> Any | None:
    p = _path(kind, key, root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))["value"]


def cache_put(kind: str, key: str, value: Any, meta: dict | None = None, root: Path = LLM_CACHE_DIR) -> None:
    p = _path(kind, key, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"value": value, "meta": meta or {}}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _counter_file(root: Path) -> Path:
    return root / "calls" / f"{datetime.now(timezone.utc):%Y-%m-%d}.json"


def calls_today(root: Path = LLM_CACHE_DIR) -> dict[str, int]:
    f = _counter_file(root)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def count_call(kind: str, root: Path = LLM_CACHE_DIR, cap: int | None = None) -> int:
    """Reserve one uncached call of this kind; raise CallCapExceeded at the cap.

    Counted before the request is sent, so failed and retried requests count too.
    """
    cap = get_settings().llm_daily_call_cap if cap is None else cap
    with _lock:
        f = _counter_file(root)
        counts = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        n = counts.get(kind, 0)
        if n >= cap:
            raise CallCapExceeded(f"{kind}: {n} calls today, cap is {cap} (LLM_DAILY_CALL_CAP)")
        counts[kind] = n + 1
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(counts), encoding="utf-8")
        return n + 1
