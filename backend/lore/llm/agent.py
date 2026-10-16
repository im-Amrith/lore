"""Tool-calling chat for the agents: Groq (role "smart") first, Gemini as the fallback.

    agent_chat(messages, tools, tool_choice) -> {"content", "tool_calls": [{id, name, arguments}], "model"}

On a 429 or a failed tool call (Groq answers 400 "tool_use_failed" when the model writes a
malformed call), the request is retried once on Groq, then sent to LLM_FALLBACK_MODEL on the
fast (Gemini) endpoint. Responses are cached on disk keyed by model + messages + tools, so
re-running the eval replays the same answers for free; a changed tool result changes the
messages and misses the cache. Uncached requests count against LLM_DAILY_CALL_CAP (kind "agent").

Gemini 3 rejects replayed tool calls that lack its own thought_signature, so for the fallback
the earlier tool calls and results are flattened into plain text turns (flatten).
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

RETRY_WAIT_MAX = 60.0  # seconds to wait on a 429 before the one retry (Groq free tier: 8K tokens/min)


def _endpoints() -> list[tuple[str, str, str, str]]:
    """(label, base_url, api_key, model) in the order they are tried."""
    s = get_settings()
    out = [("groq", *role_config("smart"))]
    if s.llm_fast_api_key and s.llm_fallback_model:
        out.append(("gemini", s.llm_fast_base_url, s.llm_fast_api_key, s.llm_fallback_model))
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
    return {"content": m.content or "", "tool_calls": calls}


def agent_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               tool_choice: str | dict = "auto", json_schema: dict | None = None,
               use_cache: bool = True) -> dict[str, Any]:
    last_err: Exception | None = None
    for label, base_url, api_key, model in _endpoints():
        key = cache_key(model, json.dumps({"tools": tools, "tool_choice": tool_choice, "schema": json_schema},
                                          sort_keys=True), messages)
        if use_cache and (hit := cache_get("agent", key)) is not None:
            return hit
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
            try:
                out = {**_message(_client(base_url, api_key).chat.completions.create(**kwargs)), "model": model}
                if json_schema and not out["content"].strip():
                    raise EmptyReply(f"{model} returned an empty answer")
                cache_put("agent", key, out, {"model": model, "at": int(time.time())})
                return out
            except Exception as e:  # noqa: BLE001 - filtered by _retryable
                if not _retryable(e):
                    raise
                last_err = e
                print(f"    [agent llm] {label} {type(e).__name__}: {str(e)[:300]}"
                      f"{' (retrying)' if attempt == 0 else ' (falling back)'}", flush=True)
                if attempt == 0 and isinstance(e, openai.RateLimitError):
                    wait = _retry_after(e) or _wait_hint(e) or 10.0
                    if wait > RETRY_WAIT_MAX:  # a daily limit: don't wait, fall back now
                        break
                    time.sleep(wait + 1)
    raise LLMError(f"agent call failed on every endpoint: {last_err}")
