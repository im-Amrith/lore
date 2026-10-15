"""FalkorDB connection and thin query wrappers.

Queries are always referenced by name (see queries.py) and always take
parameters; user input is never formatted into Cypher.
"""

from functools import lru_cache
from typing import Any

from falkordb import FalkorDB, Graph

from lore.config import get_settings, graph_name
from lore.graph.queries import load_query


@lru_cache
def get_db() -> FalkorDB:
    s = get_settings()
    return FalkorDB(
        host=s.falkordb_host,
        port=s.falkordb_port,
        password=s.falkordb_password or None,
    )


def get_graph(org: str | None = None, *, name: str | None = None) -> Graph:
    """Select the graph for an org (lore_<org>), or a graph by explicit name."""
    if name is None:
        name = graph_name(org or get_settings().demo_org)
    return get_db().select_graph(name)


def _rows(result) -> list[dict[str, Any]]:
    cols = [h[1] if isinstance(h, (list, tuple)) else h for h in result.header]
    return [dict(zip(cols, row)) for row in result.result_set]


def query(graph: Graph, name: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a named query with write access (loaders, derive jobs, memory, sync)."""
    return _rows(graph.query(load_query(name), params or {}))


def ro_query(graph: Graph, name: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a named query read-only. Use this for everything that doesn't write."""
    return _rows(graph.ro_query(load_query(name), params or {}))
