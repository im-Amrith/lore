"""Tool-calling chat for the agents: Gemini (LLM_AGENT_MODEL on the fast endpoint) first, Groq
(role "smart") as the fallback.

    agent_chat(messages, tools, tool_choice) -> {"content", "tool_calls": [{id, name, arguments}],
                                                 "model", "prompt_tokens", "seconds"}

Why Gemini first: Groq's free tier allows 8,000 tokens a minute and one question needs two or
three calls of 2-4K tokens, so Groq stalls a live demo on 429s. On a 429, a 5xx, a timeout, an
empty answer or a failed tool call (Groq answers 400 "tool_use_failed" when the model writes a
malformed call), the request is retried once, then sent to the next endpoint; a 413 (request
too large) goes straight to the next one. Responses are cached on disk keyed by model + messages
+ tools, so re-running the eval replays the same answers for free; a changed tool result
changes the messages and misses the cache. Uncached requests count against LLM_DAILY_CALL_CAP
(kind "agent").

Gemini 3 rejects replayed tool calls that lack its own thought_signature, so for Gemini the
earlier tool calls and results are sent as plain text turns (flatten).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import openai

from lore.config import get_settings
from lore.llm.cache import cache_get, cache_key, cache_put, count_call
from lore.llm.chat import LLMError, _client, _retry_after, role_config

RETRY_WAIT_MAX = 60.0  # seconds to wait on a 429 before the one retry; longer = a daily limit


def _endpoints() -> list[tuple[str, str, str, str]]:
    """(label, base_url, api_key, model) in the order they are tried."""
    s = get_settings()
    out = []
    if s.llm_fast_api_key and s.llm_agent_model:
        out.append(("gemini", s.llm_fast_base_url, s.llm_fast_api_key, s.llm_agent_model))
    if s.llm_smart_api_key and s.llm_smart_model:
        out.append(("groq", *role_config("smart")))
    if not out:
        raise LLMError("no agent LLM configured: set LLM_FAST_API_KEY (+ LLM_AGENT_MODEL) or LLM_SMART_*")
    return out


def _wait_hint(e: Exception) -> float | None:
    """Groq puts the wait in the message: 'Please try again in 13.2s' (or '1m5.3s')."""
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(e))
    return (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else None


class EmptyReply(RuntimeError):
    pass


def _retryable(e: Exception) -> bool:
    if isinstance(e, EmptyReply):
        return True
    if isinstance(e, (openai.RateLimitError, openai.InternalServerError, openai.APITimeoutError,
                      openai.APIConnectionError)):
        return True
    # Groq: 400 with code tool_use_failed when the model's tool call doesn't parse.
    return isinstance(e, openai.BadRequestError) and "tool" in str(e).lower()


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


def agent_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               tool_choice: str | dict = "auto", json_schema: dict | None = None,
               use_cache: bool = True) -> dict[str, Any]:
    last_err: Exception | None = None
    for label, base_url, api_key, model in _endpoints():
        key = cache_key(model, json.dumps({"tools": tools, "tool_choice": tool_choice, "schema": json_schema},
                                          sort_keys=True), messages)
        if use_cache and (hit := cache_get("agent", key)) is not None:
            return {**hit, "cached": True}
        kwargs: dict[str, Any] = {"model": model, "temperature": 0,
                                  "messages": flatten(messages) if label == "gemini" else messages}
        if tools:
            kwargs.update(tools=tools, tool_choice=tool_choice)
        if json_schema:
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": "answer", "schema": json_schema, "strict": True}}
        if label == "gemini":  # Gemini 3 thinks at length by default (77 s for "say hi")
            kwargs["reasoning_effort"] = "low"
        for attempt in range(2):  # one try + one retry, then the next endpoint
            count_call("agent")
            t0 = time.monotonic()
            try:
                resp = _client(base_url, api_key).chat.completions.create(**kwargs)
                out = {**_message(resp), "model": model, "seconds": round(time.monotonic() - t0, 1)}
                if json_schema and not out["content"].strip():
                    raise EmptyReply(f"{model} returned an empty answer")
                cache_put("agent", key, out, {"model": model, "at": int(time.time())})
                return out
            except Exception as e:  # noqa: BLE001 - filtered below
                last_err = e
                too_large = isinstance(e, openai.APIStatusError) and e.status_code == 413
                if not (too_large or _retryable(e)):
                    raise
                next_step = "next endpoint" if too_large or attempt == 1 else "retrying"
                print(f"    [agent llm] {label} {type(e).__name__}: {str(e)[:200]} ({next_step})", flush=True)
                if too_large:
                    break
                if attempt == 0 and isinstance(e, openai.RateLimitError):
                    wait = _retry_after(e) or _wait_hint(e) or 10.0
                    if wait > RETRY_WAIT_MAX:
                        break
                    time.sleep(wait + 1)
    raise LLMError(f"agent call failed on every endpoint: {last_err}")
