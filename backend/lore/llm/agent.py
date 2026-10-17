"""Tool-calling chat for the agents over a pool of free-tier endpoints (AGENT_LLM_POOL in config).

    agent_chat(messages, tools, tool_choice, json_schema)
      -> {"content", "tool_calls": [{id, name, arguments}], "model", "endpoint", "prompt_tokens", "seconds"}

Endpoints are tried in pool order (quality first). An endpoint is never hammered:
  - a per-minute 429 puts it on cooldown for the retry-after time (or AGENT_COOLDOWN_DEFAULT),
  - a daily-quota error marks it exhausted until its reset (the retry hint, else the next
    Gemini reset at GEMINI_DAILY_RESET_UTC_HOUR, else an hour),
  - a spend-cap / billing error marks it exhausted for the day and is logged loudly: it means a
    billing-enabled key is configured, which must never happen,
  - a 5xx or timeout cools it down briefly; any other API error (a 400 for an unsupported
    option, a 413, an empty answer, Groq's tool_use_failed) moves on without a cooldown.
Then the next endpoint gets the request. The state lives in AGENT_LLM_STATE, so the eval,
warm.py and the API share it. If every endpoint is cooling down and the soonest is back within
AGENT_WAIT_MAX seconds, the call waits for it once; otherwise it fails with the states.

Responses are cached on disk keyed by model + messages + tools; a cached reply from any pool
model is reused. Uncached requests count against LLM_DAILY_CALL_CAP (kind "agent").

Gemini 3 rejects replayed tool calls that lack its own thought_signature, so for Gemini the
earlier tool calls and results are sent as plain text turns (flatten). Endpoints without strict
json_schema support get json_object mode plus the schema in the prompt.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import openai

from lore.config import (
    AGENT_COOLDOWN_DEFAULT,
    AGENT_LLM_POOL,
    AGENT_LLM_STATE,
    AGENT_TIMEOUT,
    AGENT_WAIT_MAX,
    GEMINI_DAILY_RESET_UTC_HOUR,
    get_settings,
)
from lore.llm.cache import cache_get, cache_key, cache_put, count_call
from lore.llm.chat import LLMError, _client, _retry_after

ERROR_COOLDOWN = 30  # seconds after a 5xx or timeout
_lock = threading.Lock()


class EmptyReply(RuntimeError):
    pass


# ---------------------------------------------------------------- the pool and its state

def pool() -> list[dict[str, Any]]:
    """Configured endpoints, in order; entries whose key env var is empty are left out."""
    s = get_settings()
    base = {"gemini": s.llm_fast_base_url, "groq": s.llm_smart_base_url}
    out = []
    for provider, key_var, model, schema in AGENT_LLM_POOL:
        key = getattr(s, key_var.lower(), "")
        if key:
            out.append({"label": f"{provider}:{model}", "provider": provider, "base_url": base[provider],
                        "api_key": key, "model": model, "schema": schema})
    if not out:
        raise LLMError("no agent LLM configured: set LLM_FAST_API_KEY and/or LLM_SMART_API_KEY")
    return out


def load_state() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(AGENT_LLM_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _mark(label: str, until: float, reason: str, detail: str) -> None:
    with _lock:
        state = load_state()
        state[label] = {"until": int(until), "reason": reason, "detail": detail[:200],
                        "until_utc": f"{datetime.fromtimestamp(until, timezone.utc):%Y-%m-%d %H:%M}"}
        AGENT_LLM_STATE.parent.mkdir(parents=True, exist_ok=True)
        AGENT_LLM_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _wait_hint(e: Exception) -> float | None:
    """Retry hints inside error text: Groq 'try again in 1m5.3s', Gemini 'retryDelay': '41s'."""
    msg = str(e)
    if m := re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", msg):
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))
    if m := re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([\d.]+)s", msg):
        return float(m.group(1))
    return None


def _next_gemini_reset(now: float) -> float:
    t = datetime.fromtimestamp(now, timezone.utc).replace(hour=GEMINI_DAILY_RESET_UTC_HOUR, minute=0,
                                                          second=0, microsecond=0)
    if t.timestamp() <= now:
        t += timedelta(days=1)
    return t.timestamp()


def classify(e: Exception, provider: str, now: float) -> tuple[str, float | None]:
    """(reason, cooled-down-until or None). reason: spend, daily, minute, error or other."""
    msg, status = str(e), getattr(e, "status_code", None)
    # Not "billing": Gemini's ordinary free-tier 429 says "check your plan and billing details".
    if status == 402 or (status in (403, 429) and re.search(r"spend|budget|prepay", msg, re.I)):
        return "spend", _next_gemini_reset(now)
    if status == 429:
        hint = _retry_after(e) or _wait_hint(e)
        if re.search(r"per ?day|\(TPD\)|\(RPD\)|daily", msg, re.I):
            if hint and hint > 120:
                return "daily", now + hint
            return "daily", _next_gemini_reset(now) if provider == "gemini" else now + 3600
        return "minute", now + (hint or AGENT_COOLDOWN_DEFAULT)
    if isinstance(e, (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError)):
        return "error", now + ERROR_COOLDOWN
    return "other", None


# ---------------------------------------------------------------- calls

def flatten(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool-call history -> text turns, for endpoints that can't replay foreign tool calls."""
    names: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for i, m in enumerate(messages):
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                names[tc["id"]] = tc["function"]["name"]
                calls.append(f"{tc['function']['name']}({tc['function']['arguments']})")
            out.append({"role": "assistant", "content": ((m.get("content") or "") + "\nI called: "
                                                         + "; ".join(calls)).strip()})
        elif m["role"] == "tool":
            out.append({"role": "user", "content": f"Result of {names.get(m['tool_call_id'], 'tool')}: {m['content']}"})
        elif m["role"] == "system" and i > 0:
            out.append({"role": "user", "content": m["content"]})
        else:
            out.append(m)
    return out


def _message(resp: Any) -> dict[str, Any]:
    m = resp.choices[0].message
    calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
             for tc in (m.tool_calls or [])]
    usage = getattr(resp, "usage", None)
    return {"content": m.content or "", "tool_calls": calls,
            "prompt_tokens": getattr(usage, "prompt_tokens", None)}


def _kwargs(ep: dict[str, Any], messages: list[dict[str, Any]], tools: list | None, tool_choice: Any,
            json_schema: dict | None) -> dict[str, Any]:
    msgs = flatten(messages) if ep["provider"] == "gemini" else list(messages)
    kw: dict[str, Any] = {"model": ep["model"], "temperature": 0}
    if tools:
        kw.update(tools=tools, tool_choice=tool_choice)
    if json_schema and ep["schema"]:
        kw["response_format"] = {"type": "json_schema",
                                 "json_schema": {"name": "answer", "schema": json_schema, "strict": True}}
    elif json_schema:
        kw["response_format"] = {"type": "json_object"}
        msgs.append({"role": "user", "content": "Reply with one JSON object that matches this JSON schema: "
                                                + json.dumps(json_schema)})
    if ep["provider"] == "gemini":  # Gemini 3 thinks at length by default (77 s for "say hi")
        kw["reasoning_effort"] = "low"
    kw["messages"] = msgs
    return kw


def agent_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               tool_choice: str | dict = "auto", json_schema: dict | None = None,
               use_cache: bool = True) -> dict[str, Any]:
    endpoints = pool()
    req = json.dumps({"tools": tools, "tool_choice": tool_choice, "schema": json_schema}, sort_keys=True)
    keys = {ep["label"]: cache_key(ep["model"], req, messages) for ep in endpoints}
    if use_cache:
        for ep in endpoints:
            if (hit := cache_get("agent", keys[ep["label"]])) is not None:
                return {**hit, "endpoint": hit.get("endpoint", ep["label"]), "cached": True}

    last_err: Exception | None = None
    for waited in (False, True):
        state, now = load_state(), time.time()
        for ep in endpoints:
            st = state.get(ep["label"])
            if st and st["until"] > now:
                continue
            count_call("agent")
            t0 = time.monotonic()
            try:
                resp = _client(ep["base_url"], ep["api_key"]).with_options(timeout=AGENT_TIMEOUT).chat.completions.create(
                    **_kwargs(ep, messages, tools, tool_choice, json_schema))
                out = {**_message(resp), "model": ep["model"], "endpoint": ep["label"],
                       "seconds": round(time.monotonic() - t0, 1)}
                if json_schema and not out["content"].strip():
                    raise EmptyReply(f"{ep['model']} returned an empty answer")
                cache_put("agent", keys[ep["label"]], out, {"model": ep["model"], "at": int(time.time())})
                return out
            except (openai.APIError, EmptyReply) as e:
                last_err = e
                reason, until = classify(e, ep["provider"], time.time())
                if until:
                    _mark(ep["label"], until, reason, str(e))
                if reason == "spend":
                    print(f"    [agent llm] {ep['label']}: SPEND CAP / BILLING error. A billing-enabled key is "
                          "configured; remove it from .env (free-tier keys only).", flush=True)
                note = f"cooling until {datetime.fromtimestamp(until, timezone.utc):%H:%M:%S} UTC" if until else "skipped"
                print(f"    [agent llm] {ep['label']} {reason}: {type(e).__name__} {str(e)[:160]} ({note})", flush=True)
        state, now = load_state(), time.time()
        cooling = [state[ep["label"]]["until"] for ep in endpoints
                   if ep["label"] in state and state[ep["label"]]["until"] > now]
        if waited or not cooling or min(cooling) - now > AGENT_WAIT_MAX:
            break
        wait = min(cooling) - now + 1
        print(f"    [agent llm] every endpoint busy; waiting {wait:.0f}s for the first to cool down", flush=True)
        time.sleep(wait)
    summary = "; ".join(f"{ep['label']}: {state.get(ep['label'], {}).get('reason', 'failed')} "
                        f"until {state.get(ep['label'], {}).get('until_utc', '-')}" for ep in endpoints)
    raise LLMError(f"no agent LLM endpoint answered ({summary}); last error: {last_err}")
