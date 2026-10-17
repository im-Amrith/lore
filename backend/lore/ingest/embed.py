"""Cut docs into DocChunk nodes and store embeddings on Decision, Issue and DocChunk (M6).

What gets embedded (one model everywhere, see lore/llm/embed.py):
  Decision  statement + rationale + quote: the rationale so "why" questions match the
            reasoning, the verified quote so they match the source's own words (q03 "two
            branches" is only in the PR's words; it went from vector rank 10 to 2)
  Issue     title + the first ISSUE_EMBED_BODY chars of the body
  DocChunk  the doc's title or path + the chunk text

Embeddings are cached per text on disk, so a re-run only computes texts that changed;
every vector is written again (cheap) so the graph always matches the current texts.
"""

from __future__ import annotations

import re
from typing import Callable

from falkordb import Graph

from lore.config import DOC_CHUNK_CHARS, DOC_CHUNK_OVERLAP, ISSUE_EMBED_BODY
from lore.graph import query, ro_query
from lore.llm import embed

BATCH = 500


def chunk_text(text: str, size: int = DOC_CHUNK_CHARS, overlap: int = DOC_CHUNK_OVERLAP) -> list[str]:
    """Cut text into chunks of at most `size` chars; each starts `overlap` chars before the
    previous one ended. Cuts prefer a paragraph break, then a line break, then a space, in the
    last third of the window, so chunks rarely split a sentence mid-word."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while True:
        end = start + size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        window = text[start:end]
        cut = -1
        for sep in ("\n\n", "\n", " "):
            cut = window.rfind(sep, size * 2 // 3)
            if cut != -1:
                break
        end = start + cut if cut != -1 else end
        chunks.append(text[start:end].strip())
        nxt = end - overlap
        # Start the overlap on a word boundary.
        space = text.find(" ", nxt, end)
        start = space + 1 if space != -1 else nxt
    return [c for c in chunks if c]


def chunk_id(doc_id: str, n: int) -> str:
    """doc:<owner>/<repo>:<path> -> chunk:<owner>/<repo>:<path>#<n>"""
    return f"chunk:{doc_id.removeprefix('doc:')}#{n}"


def decision_text(statement: str, rationale: str | None, quote: str | None = None) -> str:
    return "\n".join(t for t in (statement, rationale, quote) if t)


def issue_text(title: str, body: str | None) -> str:
    # Drop HTML comments (issue templates) and collapse whitespace before cutting.
    body = re.sub(r"<!--.*?-->", " ", body or "", flags=re.S)
    body = re.sub(r"\s+", " ", body).strip()[:ISSUE_EMBED_BODY]
    return f"{title}\n{body}" if body else title


def load_chunks(graph: Graph, repo: str | None = None, log: Callable[[str], None] = print) -> int:
    rows, resets = [], []
    for d in ro_query(graph, "embed_docs", {"repo": repo}):
        parts = chunk_text(d["text"])
        rows += [{"id": chunk_id(d["id"], n), "doc_id": d["id"], "n": n, "text": t} for n, t in enumerate(parts)]
        resets.append({"doc_id": d["id"], "chunks": len(parts)})
    query(graph, "load_doc_chunks_reset", {"rows": resets})
    for start in range(0, len(rows), BATCH):
        query(graph, "load_doc_chunks", {"rows": rows[start:start + BATCH]})
    log(f"  doc chunks: {len(rows)} from {len(resets)} docs")
    return len(rows)


def _store(graph: Graph, setter: str, ids: list[str], texts: list[str]) -> None:
    vecs = embed(texts)
    rows = [{"id": i, "vec": v} for i, v in zip(ids, vecs)]
    for start in range(0, len(rows), BATCH):
        query(graph, setter, {"rows": rows[start:start + BATCH]})


def embed_graph(graph: Graph, repo: str | None = None, log: Callable[[str], None] = print,
                missing_only: bool = False, doc_ids: list[str] | None = None) -> dict[str, int]:
    """Chunk docs, then embed every Decision, Issue and DocChunk in the graph. A sync (M15) passes
    missing_only (decisions and issues without an embedding) and doc_ids (the docs it changed)."""
    load_chunks(graph, repo, log)
    counts = {}
    dec = ro_query(graph, "embed_decision_texts", {"missing": missing_only})
    _store(graph, "embed_set_decisions", [r["id"] for r in dec],
           [decision_text(r["statement"], r["rationale"], r["quote"]) for r in dec])
    counts["Decision"] = len(dec)
    iss = ro_query(graph, "embed_issue_texts", {"missing": missing_only})
    _store(graph, "embed_set_issues", [r["id"] for r in iss], [issue_text(r["title"], r["body"]) for r in iss])
    counts["Issue"] = len(iss)
    ch = ro_query(graph, "embed_chunk_texts", {"doc_ids": doc_ids if missing_only else None})
    _store(graph, "embed_set_chunks", [r["id"] for r in ch], [f"{r['doc']}\n{r['text']}" for r in ch])
    counts["DocChunk"] = len(ch)
    for label, n in counts.items():
        log(f"  embedded {label}: {n}")
    return counts
