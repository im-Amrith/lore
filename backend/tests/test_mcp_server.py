"""lore-mcp over MCP: list the tools and call trace_decision and find_experts from a client.

The stdio test starts the server as a subprocess (python -m lore.mcp_server), exactly as an
agent or Claude Desktop would; the in-process test checks that a refusal reaches the client
with its reason."""

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from lore.config import get_settings, graph_name

BACKEND = Path(__file__).resolve().parent.parent
TOOLS = {"find_entities", "trace_decision", "find_experts", "module_owners", "knowledge_risk",
         "related_work", "impact_radius", "recall", "remember", "post_triage", "data_version"}


def _graphs() -> list[str]:
    try:
        from lore.graph.client import get_db
        return get_db().list_graphs()
    except Exception:
        return []


GRAPHS = _graphs()
needs_graphs = pytest.mark.skipif(
    not {graph_name("FalkorDB"), graph_name("im-Amrith")} <= set(GRAPHS), reason="graphs not loaded")


@needs_graphs
def test_stdio_client_lists_tools_and_calls_trace_and_experts():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "lore.mcp_server"], cwd=str(BACKEND),
        env={**os.environ, "PYTHONPATH": str(BACKEND)})

    async def run():
        async with Client(params) as client:
            listed = await client.list_tools()
            assert {x.name for x in listed.tools} == TOOLS
            assert all("org" in x.input_schema["properties"] for x in listed.tools)

            r = await client.call_tool("trace_decision", {"org": "FalkorDB", "node_id": "pr:FalkorDB/FalkorDB#2678"})
            assert not r.is_error
            env = r.structured_content
            [d] = env["results"]["decisions"]
            assert "all_nodes_matrix" in d["statement"]
            assert env["cypher"][0]["query"] == "trace_decision"
            assert env["sources"]["pr:FalkorDB/FalkorDB#2678"] == "https://github.com/FalkorDB/FalkorDB/pull/2678"

            r = await client.call_tool("find_experts", {"org": "FalkorDB", "module_or_topic": "graph/src/index"})
            assert not r.is_error
            experts = r.structured_content["results"]["experts"]
            assert [e["person"] for e in experts[:2]] == ["DvirDukhan", "AviAvni"]

            r = await client.call_tool("trace_decision", {"org": "im-Amrith", "node_id": "pr:im-Amrith/lore-sandbox#11"})
            pending = r.structured_content["results"]["pending_proposals"]
            assert [p["source_id"] for p in pending] == ["pr:im-Amrith/lore-sandbox#16"]

    anyio.run(run)


@needs_graphs
def test_refusal_reaches_the_client_with_its_reason(monkeypatch):
    from lore.mcp_server.server import mcp
    monkeypatch.setattr(get_settings(), "sandbox_repo", "im-Amrith/lore-sandbox")

    async def run():
        async with Client(mcp) as client:
            r = await client.call_tool("post_triage", {"org": "FalkorDB", "issue_id": "issue:FalkorDB/FalkorDB#2677",
                                                       "draft": "dup of #1", "approval_token": "x"})
            assert r.is_error
            assert "not the sandbox repo" in r.content[0].text

    anyio.run(run)
