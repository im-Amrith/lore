"""M15 sync: the supersession judge and the webhook routing (the graph side is checked by running it)."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from lore.api import app as api
from lore.ingest import sync

OLD = [{"id": "decision:old1", "statement": "Use a shared Redis cache"},
       {"id": "decision:old2", "statement": "Short codes are 7 base62 characters"}]
NEW = {"id": "decision:new", "statement": "Replace Redis with an in-process LRU"}


def _reply(content: str):
    return lambda *a, **k: {"content": content, "model": "test"}


def test_judge_keeps_only_listed_ids(monkeypatch):
    monkeypatch.setattr(sync, "agent_chat", _reply(json.dumps({"replaces": [
        {"id": "decision:old1", "reason": "reverses it"},
        {"id": "decision:made-up", "reason": "not a candidate"}]})))
    assert sync.judge("im-Amrith/lore-sandbox", NEW, OLD) == [{"id": "decision:old1", "reason": "reverses it"}]


def test_judge_unreadable_reply_replaces_nothing(monkeypatch):
    monkeypatch.setattr(sync, "agent_chat", _reply("sorry, no JSON"))
    assert sync.judge("im-Amrith/lore-sandbox", NEW, OLD) == []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api.settings, "github_webhook_secret", "hook-secret")
    monkeypatch.setattr(api.settings, "sandbox_repo", "im-Amrith/lore-sandbox")
    started = []
    monkeypatch.setattr(api, "_in_background", lambda coro: (started.append(coro), coro.close()))
    # No lifespan: the routes under test don't touch the MCP session or the graph.
    return TestClient(api.app), started


def _post(c, event: str, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    return c.post("/webhook/github", content=body,
                  headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig})


def test_merged_pr_starts_a_sync(client):
    c, started = client
    r = _post(c, "pull_request", {"action": "closed", "pull_request": {"number": 16, "merged": True},
                                  "repository": {"full_name": "im-Amrith/lore-sandbox"}})
    assert r.status_code == 202 and r.json()["pr"] == 16 and len(started) == 1


def test_closed_unmerged_pr_is_ignored(client):
    c, started = client
    r = _post(c, "pull_request", {"action": "closed", "pull_request": {"number": 16, "merged": False},
                                  "repository": {"full_name": "im-Amrith/lore-sandbox"}})
    assert r.json()["ignored"] == "pull_request closed" and not started


def test_merged_pr_in_another_repo_is_refused(client):
    c, started = client
    r = _post(c, "pull_request", {"action": "closed", "pull_request": {"number": 1, "merged": True},
                                  "repository": {"full_name": "FalkorDB/FalkorDB"}})
    assert r.status_code == 403 and not started
