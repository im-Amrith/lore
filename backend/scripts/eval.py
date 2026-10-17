"""Run the golden set through the Navigator and score it; write docs/eval_results.md.

    uv run --directory backend python scripts/eval.py              # questions that haven't passed yet
    uv run --directory backend python scripts/eval.py --only q06,q07  # just these
    uv run --directory backend python scripts/eval.py --all        # every question: q01-q10, s01-s03, n01
    (--no-cache: bypass the answer and LLM caches; --no-remember: no memory nodes; --pause 5: seconds
    between questions)

docs/eval_results.md is merged across runs: each row keeps the run it came from, so rerunning
only the failures leaves the passed rows (and their answers) in place.

Scoring is deterministic, no LLM judge. A question passes when:
  1. every must_cite URL is among the answer's citations (and, for must_cite_evidence, at least
     one cited PR is evidence of that person's work on that module: queries/92),
  2. every key fact appears in the answer text (or one of its ALIASES below),
  3. every sentence shown carries at least one citation a tool returned,
  4. for not-found tests (expect_not_found), the answer says not found / no reason recorded.
Matching ignores case, spaces and hyphens ("Avi Avni" = "AviAvni", "12-minute" = "12 minute"),
and treats blob/main and tree/main as blob/HEAD, tree/HEAD (the default branch).
For each miss the table also says whether the URL came back from any tool (retrieved but
not cited) or never did (data, extraction or entry point), to help sort failures by cause.
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anyio
import yaml
from mcp.client import Client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.agents.navigator import ask, server_params  # noqa: E402
from lore.config import REPO_ROOT, get_settings  # noqa: E402
from lore.graph.client import get_graph, ro_query  # noqa: E402

GOLDEN = REPO_ROOT / "docs" / "golden_set.yaml"
OUT = REPO_ROOT / "docs" / "eval_results.md"
EVAL_USER = "eval"

# Wordings that state the same key fact. Kept short and literal; each is a paraphrase a
# reviewer would accept as "mentions the fact".
ALIASES = {
    "nothing reads it": ["no longer exist", "no longer read", "nothing read", "no reader", "not read by", "unused"],
    "deletion": ["deleted", "delete"],
    "bus factor 1": ["bus factor of 1", "bus factor: 1", "single expert", "single-expert", "one active expert",
                     "only one expert", "single person", "one person"],
    "no owner listed": ["no owner is listed", "not listed", "no listed owner", "no owner in codeowners"],
    "12 minute": ["12 min"],
}
NOT_FOUND_PHRASES = ["not found", "no reason", "not recorded", "no recorded", "not given", "doesn't say",
                     "does not say", "not stated", "no rationale"]


def norm(s: str) -> str:
    return re.sub(r"[\s\-‐-―]+", "", (s or "").lower())


def norm_url(u: str) -> str:
    u = (u or "").strip().lower().rstrip("/")
    return u.replace("/blob/main/", "/blob/head/").replace("/tree/main/", "/tree/head/")


def has_fact(fact: str, text: str) -> bool:
    t = norm(text)
    return any(norm(f) in t for f in [fact, *ALIASES.get(fact, [])])


def cases(only: list[str] | None) -> list[dict]:
    g = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    sandbox_org = get_settings().sandbox_repo.split("/")[0] or "im-Amrith"
    out = [{**q, "org": q.get("org", "FalkorDB")} for q in g["questions"]]
    out += [{**q, "org": sandbox_org} for q in g["sandbox"]]
    out += [{**q, "org": "FalkorDB", "type": "not-found"} for q in g["spares"] if q.get("id")]
    return [c for c in out if not only or c["id"] in only]


def score(case: dict, r: dict) -> dict:
    cited_urls = {norm_url(c["url"]) for c in r["citations"] if c["url"]}
    retrieved = {norm_url(u) for u in r["sources"].values()}
    musts = case.get("must_cite") or []
    missing_cites = [u for u in musts if norm_url(u) not in cited_urls]
    if ev := case.get("must_cite_evidence"):
        urls = [c["url"] for c in r["citations"] if c["url"] and "/pull/" in c["url"]]
        hits = ro_query(get_graph(case["org"]), "check_evidence_prs", {**ev, "urls": urls})[0]["urls"] if urls else []
        musts = [*musts, f"any evidence PR of {' or '.join(ev['persons'])} on {ev['module']}"]
        if not hits:
            missing_cites.append(musts[-1])
    facts = case.get("key_facts") or []
    missing_facts = [f for f in facts if not has_fact(f, r["answer"])]
    uncited = [s["text"] for s in r["sentences"] if not s["cites"]]
    checks = {"cites": not missing_cites, "facts": not missing_facts, "all_cited": not uncited}
    if case.get("expect_not_found"):
        checks["not_found"] = (not r["found"]) or any(p in r["answer"].lower() for p in NOT_FOUND_PHRASES)
    return {
        "pass": all(checks.values()), "checks": checks,
        "missing_cites": [(u, norm_url(u) in retrieved) for u in missing_cites],
        "missing_facts": missing_facts, "cites_hit": len(musts) - len(missing_cites), "cites_total": len(musts),
        "facts_hit": len(facts) - len(missing_facts), "facts_total": len(facts),
    }


def llm_stats(r: dict) -> dict:
    calls = r.get("llm_calls") or []
    return {"calls": len(calls), "endpoints": sorted({c.get("endpoint") or c.get("model") or "?" for c in calls}),
            "max_prompt": max((c.get("prompt_tokens") or 0 for c in calls), default=0) or None,
            "fresh": bool(calls) and not r.get("answer_cache") and not any(c.get("cached") for c in calls)}


def timing_line(results: list[dict]) -> str:
    """Average answer time and LLM calls over answers made in this run with no cached LLM call."""
    fresh = [r for r in results if llm_stats(r)["fresh"]]
    if not fresh:
        return "Average answer time: n/a (no fresh answers in this run; cached answers are instant)."
    secs = sum(r["seconds"] for r in fresh) / len(fresh)
    calls = sum(llm_stats(r)["calls"] for r in fresh) / len(fresh)
    toks = [t for r in fresh if (t := llm_stats(r)["max_prompt"])]
    eps = sorted({e for r in fresh for e in llm_stats(r)["endpoints"]})
    return (f"Average answer time: {secs:.1f} s, {calls:.1f} LLM calls per question, over {len(fresh)} fresh "
            f"answers. Largest prompt: {max(toks) if toks else 'n/a'} tokens. Endpoints: {', '.join(eps)}.")


# ---------------------------------------------------------------- report (merged across runs)

COLUMNS = ["id", "type", "pass", "must_cite", "key facts", "tools", "llm calls", "endpoints", "secs",
           "max prompt tok", "dropped", "run", "notes"]


def read_report() -> tuple[dict[str, dict[str, str]], dict[str, str], str]:
    """The existing report: table rows and answer sections by id, and its run time (for old rows)."""
    if not OUT.exists():
        return {}, {}, ""
    text = OUT.read_text(encoding="utf-8")
    m = re.search(r"^Run (.+?) by", text, re.M)
    run = m.group(1) if m else ""
    rows, header = {}, None
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "id":
            header = cells
        elif header and not set(cells[0]) <= {"-", " "}:
            row = dict(zip(header, cells))
            row.setdefault("run", run)
            rows[cells[0]] = row
    sections = {}
    for chunk in re.split(r"^### ", text.split("## Answers", 1)[-1], flags=re.M)[1:]:
        sections[chunk.split(":", 1)[0].strip()] = "### " + chunk.rstrip() + "\n"
    return rows, sections, run


def new_row(case: dict, r: dict | None, s: dict | None, err: str | None, when: str) -> dict[str, str]:
    row = {"id": case["id"], "type": case.get("type", ""), "run": when}
    if err:
        return {**row, "pass": "ERROR", "notes": err[:160].replace("|", "/")}
    notes = []
    for u, got in s["missing_cites"]:
        what = u if u.startswith("any ") else u.rsplit("/", 1)[-1]
        notes.append(f"missing cite {what} ({'retrieved, not cited' if got else 'not cited' if what is u else 'never retrieved'})")
    if s["missing_facts"]:
        notes.append("missing facts: " + ", ".join(s["missing_facts"]))
    if "not_found" in s["checks"] and not s["checks"]["not_found"]:
        notes.append("did not say not found")
    st = llm_stats(r)
    return {**row, "pass": "PASS" if s["pass"] else "FAIL", "must_cite": f"{s['cites_hit']}/{s['cites_total']}",
            "key facts": f"{s['facts_hit']}/{s['facts_total']}", "tools": ", ".join(c["tool"] for c in r["tool_calls"]),
            "llm calls": "cache" if r.get("answer_cache") else str(st["calls"]), "endpoints": ", ".join(st["endpoints"]),
            "secs": str(r["seconds"]), "max prompt tok": str(st["max_prompt"] or ""), "dropped": str(len(r["dropped"])),
            "notes": "; ".join(notes)}


def new_section(case: dict, r: dict | None, s: dict | None, err: str | None, when: str) -> str:
    lines = [f"### {case['id']}: {case['question']}", ""]
    if err:
        return "\n".join(lines + [f"ERROR ({when}): {err}", ""]) + "\n"
    st = llm_stats(r)
    how = "answer cache" if r.get("answer_cache") else f"{st['calls']} LLM calls via " + ", ".join(st["endpoints"])
    lines += [f"**{'PASS' if s['pass'] else 'FAIL'}** · {when} · intent {r['intent']} · {how} · "
              f"tools: {', '.join(c['tool'] + ('(error)' if c['error'] else '') for c in r['tool_calls'])}", "",
              r["answer"], ""]
    lines += [f"- [{c['n']}] `{c['id']}` {c['url'] or ''}" for c in r["citations"]]
    if r["dropped"]:
        lines += ["", "Dropped (cited nothing a tool returned):"]
        lines += [f"- {d['text']} `{d['cites']}`" for d in r["dropped"]]
    lines += ["", f"Expected: {' '.join(str(case.get('expected', case.get('expected_before_reversal', ''))).split())}", ""]
    return "\n".join(lines) + "\n"


def write_report(all_cases: list[dict], fresh: dict[str, tuple], when: str, results: list[dict]) -> None:
    """Rows and answers from this run replace their old ones; questions not run keep theirs."""
    old_rows, old_sections, _ = read_report()
    rows, sections = [], []
    for case in all_cases:
        if case["id"] in fresh:
            r, s, err = fresh[case["id"]]
            rows.append(new_row(case, r, s, err, when))
            sections.append(new_section(case, r, s, err, when))
        elif case["id"] in old_rows:
            rows.append(old_rows[case["id"]])
            sections.append(old_sections.get(case["id"], f"### {case['id']}: {case['question']}\n\n(not shown)\n"))
        else:
            rows.append({"id": case["id"], "type": case.get("type", ""), "pass": "not run"})
            sections.append(f"### {case['id']}: {case['question']}\n\nNot run yet.\n")
    passed = lambda ids: sum(1 for r in rows if r["id"] in ids and r.get("pass") == "PASS")  # noqa: E731
    golden = {c["id"] for c in all_cases if c["id"].startswith("q")}
    lines = [
        "# Eval results", "",
        f"Run {when} by `scripts/eval.py` (Navigator via lore-mcp over stdio). Rows keep the run they come "
        "from (column `run`): questions that already passed aren't rerun unless asked. Scoring is "
        "deterministic: every must_cite URL cited, every key fact mentioned, every shown sentence cited "
        "(and, for not-found tests, the answer says so). See the script's docstring.", "",
        f"**Golden q01-q10: {passed(golden)} of {len(golden)} pass. All checks: "
        f"{passed({c['id'] for c in all_cases})} of {len(all_cases)}.**", "",
        f"This run: {timing_line(results)}", "",
        "| " + " | ".join(COLUMNS) + " |", "|" + " --- |" * len(COLUMNS),
    ]
    lines += ["| " + " | ".join(r.get(c, "") for c in COLUMNS) + " |" for r in rows]
    lines += ["", "## Answers", "", *sections]
    OUT.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- run

async def run(todo: list[dict], use_cache: bool, remember: bool, pause: float) -> dict[str, tuple]:
    fresh: dict[str, tuple] = {}
    session = f"session:{EVAL_USER}:{datetime.now(timezone.utc):%Y-%m-%dT%H%M}"
    async with Client(server_params()) as client:
        for i, case in enumerate(todo):
            if i and pause:
                time.sleep(pause)  # spread calls out over the free tiers' per-minute limits
            print(f"\n== {case['id']} ({case['org']}) {case['question']}", flush=True)
            try:
                r = await ask(case["question"], case["org"], EVAL_USER, client, session_id=session,
                              remember=remember, use_cache=use_cache, verbose=True)
            except Exception as e:  # noqa: BLE001 - one failed question shouldn't stop the run
                print(f"   ERROR {type(e).__name__}: {e}", flush=True)
                fresh[case["id"]] = (None, None, f"{type(e).__name__}: {e}")
                continue
            s = score(case, r)
            calls = [(c.get("endpoint"), c.get("prompt_tokens"), c.get("seconds"), "cached" if c.get("cached") else "")
                     for c in r["llm_calls"]]
            how = "answer cache" if r.get("answer_cache") else f"llm {calls}"
            print(f"   {'PASS' if s['pass'] else 'FAIL'} {s['checks']} ({r['seconds']}s, {how})\n   {r['answer']}",
                  flush=True)
            fresh[case["id"]] = (r, s, None)
    return fresh


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="*", help="question ids, comma or space separated: q06,q07 s02")
    p.add_argument("--all", action="store_true", help="rerun every question, passed ones too")
    p.add_argument("--pause", type=float, default=5.0, help="seconds between questions (default 5)")
    p.add_argument("--no-cache", action="store_true", help="bypass the answer cache and the LLM cache")
    p.add_argument("--no-remember", action="store_true")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    all_cases = cases(None)
    only = [x for arg in (a.only or []) for x in re.split(r"[,\s]+", arg) if x]
    if unknown := set(only) - {c["id"] for c in all_cases}:
        sys.exit(f"unknown ids: {sorted(unknown)}")
    old_rows, _, _ = read_report()
    if only:
        todo = [c for c in all_cases if c["id"] in only]
    elif a.all:
        todo = all_cases
    else:
        todo = [c for c in all_cases if old_rows.get(c["id"], {}).get("pass") != "PASS"]
        print(f"skipping {len(all_cases) - len(todo)} questions that already passed (--all reruns them)")
    print(f"running {len(todo)}: {', '.join(c['id'] for c in todo)}")
    when = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
    fresh = anyio.run(run, todo, not a.no_cache, not a.no_remember, a.pause)
    results = [r for r, _, _ in fresh.values() if r]
    write_report(all_cases, fresh, when, results)
    print(f"\n{timing_line(results)}\nwrote {OUT}")
    rows, _, _ = read_report()
    golden = [k for k in rows if k.startswith("q")]
    print(f"golden: {sum(1 for k in golden if rows[k].get('pass') == 'PASS')} of {len(golden)} pass; "
          f"all: {sum(1 for r in rows.values() if r.get('pass') == 'PASS')} of {len(rows)}")


if __name__ == "__main__":
    main()
