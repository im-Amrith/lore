"""Deterministic grounding of the Navigator's answer, after the LLM has written it.

The LLM decides what to say; code makes sure what it says is tied to the graph:
  - why_lead: a "why" answer opens with the traced decision's statement, verbatim, cited to the
    decision, the source it was DECIDED_IN and the issues that source CLOSES (the walked path)
  - attach_mentions: a sentence that names a person, a module path, a PR or issue number or
    CODEOWNERS that this question's tool results returned gets that node id as a citation; in a
    who/owns answer a person also gets their top evidence PR on the module, and an owner sentence
    always cites CODEOWNERS
  - module_first: a who/owns answer names the exact module path in its first sentence
Nothing here invents a node: every id it adds is one a tool returned for this question.
"""

import re
from typing import Any

PERSON_INTENTS = ("who-knows", "owns")
MODULE_INTENTS = ("who-knows", "owns", "risk", "impact")
_OWNER_WORDS = re.compile(r"\b(owns?|owned|owners?|codeowners|listed)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().rstrip(".")


def _results_of(results: list[tuple[str, dict[str, Any]]], tool: str) -> list[dict[str, Any]]:
    return [r for t, r in results if t == tool and isinstance(r, dict)]


def why_lead(results: list[tuple[str, dict[str, Any]]], known: set[str]) -> dict[str, Any] | None:
    """The opening sentence of a why answer: the first active decision trace_decision returned."""
    for r in _results_of(results, "trace_decision"):
        for d in r.get("decisions") or []:
            if d.get("status") != "active" or not d.get("statement") or d.get("id") not in known:
                continue
            cites = [d["id"]] + [s["id"] for s in d.get("sources") or [] if s.get("id") in known]
            cites += [i["id"] for i in d.get("issues") or [] if "CLOSES" in (i.get("rels") or []) and i.get("id") in known]
            text = d["statement"].strip()
            return {"text": text if text.endswith((".", "!", "?")) else text + ".", "cites": list(dict.fromkeys(cites))}
    return None


def add_lead(sentences: list[dict[str, Any]], lead: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Put the lead first; drop an LLM sentence that only repeats it."""
    if not lead:
        return sentences
    return [lead] + [s for s in sentences if _norm(s["text"]) != _norm(lead["text"])]


def subject_module(results: list[tuple[str, dict[str, Any]]]) -> dict[str, str] | None:
    """The module a who/owns answer is about: module_owners' module, else find_experts' subject."""
    for r in _results_of(results, "module_owners"):
        m = r.get("module")
        if isinstance(m, dict) and m.get("id") and m.get("path"):
            return {"id": m["id"], "path": m["path"]}
    for r in _results_of(results, "find_experts"):
        s = r.get("subject")
        if isinstance(s, dict) and s.get("kind") == "module" and s.get("id") and s.get("path"):
            return {"id": s["id"], "path": s["path"]}
    return None


def module_first(sentences: list[dict[str, Any]], module: dict[str, str] | None, known: set[str]) -> list[dict[str, Any]]:
    """Make sure the first sentence names the module path; prepend it when the LLM didn't."""
    if not sentences or not module or module["path"] == "/":
        return sentences
    first = dict(sentences[0])
    if not _mentions_path(first["text"], module["path"]):
        first["text"] = f"On {module['path']}: {first['text'][:1].lower()}{first['text'][1:]}"
    if module["id"] in known and module["id"] not in first["cites"]:
        first["cites"] = first["cites"] + [module["id"]]
    return [first] + sentences[1:]


def _mentions_path(text: str, path: str) -> bool:
    return re.search(rf"(?<![\w/]){re.escape(path)}(?![\w/])", text) is not None


def _name_pattern(name: str) -> re.Pattern | None:
    """'AviAvni' or 'Avi Avni' -> a pattern matching either spelling (spaces, '-' and '_' optional)."""
    letters = [c for c in name if c.isalnum()]
    if len(letters) < 3:
        return None
    return re.compile(r"(?<![\w])" + r"[\s_-]?".join(re.escape(c) for c in letters) + r"(?![\w])", re.I)


def _evidence_prs(results: list[tuple[str, dict[str, Any]]], url_to_id) -> dict[str, list[str]]:
    """person id -> their evidence PR ids on the module, best first (find_experts, then module_owners)."""
    out: dict[str, list[str]] = {}
    for r in _results_of(results, "find_experts"):
        for e in r.get("experts") or []:
            pid = e.get("person_id")
            if pid:
                out.setdefault(pid, []).extend(url_to_id(u) for u in e.get("evidence") or [])
    for r in _results_of(results, "module_owners"):
        for e in r.get("active_experts") or []:
            if e.get("id"):
                out.setdefault(e["id"], []).extend(url_to_id(u) for u in e.get("evidence") or [])
    return out


def attach_mentions(sentences: list[dict[str, Any]], intent: str, results: list[tuple[str, dict[str, Any]]],
                    known: set[str], labels: dict[str, str], url_to_id) -> list[dict[str, Any]]:
    """Add the citation for every graph node a sentence names. Only ids in `known` are added."""
    people: list[tuple[str, re.Pattern]] = []
    modules: list[tuple[str, str]] = []
    numbered: dict[str, list[str]] = {}  # "123" -> PR / issue ids with that number
    for nid in known:
        kind = nid.split(":", 1)[0]
        if kind == "person":
            names = {nid.removeprefix("person:name:").removeprefix("person:"), labels.get(nid, "")}
            people += [(nid, p) for n in names if n and (p := _name_pattern(n))]
        elif kind == "module":
            path = nid.split(":", 2)[2] if nid.count(":") >= 2 else ""
            # One-segment paths (graph, docs, cache) are ordinary words in prose; match them only
            # in answers that are about modules.
            if path and path != "/" and ("/" in path or intent in MODULE_INTENTS):
                modules.append((nid, path))
        elif kind in ("pr", "issue") and (m := re.search(r"#(\d+)$", nid)):
            numbered.setdefault(m.group(1), []).append(nid)
    evidence = _evidence_prs(results, url_to_id) if intent in PERSON_INTENTS else {}

    out = []
    for s in sentences:
        text = s["text"]
        found: list[tuple[int, list[str]]] = []  # (position in the text, ids), so cites follow the text
        for pid, pat in people:
            if m := pat.search(text):
                found.append((m.start(), [pid] + [p for p in evidence.get(pid, [])[:1] if p in known]))
        for mid, path in modules:
            if m := re.search(rf"(?<![\w/]){re.escape(path)}(?![\w/])", text):
                found.append((m.start(), [mid]))
        for m in re.finditer(r"(?:\b(PR|pull request|issue)\s*)?#(\d+)\b", text, re.I):
            kind = (m.group(1) or "").lower()
            found.append((m.start(), [nid for nid in sorted(numbered.get(m.group(2), []))
                                      if not kind or (kind == "issue") == nid.startswith("issue:")]))
        if "codeowners" in known and (m := re.search(r"codeowners", text, re.I)
                                      or (intent == "owns" and _OWNER_WORDS.search(text))):
            found.append((m.start(), ["codeowners"]))
        added = [nid for _, ids in sorted(found, key=lambda f: f[0]) for nid in ids]
        out.append({**s, "cites": list(dict.fromkeys(list(s["cites"]) + added))})
    return out
