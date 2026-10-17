"""The HTTP API: rate limiter in isolation, and routes against the loaded graphs (no LLM calls:
/ask is only checked for validation and the rate limit, using a stubbed Navigator)."""

import pytest
from fastapi.testclient import TestClient

from lore.api import app as api
from lore.api.ratelimit import RateLimiter
from lore.config import graph_name


def test_rate_limiter_minute_and_day_windows():
    rl = RateLimiter(per_minute=2, per_day=3)
    assert rl.check("a", 0) == 0 and rl.check("a", 1) == 0
    assert rl.check("a", 2) == 58  # third in the same minute: wait until the first leaves the window
    assert rl.check("b", 2) == 0  # per user
    assert rl.check("a", 61) == 0  # the minute has passed; the day now holds 3
    assert rl.check("a", 200) == 86400 - 200  # day limit


def _graphs() -> list[str]:
    try:
        from lore.graph.client import get_db
        return get_db().list_graphs()
    except Exception:
        return []


needs_graphs = pytest.mark.skipif(
    not {graph_name("FalkorDB"), graph_name("im-Amrith")} <= set(_graphs()), reason="graphs not loaded")


@pytest.fixture
def client():
    with TestClient(api.app) as c:
        yield c


@needs_graphs
def test_module_page_and_unknowns(client):
    r = client.get("/module/graph/src/parser", params={"org": "FalkorDB"}).json()
    assert r["owners"]["listed_owner"] is False and r["experts"][0]["person"] == "AviAvni"
    assert {c["module"] for c in r["co_changed"][:2]} == {"graph/src/runtime", "graph/src/planner"}
    assert any(c["query"] == "module_decisions" for c in r["cypher"])
    sandbox = client.get("/module/module:lore-sandbox:analytics").json()  # org inferred from the id
    assert sandbox["org"] == "im-Amrith" and sandbox["owners"]["paper_owners"]
    assert client.get("/module/no-such-module").status_code == 404
    assert client.get("/risk", params={"org": "nope"}).status_code == 404


@needs_graphs
def test_risk_and_triage_inbox(client):
    r = client.get("/risk", params={"org": "im-Amrith"}).json()
    assert "storage" in r["single_expert_modules"]
    inbox = client.get("/triage", params={"preview": False}).json()
    assert all(i["task_id"].startswith("task:triage:issue:") for i in inbox["items"])


@needs_graphs
def test_ask_validates_and_rate_limits(client, monkeypatch):
    async def fake_ask(question, org, user, mcp_client, session_id=None):
        return {"question": question, "org": org, "user": user, "answer": "ok", "citations": []}
    monkeypatch.setattr(api, "navigator_ask", fake_ask)
    monkeypatch.setattr(api, "limiter", RateLimiter(per_minute=2, per_day=10))
    body = {"org": "im-amrith", "user": "ratelimit-test", "question": "Who owns analytics?"}
    assert client.post("/ask", json={**body, "user": "bad name"}).status_code == 422
    assert client.post("/ask", json=body).json()["org"] == "im-Amrith"  # org matched case-insensitively
    assert client.post("/ask", json=body).status_code == 200
    r = client.post("/ask", json=body)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
