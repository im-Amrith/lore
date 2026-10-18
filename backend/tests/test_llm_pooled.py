"""chat_json in pooled mode (the M15 sync): through agent_chat with the sync's extra endpoints."""

from lore.config import SYNC_EXTRA_POOL
from lore.llm import agent, chat


def test_pooled_chat_json_goes_through_the_agent_pool(monkeypatch):
    seen = {}

    def fake_agent_chat(messages, extra_pool=(), **kw):
        seen["extra"], seen["messages"] = extra_pool, messages
        return {"content": 'Sure:\n```json\n{"decisions": []}\n```', "model": "m", "endpoint": "groq:m"}

    monkeypatch.setattr(agent, "agent_chat", fake_agent_chat)
    monkeypatch.setattr(chat, "role_config", lambda role: ("http://x", "k", "fast-model"))
    monkeypatch.setattr(chat, "cache_get", lambda kind, key: None)
    monkeypatch.setattr(chat, "cache_put", lambda *a, **k: None)
    token = chat.POOLED.set(SYNC_EXTRA_POOL)
    try:
        out = chat.chat_json("fast", "system", "text", {"type": "object"}, "decisions")
    finally:
        chat.POOLED.reset(token)
    assert out == {"decisions": []}
    assert seen["extra"] == SYNC_EXTRA_POOL
    assert "matching this JSON schema" in seen["messages"][-1]["content"]


def test_sync_extra_endpoint_is_not_in_the_answer_pool():
    assert not {m for _, _, m, _ in SYNC_EXTRA_POOL} & {m for _, _, m, _ in agent.AGENT_LLM_POOL}
