"""Load normalised rows into a FalkorDB graph with the queries/01_load_*.cypher files."""

from __future__ import annotations

from typing import Callable

from falkordb import Graph

from lore.config import get_settings
from lore.graph import load_query, query
from lore.ingest.normalize import Rows

BATCH = 500

# Order matters: nodes first, then the edges that MATCH them.
STEPS: list[tuple[str, str]] = [
    ("repos", "load_repos"),
    ("persons", "load_persons"),
    ("teams", "load_teams"),
    ("modules", "load_modules"),
    ("prs", "load_prs"),
    ("issues", "load_issues"),
    ("commits", "load_commits"),
    ("touches", "load_touches"),
    ("commits", "load_part_of_reset"),
    ("part_of", "load_part_of"),
    ("reviews", "load_reviews"),
    ("closes", "load_closes"),
    ("comments", "load_comments"),
    ("docs", "load_docs"),
    ("releases", "load_releases"),
    ("owns", "load_owns"),
    ("references", "load_references"),
]


def create_indexes(graph: Graph, log: Callable[[str], None] = print) -> None:
    created = 0
    code = "\n".join(l for l in load_query("load_indexes").splitlines() if not l.strip().startswith("//"))
    for stmt in (s.strip() for s in code.split(";")):
        if not stmt:
            continue
        try:
            graph.query(stmt, {"dim": get_settings().embedding_dim})
            created += 1
        except Exception as e:  # FalkorDB raises on an index that already exists
            if "already indexed" not in str(e).lower() and "already exists" not in str(e).lower():
                raise
    log(f"  indexes: {created} created (others existed)")


def load_rows(graph: Graph, rows: Rows, log: Callable[[str], None] = print) -> None:
    create_indexes(graph, log)
    for attr, name in STEPS:
        items = getattr(rows, attr)
        for start in range(0, len(items), BATCH):
            query(graph, name, {"rows": items[start:start + BATCH]})
        log(f"  {name}: {len(items)} rows")
