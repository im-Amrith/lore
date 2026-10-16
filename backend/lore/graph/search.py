"""Entry points into the graph (query 2) and similar issues (query 9).

find_start(): decisions first (vector + full-text fused by RRF, weighted by kind), then doc
chunks, PRs and issues as fallback starting nodes. The vector search only picks where a
traversal starts; the answer itself comes from the Cypher that follows.
"""

from __future__ import annotations

import re
from typing import Any

from falkordb import Graph

from lore.config import (
    DECISION_MIN_CONFIDENCE,
    ENTRY_CANDIDATES,
    ENTRY_TEXT_CANDIDATES,
    RRF_K,
    RRF_TEXT_WEIGHT,
)
from lore.graph.client import ro_query
from lore.ingest.embed import issue_text
from lore.llm import embed

# BGE v1.5's instruction for short queries against longer passages.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Empty full-text query: no node contains this token, so the full-text list is empty and the
# fusion falls back to the vector ranks alone.
NO_TEXT = "__no_specific_terms__"


def fulltext_query(text: str) -> str:
    """Keep only a question's specific terms for full-text, joined with | (OR).

    Meaning is the vector's job; full-text is there for exact identifiers the embedding may
    blur. A term is specific when it is an identifier (inner '.', '-', '/' or '_', or letters
    with digits) or an acronym (MVCC, TTL). Plain words, even names like "Rust", match most of
    a project's decisions and drown the right one (measured: "rust|all_nodes_matrix" drops
    PR 2678's decision out of the full-text top 3; "all_nodes_matrix" alone finds only it).
    The tokenizer splits on '.', '-' and '/' but not '_', so graphblas.sh becomes the phrase
    "graphblas sh" and all_nodes_matrix stays one term. Returns NO_TEXT when nothing is left.
    """
    terms: list[str] = []
    for raw in text.split():
        word = raw.strip(".,;:!?()[]{}'\"`")
        if not word:
            continue
        acronym = len(word) >= 2 and word.isalpha() and word.isupper()
        identifier = bool(re.search(r"\w[._/-]\w", word)) or bool(re.search(r"[a-zA-Z]\d|\d[a-zA-Z]", word))
        if not (acronym or identifier):
            continue
        parts = [p for p in re.split(r"[^a-z0-9_]+", word.lower()) if p]
        term = parts[0] if len(parts) == 1 else '"' + " ".join(parts) + '"'
        if term not in terms:
            terms.append(term)
    return "|".join(terms) or NO_TEXT


# Question words and glue left out of keyword_query.
STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does doing for from had has have how i if in
into is it its me my no not now of on or our should so than that the their them then there these
they this those to us was we were what when where which who whom why will with would you your
""".split())


def keyword_query(text: str) -> str:
    """Every non-stopword of a question, joined with | (OR), for the PR fallback: PRs have no
    embedding, so full-text is all they have. A raw question would be an AND of every word
    (and '-' means NOT), which matches nothing."""
    terms: list[str] = []
    for word in re.split(r"[^a-z0-9_]+", text.lower()):
        if len(word) >= 2 and word not in STOPWORDS and word not in terms:
            terms.append(word)
    return "|".join(terms) or NO_TEXT


def embed_query(text: str) -> list[float]:
    return embed([QUERY_PREFIX + text])[0]


def find_decisions(graph: Graph, question: str, limit: int = 5, vec: list[float] | None = None,
                   ro=ro_query) -> list[dict[str, Any]]:
    q_text = fulltext_query(question)
    return ro(graph, "entry_decisions", {
        "q_text": q_text, "q_vec": vec or embed_query(question), "k": ENTRY_CANDIDATES,
        "text_k": ENTRY_TEXT_CANDIDATES, "text_weight": RRF_TEXT_WEIGHT, "rrf_k": RRF_K,
        "min_confidence": DECISION_MIN_CONFIDENCE, "limit": limit,
    })


def find_start(graph: Graph, question: str, limit: int = 5, ro=ro_query,
               kinds: tuple[str, ...] = ("decisions", "docs", "prs", "issues")) -> dict[str, list[dict[str, Any]]]:
    """Candidate starting nodes for a question, in the order they should be tried.
    `ro` runs each named query (lore-mcp passes one that records the Cypher); `kinds` limits
    which entry queries run."""
    vec = embed_query(question)
    out: dict[str, list[dict[str, Any]]] = {}
    if "decisions" in kinds:
        out["decisions"] = find_decisions(graph, question, limit, vec, ro=ro)
    if "docs" in kinds:
        out["docs"] = ro(graph, "entry_docs", {"q_vec": vec, "k": limit * 2, "limit": limit})
    if "prs" in kinds:
        out["prs"] = ro(graph, "entry_prs", {"q_text": keyword_query(question), "limit": limit})
    if "issues" in kinds:
        out["issues"] = ro(graph, "entry_issues", {"q_vec": vec, "k": limit, "limit": limit})
    return out


def similar_issues(graph: Graph, title: str, body: str = "", issue_id: str | None = None,
                   limit: int = 5, max_distance: float = 0.5, ro=ro_query) -> list[dict[str, Any]]:
    """Query 9: issues nearest to a (new) issue, with the PRs that closed them and the modules
    those PRs touched. The issue is embedded exactly like stored issues (no query prefix)."""
    vec = embed([issue_text(title, body)])[0]
    return ro(graph, "similar_issues", {
        "issue_vec": vec, "issue_id": issue_id, "k": limit + 1, "max_distance": max_distance, "limit": limit,
    })
