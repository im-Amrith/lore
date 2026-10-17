"""The agent LLM pool: error classification, cooldowns and skipping, with no network calls."""

import json

import httpx
import openai
import pytest

from lore.llm import agent

NOW = 1_800_000_000.0


def _err(cls, status, msg):
    req = httpx.Request("POST", "https://x/chat/completions")
    return cls(msg, response=httpx.Response(status, request=req), body=None)


def test_classify_minute_daily_spend_and_errors():
    e = _err(openai.RateLimitError, 429, "Rate limit reached on tokens per minute (TPM): Please try again in 13.2s.")
    assert agent.classify(e, "groq", NOW) == ("minute", NOW + 13.2)
    e = _err(openai.RateLimitError, 429, "Rate limit reached on tokens per day (TPD): Please try again in 7m12s.")
    assert agent.classify(e, "groq", NOW) == ("daily", NOW + 432)
    e = _err(openai.RateLimitError, 429, "You exceeded your current quota, please check your plan and billing "
             "details. quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    reason, until = agent.classify(e, "gemini", NOW)
    assert reason == "daily" and until > NOW  # "billing" in Gemini's usual text is not a spend cap
    e = _err(openai.RateLimitError, 429, "GenerateRequestsPerMinutePerProjectPerModel-FreeTier 'retryDelay': '41s'")
    assert agent.classify(e, "gemini", NOW) == ("minute", NOW + 41)
    e = _err(openai.APIStatusError, 429, "Your project has exceeded its monthly spending cap")
    assert agent.classify(e, "gemini", NOW)[0] == "spend"
    assert agent.classify(_err(openai.BadRequestError, 400, "unsupported"), "gemini", NOW) == ("other", None)


class _Fake:
    """Stands in for the OpenAI client: per model, a list of outcomes (an exception or reply text)."""

    def __init__(self, plan):
        self.plan, self.calls = plan, []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw["model"])
        outcome = self.plan[kw["model"]].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        msg = type("M", (), {"content": outcome, "tool_calls": None})
        return type("R", (), {"choices": [type("C", (), {"message": msg})], "usage": None})


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "AGENT_LLM_STATE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "count_call", lambda kind: 1)
    eps = [{"label": f"p:{m}", "provider": "groq", "base_url": "u", "api_key": "k", "model": m, "schema": True}
           for m in ("a", "b", "c")]
    monkeypatch.setattr(agent, "pool", lambda: eps)
    return tmp_path / "state.json"


def test_rate_limited_endpoint_cools_down_and_is_skipped(monkeypatch, state):
    fake = _Fake({"a": [_err(openai.RateLimitError, 429, "per minute. Please try again in 30s.")],
                  "b": ["first", "second"], "c": []})
    monkeypatch.setattr(agent, "_client", lambda *a: fake)
    assert agent.agent_chat([{"role": "user", "content": "1"}], use_cache=False)["endpoint"] == "p:b"
    assert agent.agent_chat([{"role": "user", "content": "2"}], use_cache=False)["content"] == "second"
    assert fake.calls == ["a", "b", "b"]  # a is cooling down: never hammered
    assert json.loads(state.read_text())["p:a"]["reason"] == "minute"


def test_all_exhausted_fails_with_the_states(monkeypatch, state):
    def daily():
        return _err(openai.RateLimitError, 429, "tokens per day (TPD): Please try again in 2h0m0s.")
    fake = _Fake({"a": [daily()], "b": [daily()], "c": [_err(openai.BadRequestError, 400, "bad option")]})
    monkeypatch.setattr(agent, "_client", lambda *a: fake)
    with pytest.raises(agent.LLMError, match="p:a: daily"):
        agent.agent_chat([{"role": "user", "content": "x"}], use_cache=False)
    assert fake.calls == ["a", "b", "c"]  # one try each; no waiting on a 2-hour reset
