"use client";

import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { TriageCard } from "@/components/TriageCard";
import { getPlaybook, getTriage, syncTriage, type Playbook, type TriageInbox } from "@/lib/api";

const REFRESH_MS = 8000; // the inbox re-reads the work board; Steward itself runs in the API

function readUser(): string | null {
  try {
    return localStorage.getItem("lore.user");
  } catch {
    return null;
  }
}

function clock(epoch: number | null | undefined): string {
  return epoch ? new Date(epoch * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
}

export default function TriagePage() {
  const [user, setUser] = useState<string | null>(null);
  const [inbox, setInbox] = useState<TriageInbox | null>(null);
  const [playbook, setPlaybook] = useState<Playbook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState<"todo" | "all">("todo");
  const [showPlaybook, setShowPlaybook] = useState(false);

  const refresh = useCallback(() => {
    getTriage()
      .then((r) => {
        setInbox(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getPlaybook().then(setPlaybook).catch(() => {});
  }, []);

  useEffect(() => {
    setUser(readUser());
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  function chooseUser(id: string) {
    setUser(id);
    try {
      localStorage.setItem("lore.user", id);
    } catch {
      /* not remembered */
    }
  }

  async function sync() {
    setSyncing(true);
    try {
      await syncTriage();
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  }

  const items = (inbox?.items ?? []).filter((i) => filter === "all" || i.status !== "approved");
  const counts = (inbox?.items ?? []).reduce<Record<string, number>>((a, i) => ({ ...a, [i.status]: (a[i.status] ?? 0) + 1 }), {});
  const learned = new Set((playbook?.feedback ?? []).map((f) => f.rule).filter(Boolean));
  const tick = inbox?.steward.last_tick;

  return (
    <div className="flex min-h-dvh flex-col">
      <Header user={user} onUser={chooseUser} />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 sm:px-5">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1">
            <h1 className="font-serif text-[26px] leading-tight text-ink">Triage inbox</h1>
            <p className="mt-1 text-sm text-muted">
              New issues in{" "}
              {inbox ? (
                <a href={`https://github.com/${inbox.repo}/issues`} target="_blank" rel="noreferrer" className="text-ink-2 hover:text-accent">
                  {inbox.repo}
                </a>
              ) : (
                "the sandbox repo"
              )}
              . Steward drafts each from the graph; nothing is posted until you approve it.
            </p>
          </div>
          {inbox && (
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                inbox.dry_run ? "border-line-strong bg-sunk text-muted" : "border-miss-line bg-miss-soft text-miss"
              }`}
              title={inbox.dry_run ? "DRY_RUN=true: approving only records the approval" : "DRY_RUN=false: approving posts the comment on GitHub"}
            >
              {inbox.dry_run ? "Dry run: approvals don't post" : "Live: approvals post to GitHub"}
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 border-y border-line py-2.5 text-sm">
          <div className="flex rounded-lg border border-line bg-sunk p-0.5">
            {(["todo", "all"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setFilter(k)}
                aria-pressed={filter === k}
                className={`rounded-md px-3 py-0.5 ${filter === k ? "bg-surface font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}
              >
                {k === "todo" ? `To do (${(inbox?.items.length ?? 0) - (counts.approved ?? 0)})` : `All (${inbox?.items.length ?? 0})`}
              </button>
            ))}
          </div>
          <span className="text-muted">
            {inbox?.poll_seconds ? `Checks GitHub every ${inbox.poll_seconds} s` : "Webhook only"}
            {tick && ` · last check ${clock(tick.at)}`}
            {tick && tick.loaded.length > 0 && ` · ${tick.loaded.length} new`}
          </span>
          <button
            onClick={sync}
            disabled={syncing}
            className="ml-auto rounded-lg border border-line-strong px-3 py-1 text-sm text-ink-2 hover:border-ink-2 hover:text-ink disabled:opacity-60"
          >
            {syncing ? "Checking…" : "Check now"}
          </button>
          <button onClick={() => setShowPlaybook(!showPlaybook)} className="text-sm text-muted hover:text-ink" aria-expanded={showPlaybook}>
            Playbook v{playbook?.version ?? 0} {showPlaybook ? "▴" : "▾"}
          </button>
        </div>

        {showPlaybook && playbook && (
          <section aria-label="Playbook" className="mt-3 rounded-xl border border-line bg-surface px-5 py-4">
            <h2 className="text-sm font-medium text-ink">Steward&rsquo;s triage Playbook</h2>
            <p className="mt-0.5 text-xs text-muted">
              Procedural memory in the graph: (Feedback)-[:ADJUSTS]-&gt;(Playbook). Edits you approve add a rule; the next draft follows it.
            </p>
            <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-ink-2">
              {playbook.steps.map((s, i) => (
                <li key={i} className={learned.has(s) ? "text-accent-ink" : undefined}>
                  {s}
                  {learned.has(s) && <span className="ml-1.5 rounded bg-accent-soft px-1 text-[11px] text-accent-ink">learned</span>}
                </li>
              ))}
            </ol>
          </section>
        )}

        {error && (
          <div className="mt-4 rounded-lg border border-miss-line bg-miss-soft px-4 py-2.5 text-sm text-miss">
            Can&rsquo;t load the inbox: {error}
          </div>
        )}
        {inbox?.steward.last_error && (
          <div className="mt-4 rounded-lg border border-pending-line bg-pending-soft px-4 py-2.5 text-sm text-pending">
            Last check failed: {inbox.steward.last_error}
          </div>
        )}

        <div className="mt-5 space-y-4">
          {inbox && items.length === 0 && (
            <div className="rounded-xl border border-dashed border-line-strong px-6 py-10 text-center">
              <p className="text-[15px] text-ink-2">Nothing to triage.</p>
              <p className="mt-1 text-sm text-muted">
                Open an issue in{" "}
                <a href={`https://github.com/${inbox.repo}/issues/new`} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  {inbox.repo}
                </a>{" "}
                and its draft appears here within a minute.
              </p>
            </div>
          )}
          {items.map((item) => (
            <TriageCard
              key={item.task_id}
              item={item}
              user={user}
              playbookVersion={playbook?.version ?? 0}
              onChanged={refresh}
            />
          ))}
        </div>
      </main>
    </div>
  );
}
