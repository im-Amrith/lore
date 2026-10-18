"""Reset the live demo's runtime state before recording (run on the server, inside the backend container).

    uv run --directory backend python scripts/demo_reset.py            # dry run: print what would change
    uv run --directory backend python scripts/demo_reset.py --yes      # apply
    uv run --directory backend python scripts/demo_reset.py --on-copy  # apply to throwaway copies of the graphs, then drop them

What it does, in every org graph (the demo org and the sandbox owner):
  - the demo user (--user, default amrith): deletes their questions and answers, except, in the
    sandbox graph, the latest question matching --keep ("why ... redis"): the pre-merge question
    that "what changed since I last asked?" compares against after PR #16 is merged
  - test users (--delete-users, default dvir-fan): deleted with everything they asked
  - sandbox triage Tasks (--tasks, default 6-10): back to 'drafted', approval fields cleared
It leaves the answer cache alone (memory nodes aren't in the data version, so cached answers stay
valid) and touches nothing else: no knowledge nodes, Playbook, Feedback or other users.
Queries: queries/16_demo_*.cypher.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import get_settings, graph_name  # noqa: E402
from lore.graph.client import get_graph, ro_query  # noqa: E402
from lore.graph.queries import load_query  # noqa: E402


def deleted(graph, name: str, params: dict) -> int:
    return graph.query(load_query(name), params).nodes_deleted


def reset(graphs: dict[str, object], sandbox_org: str, repo: str, a: argparse.Namespace, apply: bool) -> None:
    keep_re = re.compile(a.keep, re.I)
    for org, g in graphs.items():
        print(f"== {org} ({g.name})")
        questions = ro_query(g, "demo_questions", {"user_id": a.user})
        keep = [q for q in questions if org == sandbox_org and keep_re.search(q["question"])][-1:]
        keep_ids = [q["question_id"] for q in keep]
        for q in keep:
            print(f"  keep    {a.user}: {q['question']!r} ({q['question_id']})")
        print(f"  forget  {a.user}: {len(questions) - len(keep)} of {len(questions)} questions")
        if apply:
            n = deleted(g, "demo_forget", {"user_id": a.user, "keep": keep_ids})
            n += deleted(g, "demo_empty_sessions", {"user_id": a.user})
            print(f"          deleted {n} nodes")

        for u in a.delete_users:
            n_q = len(ro_query(g, "demo_questions", {"user_id": u}))
            print(f"  delete  user {u} ({n_q} questions)")
            if apply:
                print(f"          deleted {deleted(g, 'demo_delete_user', {'user_id': u})} nodes")

        if org == sandbox_org and a.tasks:
            task_ids = [f"task:triage:issue:{repo}#{n}" for n in a.tasks]
            for t in ro_query(g, "demo_tasks", {"task_ids": task_ids}):
                note = "" if t["has_draft"] or t["has_approved_draft"] else "  (no draft text: left for Steward)"
                print(f"  task    #{t['number']} {t['status']} -> drafted{note}")
            if apply:
                print(f"          reset {len(g.query(load_query('demo_task_redrafted'), {'task_ids': task_ids}).result_set)} Tasks")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user", default="amrith", help="the demo user whose memory is cleared")
    p.add_argument("--keep", default=r"why.*redis", help="regex: the demo user's sandbox question to keep (latest match)")
    p.add_argument("--delete-users", nargs="*", default=["dvir-fan"], help="test users to delete")
    p.add_argument("--tasks", nargs="*", type=int, default=[6, 7, 8, 9, 10], help="sandbox issue numbers")
    p.add_argument("--yes", action="store_true", help="apply (default: dry run)")
    p.add_argument("--on-copy", action="store_true", help="apply to copies of the graphs, print the result, drop them")
    a = p.parse_args()
    if a.user in a.delete_users:
        sys.exit(f"--user {a.user} is also in --delete-users")

    s = get_settings()
    if not s.sandbox_repo:
        sys.exit("SANDBOX_REPO is not set")
    sandbox_org = s.sandbox_repo.split("/")[0]
    orgs = list(dict.fromkeys([s.demo_org, sandbox_org]))

    if not a.on_copy:
        reset({o: get_graph(o) for o in orgs}, sandbox_org, s.sandbox_repo, a, apply=a.yes)
        if not a.yes:
            print("\ndry run: nothing changed; rerun with --yes to apply")
        return

    copies = {}
    try:
        for o in orgs:
            copies[o] = get_graph(o).copy(f"{graph_name(o)}_reset_test")
        reset(copies, sandbox_org, s.sandbox_repo, a, apply=True)
        print("\n-- after, on the copies:")
        reset(copies, sandbox_org, s.sandbox_repo, a, apply=False)
    finally:
        for c in copies.values():
            c.delete()
        print(f"\ndropped the copies: {', '.join(c.name for c in copies.values())}")


if __name__ == "__main__":
    main()
