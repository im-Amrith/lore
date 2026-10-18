"""Chat calls with structured (JSON schema) output, against one of two OpenAI-compatible
endpoints: role "fast" (Gemini, extraction) or "smart" (Groq, agents).

    chat_json("fast", system_prompt, user_text, schema, "decisions") -> dict

The cache key is model + (system prompt + schema) + user text, so changing the prompt
or the schema invalidates old results. Uncached calls are paced (LLM_MIN_INTERVAL) and
retried with exponential backoff on 429 / 5xx / timeouts, honouring Retry-After.
"""

from __future__ import annotations

import json
import random
import time
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

import openai

from lore.config import LLM_MAX_RETRIES, LLM_MIN_INTERVAL, get_settings
from lore.llm.cache import cache_get, cache_key, cache_put, count_call

# While set (the M15 sync sets it), chat_json goes through the agent pool plus these extra endpoints, so
# one endpoint out of quota can't stall a merge: no long retries, the next endpoint answers instead.
POOLED: ContextVar[list | None] = ContextVar("lore_llm_pooled", default=None)

_last_call: dict[str, float] = {}


class LLMError(RuntimeError):
    pass


def role_config(role: str) -> tuple[str, str, str]:
    s = get_settings()
    if role == "fast":
        cfg = (s.llm_fast_base_url, s.llm_fast_api_key, s.llm_fast_model)
    elif role == "smart":
        cfg = (s.llm_smart_base_url, s.llm_smart_api_key, s.llm_smart_model)
    else:
        raise ValueError(f"unknown LLM role {role!r}")
    if not cfg[1] or not cfg[2]:
        raise LLMError(f"LLM_{role.upper()}_API_KEY / LLM_{role.upper()}_MODEL not set")
    return cfg


@lru_cache
def _client(base_url: str, api_key: str) -> openai.OpenAI:
    # Retries are ours (below), so the client's own are off.
    return openai.OpenAI(base_url=base_url, api_key=api_key, max_retries=0, timeout=120)


def _pace(role: str) -> None:
    wait = _last_call.get(role, 0) + LLM_MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[role] = time.monotonic()


def _retry_after(err: Exception) -> float | None:
    try:
        return float(err.response.headers.get("retry-after"))  # type: ignore[attr-defined]
    except (TypeError, ValueError, AttributeError):
        return None


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t


def chat_json(role: str, system: str, user: str, schema: dict, name: str,
              temperature: float = 0.0, use_cache: bool = True) -> dict[str, Any]:
    base_url, api_key, model = role_config(role)
    prompt = system + "\n#schema " + json.dumps(schema, sort_keys=True)
    key = cache_key(model, prompt, user)
    if use_cache and (hit := cache_get("chat", key)) is not None:
        return hit
    if (extra := POOLED.get()) is not None:
        return _pooled_json(system, user, schema, key, role, name, extra)

    client = _client(base_url, api_key)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    response_format = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
    last_err: Exception | None = None
    bad_json = 0
    for attempt in range(LLM_MAX_RETRIES + 1):
        count_call("chat")
        _pace(role)
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature,
                                                  response_format=response_format)
            value = json.loads(_strip_fence(resp.choices[0].message.content or ""))
            cache_put("chat", key, value, {"model": model, "role": role, "name": name, "at": int(time.time())})
            return value
        except (openai.RateLimitError, openai.InternalServerError, openai.APITimeoutError,
                openai.APIConnectionError) as e:
            last_err = e
            delay = _retry_after(e) or min(90.0, 5.0 * 2 ** attempt) + random.uniform(0, 2)
            print(f"    [llm] {type(e).__name__}, retry {attempt + 1}/{LLM_MAX_RETRIES} in {delay:.0f}s", flush=True)
            time.sleep(delay)
        except json.JSONDecodeError as e:
            # Malformed JSON: retry once, then give up. Failures are never cached.
            last_err = e
            bad_json += 1
            if bad_json > 1:
                break
    raise LLMError(f"{role} call failed: {last_err}")


def _pooled_json(system: str, user: str, schema: dict, key: str, role: str, name: str, extra: list) -> dict[str, Any]:
    """chat_json through the agent pool (POOLED). The schema goes in the prompt, not response_format,
    so no endpoint rejects it for strict-mode rules; the reply is cached under chat_json's own key."""
    from lore.llm.agent import agent_chat  # agent imports this module

    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user + "\n\nReply with one JSON object only, matching this JSON schema: "
                                        + json.dumps(schema, sort_keys=True)}]
    reply = agent_chat(msgs, extra_pool=extra)
    text = _strip_fence(reply["content"])
    try:
        value = json.loads(text[text.find("{"):text.rfind("}") + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"{reply.get('endpoint')} returned no JSON object: {e}") from e
    cache_put("chat", key, value, {"model": reply.get("model"), "endpoint": reply.get("endpoint"), "role": role,
                                   "name": name, "at": int(time.time())})
    return value
