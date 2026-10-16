"""Decision extraction and topic tagging (PLAN.md pipeline steps 6-7, milestone M5).

Candidates come from the graph (queries/20_extract_*): merged PRs with a real description,
closed issues with a long human thread, and docs/ADRs. Each candidate becomes one prompt
built only from human-written text: bot comments are dropped by the queries, and bot
blocks inside PR bodies (CodeRabbit summaries, cubic and Copilot sections, benchmark
tables, review-stack links) are stripped here, since they describe what changed, not why.

The LLM (role "fast") returns 0-3 decisions plus 1-3 topics for the candidate. Its choices
are fenced by a per-candidate JSON schema: affected modules come only from the candidate's
own modules, proposed_by only from its author, approved_by only from its approving
reviewers, topics only from the org's fixed list. Everything is checked again in Python
(validate()), because not every endpoint enforces the schema strictly.

Anti-invention check: the quote must appear in the text we sent (whitespace and markdown
ignored, 80% of its words in one run). If it doesn't, confidence is capped at 0.5, which
keeps the decision out of answers (DECISION_MIN_CONFIDENCE = 0.6) but in the graph for review.
"""

from __future__ import annotations

import difflib
import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from falkordb import Graph

from lore.config import (
    EXTRACT_MAX_INPUT_CHARS,
    EXTRACT_MAX_MODULES,
    EXTRACT_MIN_ISSUE_COMMENTS,
    EXTRACT_MIN_PR_BODY,
    EXTRACT_MUST_INCLUDE,
    Topic,
    topics_for,
)
from lore.graph import query, ro_query
from lore.llm import chat_json
from lore.llm.chat import role_config

MAX_DECISIONS = 3
MAX_QUOTE_WORDS = 30
UNVERIFIED_CONFIDENCE_CAP = 0.5
MAX_COMMENTS = 25  # most recent human comments per candidate, oldest first
MAX_COMMENT_CHARS = 1500
MAX_ISSUE_CHARS = 3000
MAX_LINKED_ISSUES = 3

# ---------------------------------------------------------------------------
# Bot blocks inside human-written bodies
# ---------------------------------------------------------------------------

# Start/end HTML-comment markers seen in FalkorDB PR bodies (counts from 598 merged PRs):
# CodeRabbit release notes (358), cubic descriptions (22), Copilot agent sections (21+12+10),
# benchmark tables (11), review-stack entries (5).
_BLOCK_START = re.compile(
    r"<!--\s*(?:This is an auto-generated|START COPILOT|Benchmark results auto generation start"
    r"|review_stack_entry_start)[^>]*-->", re.I)
_BLOCK_END = re.compile(
    r"<!--\s*(?:end of auto-generated|END COPILOT|Benchmark results auto generation end"
    r"|review_stack_entry_end)[^>]*-->", re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Unmarked CodeRabbit summary: from its heading to the next heading of the same or higher level.
_CODERABBIT_HEADING = re.compile(r"^#{1,6}\s*Summary by CodeRabbit.*?(?=^#{1,2}\s|\Z)", re.S | re.M | re.I)
_GENERATED_LINE = re.compile(r"^.*Generated with \[[^\]]+\]\([^)]*\).*$", re.M)


def strip_bot_blocks(text: str | None) -> str:
    """Remove auto-generated sections from a PR/issue body; keep everything a human wrote."""
    if not text:
        return ""
    out, pos = [], 0
    while (m := _BLOCK_START.search(text, pos)):
        out.append(text[pos:m.start()])
        end = _BLOCK_END.search(text, m.end())
        pos = end.end() if end else len(text)  # an unclosed block runs to the end
    out.append(text[pos:])
    text = "".join(out)
    text = _CODERABBIT_HEADING.sub("", text)
    text = _HTML_COMMENT.sub("", text)  # PR-template hints like <!-- Closes #N -->
    text = _GENERATED_LINE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    id: str
    kind: str  # pr | issue | doc
    url: str
    title: str
    body: str  # stripped of bot blocks
    author: str | None
    author_id: str | None
    approvers: list[str]
    modules: list[str]  # allowed affected modules, most-touched first, capped
    labels: list[str] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    number: int | None = None
    at: int | None = None  # when the decision took effect: merged / closed / doc updated
    status: str = "active"
    label: str = ""  # "PR #2349", "issue #12", "doc docs/adr/0001.md"


def rank_modules(modules: list[str], files: list[str] | None, cap: int = EXTRACT_MAX_MODULES) -> list[str]:
    """Distinct module ids, the ones holding most of the changed files first.

    A file belongs to the module whose path is its longest directory prefix ('/' for root
    files). PR #2279 replaced the whole tree, so without a cap its choice list is huge.
    """
    mods = list(dict.fromkeys(m for m in modules if m))
    if not files:
        return mods[:cap]
    paths = {m: m.split(":", 2)[2] for m in mods}
    counts = {m: 0 for m in mods}
    for f in files:
        best, best_len = None, -1
        for m, p in paths.items():
            if p == "/":
                if "/" not in f and best_len < 0:
                    best, best_len = m, 0
            elif (f == p or f.startswith(p + "/")) and len(p) > best_len:
                best, best_len = m, len(p)
        if best:
            counts[best] += 1
    return sorted(mods, key=lambda m: (-counts[m], m))[:cap]


def pick_issues(issues: list[dict], body: str, cap: int = MAX_LINKED_ISSUES) -> list[dict]:
    """Linked issues worth the prompt space: ones the PR closes first, then the ones its
    body mentions earliest ("Fix #2280" before a long "issues resolved" list).
    An issue can come back twice (CLOSES and REFERENCES rows); it counts as closed if either is."""
    def pos(i: dict) -> int:
        m = re.search(rf"#{i['number']}\b", body)
        return m.start() if m else len(body)
    uniq: dict[str, dict] = {}
    for i in issues:
        prev = uniq.get(i["id"])
        uniq[i["id"]] = {**i, "closes": bool(i.get("closes")) or bool(prev and prev.get("closes"))}
    return sorted(uniq.values(), key=lambda i: (not i["closes"], pos(i), i["number"]))[:cap]


def _row_to_candidate(r: dict, repo: str) -> Candidate:
    kind = r["kind"]
    body = strip_bot_blocks(r["body"]) if kind != "doc" else (r["body"] or "")
    if kind == "pr":
        merged = r["merged_at"] is not None
        status, at = ("active", r["merged_at"]) if merged else ("proposed", None)
        label = f"PR #{r['number']}" + ("" if merged else " (draft)" if r["is_draft"] else f" ({r['state']})")
        modules = rank_modules(r["modules"] or [], r["files"])
    elif kind == "issue":
        status, at, label = "active", r["closed_at"], f"issue #{r['number']}"
        modules = rank_modules(r["modules"] or [], None)
    else:
        status, at, label = "active", r["updated_at"], f"doc {r['path']}"
        modules = rank_modules(r["modules"] or [], None)
    comments = [c for c in r["comments"] if (c.get("body") or "").strip()]
    return Candidate(
        id=r["id"], kind=kind, url=r["url"], title=r["title"] or "", body=body,
        author=r["author"], author_id=r["author_id"], approvers=sorted(r["approvers"] or []),
        modules=modules, labels=r.get("labels") or [], comments=comments,
        issues=pick_issues(r.get("issues") or [], body), number=r.get("number"), at=at, status=status, label=label,
    )


def load_candidates(graph: Graph, repo: str, all_prs: bool = False) -> list[Candidate]:
    must = EXTRACT_MUST_INCLUDE.get(repo, [])
    params = {"repo": repo, "min_body": EXTRACT_MIN_PR_BODY, "must": must, "all": all_prs}
    out: list[Candidate] = []
    for r in ro_query(graph, "extract_pr_candidates", params):
        if r["author_is_bot"]:
            continue
        c = _row_to_candidate(r, repo)
        # The body filter is re-applied after stripping: a 2,000-char body that is all
        # CodeRabbit summary has no human description.
        if all_prs or c.number in must or len(c.body) > EXTRACT_MIN_PR_BODY:
            out.append(c)
    for r in ro_query(graph, "extract_issue_candidates", {"repo": repo, "min_comments": EXTRACT_MIN_ISSUE_COMMENTS}):
        if not r["author_is_bot"]:
            out.append(_row_to_candidate(r, repo))
    for r in ro_query(graph, "extract_doc_candidates", {"repo": repo}):
        out.append(_row_to_candidate(r, repo))
    return out


def sample(cands: list[Candidate], n: int, repo: str, seed: int = 42) -> list[Candidate]:
    """Must-include PRs first, then a seeded mix: ~70% PRs, ~20% issues, ~10% docs."""
    must = set(EXTRACT_MUST_INCLUDE.get(repo, []))
    first = [c for c in cands if c.kind == "pr" and c.number in must]
    rest = [c for c in cands if c not in first]
    rng = random.Random(seed)
    by_kind = {k: [c for c in rest if c.kind == k] for k in ("pr", "issue", "doc")}
    for v in by_kind.values():
        rng.shuffle(v)
    left = max(0, n - len(first))
    n_doc = min(len(by_kind["doc"]), max(1, left // 10))
    n_issue = min(len(by_kind["issue"]), max(1, left // 5))
    n_pr = left - n_doc - n_issue
    picked = first + by_kind["pr"][:n_pr] + by_kind["issue"][:n_issue] + by_kind["doc"][:n_doc]
    return picked[:n]


# ---------------------------------------------------------------------------
# Prompt and schema
# ---------------------------------------------------------------------------

SYSTEM = """You extract engineering decisions from ONE item of the GitHub repository {repo}: a pull request, a closed issue thread, or a design doc / ADR.

A decision is a deliberate choice the team made about how the software works or how they work: picking one design, approach, policy, tool or behaviour over others, or removing or replacing something. These are NOT decisions: plain bug fixes, refactors with no stated choice, dependency bumps, adding tests, typo fixes, release chores. Most items contain zero or one decision. Return an empty "decisions" list when there is none; never invent one to fill the list. At most {max_decisions}.

Record only what the text states.
- statement: one sentence saying what was decided, specific to this repo.
- rationale: the reasons the text gives, in your own words but nothing more. If the text says what was done but not why, use an empty string. Never add reasons from general knowledge (for example, do not write "because Rust is faster" unless the text says it).
- alternatives: options the text says were considered or rejected, each with its stated reason if one is given. Empty list if the text names none.
- affected_modules: only from the module ids listed with the item, and only the ones the decision is about, not every file touched. Empty list if none fit.
- proposed_by: the item's author, if they made or proposed the decision; otherwise empty.
- approved_by: only from the listed approving reviewers; empty if none are listed.
- quote: an exact passage copied from the item's text, under {max_quote} words, that states the decision or its reason. Copy it verbatim; do not paraphrase or join separate sentences.
- confidence: 0 to 1, how clearly the text states this as a decision. 0.9 or more: explicit ("we decided", "Decision:", an ADR, "instead of X we now Y because..."). 0.6 to 0.8: clearly described choice with some reasoning. Below 0.6: you are inferring.
- topics: 1 to 3 topic ids per decision, from the list below only. Also give 1 to 3 "topics" for the item as a whole.

Topics (id: what it covers; path and label hints):
{topics}"""


def topic_lines(topics: tuple[Topic, ...]) -> str:
    lines = []
    for t in topics:
        hints = "; ".join(h for h in (f"paths {t.paths}" if t.paths else "", f"labels {t.labels}" if t.labels else "") if h)
        lines.append(f"- {t.id}: {t.covers}" + (f" ({hints})" if hints else ""))
    return "\n".join(lines)


def _enum_array(values: list[str], max_items: int | None = None, min_items: int = 0) -> dict:
    if not values:
        return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    s: dict[str, Any] = {"type": "array", "items": {"type": "string", "enum": values}}
    if min_items:
        s["minItems"] = min_items
    if max_items:
        s["maxItems"] = max_items
    return s


def schema_for(c: Candidate, topic_ids: list[str]) -> dict:
    decision = {
        "type": "object",
        "properties": {
            "statement": {"type": "string"},
            "rationale": {"type": "string"},
            "alternatives": {"type": "array", "items": {"type": "string"}},
            "affected_modules": _enum_array(c.modules),
            "proposed_by": _enum_array([c.author] if c.author else []),
            "approved_by": _enum_array(c.approvers),
            "quote": {"type": "string"},
            "confidence": {"type": "number"},
            "topics": _enum_array(topic_ids, max_items=3, min_items=1),
        },
        "required": ["statement", "rationale", "alternatives", "affected_modules", "proposed_by",
                     "approved_by", "quote", "confidence", "topics"],
    }
    return {
        "type": "object",
        "properties": {
            "topics": _enum_array(topic_ids, max_items=3, min_items=1),
            "decisions": {"type": "array", "items": decision, "maxItems": MAX_DECISIONS},
        },
        "required": ["topics", "decisions"],
    }


def _day(ts: int | None) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else "-"


def source_text(c: Candidate) -> str:
    """The item as the LLM sees it. Also the text quotes are verified against."""
    head = [f"Item: {c.label}" + (f" by {c.author}" if c.author else ""),
            f"URL: {c.url}", f"Title: {c.title}"]
    if c.kind == "pr":
        head.append(f"Merged: {_day(c.at)}" if c.at else "Not merged (open or draft): a proposal")
    if c.labels:
        head.append("Labels: " + ", ".join(c.labels))
    head.append("Approving reviewers: " + (", ".join(c.approvers) if c.approvers else "none"))
    head.append("Module ids (choose affected_modules from these): " + (", ".join(c.modules) or "none"))
    parts = ["\n".join(head), "## Text\n" + (c.body or "(empty)")]
    for i in c.issues:
        parts.append(f"## Linked issue #{i['number']}: {i['title']}\n{strip_bot_blocks(i['body'])[:MAX_ISSUE_CHARS]}")
    if c.comments:
        cs = c.comments[-MAX_COMMENTS:]
        parts.append("## Comments (human only, oldest first)\n" + "\n\n".join(
            f"- {cm['author'] or 'unknown'} ({_day(cm['at'])}): {strip_bot_blocks(cm['body'])[:MAX_COMMENT_CHARS]}"
            for cm in cs))
    text = "\n\n".join(parts)
    if len(text) > EXTRACT_MAX_INPUT_CHARS:
        text = text[:EXTRACT_MAX_INPUT_CHARS] + "\n[...truncated]"
    return text


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+(?:['.][a-z0-9]+)*")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def quote_match(quote: str, text: str) -> float:
    """Share of the quote's words found as one contiguous run in the text (0-1).

    Word-level, so markdown (`code`, **bold**), punctuation and line breaks don't matter.
    """
    q, t = _words(quote), _words(text)
    if not q:
        return 0.0
    m = difflib.SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
    return m.size / len(q)


def decision_id(source_id: str, statement: str) -> str:
    h = hashlib.sha1(f"{source_id}|{' '.join(_words(statement))}".encode("utf-8")).hexdigest()[:16]
    return f"decision:{h}"


def validate(raw: dict, c: Candidate, text: str, topic_ids: list[str], model: str) -> tuple[list[str], list[dict]]:
    """Clamp the LLM output to the candidate's allowed values. Returns (item topics, decisions)."""
    allowed_topics = set(topic_ids)
    item_topics = [t for t in dict.fromkeys(raw.get("topics") or []) if t in allowed_topics][:3]
    out = []
    for d in (raw.get("decisions") or [])[:MAX_DECISIONS]:
        statement = (d.get("statement") or "").strip()
        if not statement:
            continue
        quote = " ".join((d.get("quote") or "").split())
        words = quote.split()
        if len(words) > MAX_QUOTE_WORDS:
            quote = " ".join(words[:MAX_QUOTE_WORDS]) + " ..."
        match = quote_match(quote.removesuffix(" ..."), text)
        verified = match >= 0.8
        llm_conf = max(0.0, min(1.0, float(d.get("confidence") or 0)))
        out.append({
            "id": decision_id(c.id, statement),
            "statement": statement,
            "rationale": (d.get("rationale") or "").strip(),
            "alternatives": [a.strip() for a in d.get("alternatives") or [] if a and a.strip()],
            "affected_modules": [m for m in dict.fromkeys(d.get("affected_modules") or []) if m in c.modules],
            "proposed_by": [p for p in d.get("proposed_by") or [] if p == c.author][:1],
            "approved_by": [p for p in dict.fromkeys(d.get("approved_by") or []) if p in c.approvers],
            "quote": quote,
            "quote_match": round(match, 2),
            "quote_verified": verified,
            "llm_confidence": llm_conf,
            "confidence": llm_conf if verified else min(llm_conf, UNVERIFIED_CONFIDENCE_CAP),
            "topics": [t for t in dict.fromkeys(d.get("topics") or []) if t in allowed_topics][:3],
            "status": c.status, "valid_from": c.at, "source_id": c.id, "source_url": c.url,
            "model": model,
        })
    return item_topics, out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

@dataclass
class Extraction:
    candidate: Candidate
    topics: list[str]
    decisions: list[dict]
    error: str | None = None


def extract(cands: list[Candidate], repo: str, org: str,
            log: Callable[[str], None] = print) -> list[Extraction]:
    topics = topics_for(org)
    topic_ids = [t.id for t in topics]
    system = SYSTEM.format(repo=repo, max_decisions=MAX_DECISIONS, max_quote=MAX_QUOTE_WORDS,
                           topics=topic_lines(topics))
    model = role_config("fast")[2]
    results = []
    for n, c in enumerate(cands, 1):
        text = source_text(c)
        t0 = time.perf_counter()
        try:
            raw = chat_json("fast", system, text, schema_for(c, topic_ids), "decisions")
            item_topics, decisions = validate(raw, c, text, topic_ids, model)
            results.append(Extraction(c, item_topics, decisions))
            log(f"  [{n}/{len(cands)}] {c.label}: {len(decisions)} decision(s) ({time.perf_counter() - t0:.1f}s)")
        except Exception as e:  # keep going; the failure is reported and nothing is loaded for it
            results.append(Extraction(c, [], [], error=f"{type(e).__name__}: {e}"))
            log(f"  [{n}/{len(cands)}] {c.label}: ERROR {type(e).__name__}: {e}")
            if type(e).__name__ == "CallCapExceeded":
                break
    return results


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

BATCH = 500


def _batched(graph: Graph, name: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        query(graph, name, {"rows": rows[i:i + BATCH]})


def load_extractions(graph: Graph, results: list[Extraction], org: str,
                     log: Callable[[str], None] = print) -> None:
    now = int(time.time())
    ok = [r for r in results if r.error is None]
    _batched(graph, "load_topics", [{"name": t.id, "covers": t.covers} for t in topics_for(org)])
    _batched(graph, "load_decisions_reset",
             [{"source_id": r.candidate.id, "keep": [d["id"] for d in r.decisions]} for r in ok])
    decisions, affects, proposed, approved, about = [], [], [], [], []
    for r in ok:
        c = r.candidate
        about += [{"src_id": c.id, "topic": t, "at": c.at} for t in r.topics]
        for d in r.decisions:
            decisions.append({**{k: d[k] for k in ("id", "statement", "rationale", "alternatives", "status",
                                                   "valid_from", "confidence", "llm_confidence", "quote",
                                                   "quote_verified", "source_id", "source_url", "model")},
                              "extracted_at": now})
            affects += [{"decision_id": d["id"], "module_id": m, "at": c.at} for m in d["affected_modules"]]
            if d["proposed_by"] and c.author_id:
                proposed.append({"decision_id": d["id"], "person_id": c.author_id, "at": c.at})
            approved += [{"decision_id": d["id"], "person_id": f"person:{p}", "at": c.at} for p in d["approved_by"]]
            about += [{"src_id": d["id"], "topic": t, "at": c.at} for t in d["topics"]]
    for name, rows in (("load_decisions", decisions), ("load_affects", affects), ("load_proposed", proposed),
                       ("load_approved", approved), ("load_about", about)):
        _batched(graph, name, rows)
        log(f"  {name}: {len(rows)} rows")
