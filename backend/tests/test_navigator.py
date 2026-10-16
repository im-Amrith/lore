"""Navigator without a real LLM: a scripted fake replaces agent_chat, and lore-mcp runs
in-process (Client(mcp)), so these check the loop's guarantees cheaply:
uncited sentences are dropped, the tool budget holds, org and user_id are forced by code."""

import json

import anyio
import pytest
from mcp.client import Client

from lore.agents import navigator as nav
from lore.config import NAVIGATOR_MAX_TOOL_CALLS, graph_name


def test_classify_intent():
    assert nav.classify_intent("Why did the Rust engine drop all_nodes_matrix?") == "why"
    assert nav.classify_intent("Who should I ask about indexes in the Rust engine?") == "who-knows"
    assert nav.classify_intent("Who owns the query planner?") == "owns"
    assert nav.classify_intent("Which parts of the engine depend on a single person?") == "risk"
    assert nav.classify_intent("If we change the parser, what else usually has to change?") == "impact"
    assert nav.classify_intent("What changed since I last asked?") == "changed"
    assert nav.classify_intent("Tell me about FalkorDB") == "general"


def test_compact_drops_noise_caps_lists_and_turns_urls_into_ids():
    out = nav.compact({"experts": [{"score": 42.86305, "source_url": "x", "parity": False,
                                    "evidence": ["https://github.com/FalkorDB/FalkorDB/pull/2350"] * 5}] * 12})
    assert len(out["experts"]) == 11 and out["experts"][-1] == "... 2 more"
    e = out["experts"][0]
    assert e == {"score": 42.9, "evidence": ["pr:FalkorDB/FalkorDB#2350"] * 5}


def test_evidence_resolves_ids_and_urls_only_if_a_tool_returned_them():
    ev = nav._Evidence()
    ev.add("trace_decision", {}, {"nodes": ["decision:x"], "edges": [
        {"id": "e", "source": "decision:x", "type": "DECIDED_IN", "target": "pr:o/r#1"}],
        "sources": {"pr:o/r#1": "https://github.com/o/r/pull/1"}, "cypher": []}, None)
    assert ev.resolve("decision:x") == "decision:x"
    assert ev.resolve("https://github.com/o/r/pull/1") == "pr:o/r#1"
    assert ev.resolve("pr:o/r#2") is None


def _graphs() -> list[str]:
    try:
        from lore.graph.client import get_db
        return get_db().list_graphs()
    except Exception:
        return []


needs_sandbox = pytest.mark.skipif(graph_name("im-Amrith") not in _graphs(), reason="sandbox graph not loaded")


class FakeLLM:
    """Replays scripted replies; records what it was sent."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, messages, tools=None, tool_choice="auto", json_schema=None, use_cache=True):
        self.seen.append({"messages": messages, "tools": tools, "json_schema": json_schema})
        return {**self.replies.pop(0), "model": "fake"}


def _call(i, name, args):
    return {"id": f"c{i}", "name": name, "arguments": json.dumps(args)}


def _run(question, fake, monkeypatch, **kw):
    from lore.mcp_server.server import mcp
    monkeypatch.setattr(nav, "agent_chat", fake)

    async def go():
        async with Client(mcp) as client:
            return await nav.ask(question, "im-Amrith", "tester", client, remember=False, **kw)
    return anyio.run(go)


@needs_sandbox
def test_answer_keeps_only_cites_a_tool_returned(monkeypatch):
    answer = {"intent": "why", "found": True, "not_found": "", "sentences": [
        {"text": "Links are cached in Redis.", "cites": ["decision:3dd18586343e603b", "pr:im-Amrith/lore-sandbox#999"]},
        {"text": "An invented claim.", "cites": ["decision:made-up"]},
    ]}
    fake = FakeLLM([
        {"content": "", "tool_calls": [_call(1, "trace_decision", {"node_id": "pr:im-Amrith/lore-sandbox#11",
                                                                   "org": "SomeoneElse"})]},
        {"content": "done", "tool_calls": []},
        {"content": json.dumps(answer), "tool_calls": []},
    ])
    r = _run("Why do we cache links in Redis?", fake, monkeypatch)
    assert [c["tool"] for c in r["tool_calls"]] == ["find_entities", "trace_decision"]
    assert r["tool_calls"][1]["args"]["org"] == "im-Amrith"  # the LLM's org is overridden
    assert [s["text"] for s in r["sentences"]] == ["Links are cached in Redis."]
    assert r["sentences"][0]["cites"] == ["decision:3dd18586343e603b"]
    assert r["dropped"][0]["text"] == "An invented claim."
    assert r["citations"][0]["url"] == "https://github.com/im-Amrith/lore-sandbox/pull/11"
    assert "remember" not in {t["function"]["name"] for t in fake.seen[0]["tools"]}
    assert fake.seen[-1]["json_schema"] is nav.ANSWER_SCHEMA and fake.seen[-1]["tools"] is None


@needs_sandbox
def test_tool_budget_and_recall_user_are_enforced(monkeypatch):
    many = [_call(i, "recall", {"user_id": "someone-else"}) for i in range(6)]
    fake = FakeLLM([
        {"content": "", "tool_calls": many},
        {"content": json.dumps({"intent": "changed", "found": False, "not_found": "nothing asked yet",
                                "sentences": []}), "tool_calls": []},
    ])
    r = _run("What changed since I last asked?", fake, monkeypatch)
    assert len(r["tool_calls"]) == NAVIGATOR_MAX_TOOL_CALLS
    assert all(c["args"]["user_id"] == "tester" for c in r["tool_calls"][1:])
    assert r["found"] is False and r["answer"].startswith("Not found: nothing asked yet.")
