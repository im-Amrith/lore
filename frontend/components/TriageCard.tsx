"use client";

import { useState } from "react";
import { approveTask, redraftTask, type ApproveResult, type TriageItem, type TriagePerson } from "@/lib/api";
import { Markdown } from "@/lib/markdown";

const STATUS: Record<TriageItem["status"], { label: string; cls: string }> = {
  open: { label: "Waiting for Steward", cls: "border-line-strong bg-sunk text-muted" },
  claimed: { label: "Steward is drafting", cls: "border-accent/30 bg-accent-soft text-accent-ink" },
  drafted: { label: "Draft ready", cls: "border-pending-line bg-pending-soft text-pending" },
  approved: { label: "Approved", cls: "border-accent/40 bg-accent-soft text-accent-ink" },
};

function ago(epoch: number | null): string {
  if (!epoch) return "";
  const s = Math.max(0, Date.now() / 1000 - epoch);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// The approve passcode is kept for this browser tab only (sessionStorage), never in localStorage.
function readPasscode(): string {
  try {
    return sessionStorage.getItem("lore.passcode") ?? "";
  } catch {
    return "";
  }
}

function Who({ label, p }: { label: string; p: TriagePerson }) {
  const href = p.login ? `https://github.com/${p.login}` : undefined;
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" className="font-medium hover:text-accent">
            {p.mention}
          </a>
        ) : (
          <span className="font-medium">{p.mention}</span>
        )}
        {p.why && <span className="text-muted"> · {p.why}</span>}
      </dd>
    </div>
  );
}

export function TriageCard({
  item, user, playbookVersion, onChanged,
}: {
  item: TriageItem;
  user: string | null;
  playbookVersion: number;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.draft ?? "");
  const [rule, setRule] = useState("");
  const [busy, setBusy] = useState<null | "approve" | "redraft">(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApproveResult | null>(null);
  const [showFacts, setShowFacts] = useState(false);
  const [passcode, setPasscode] = useState(readPasscode);

  const f = item.facts;
  const status = STATUS[item.status] ?? STATUS.open;
  const final = item.status === "approved" ? item.approved_draft ?? item.draft ?? "" : editing ? text : item.draft ?? "";
  const edited = editing && text.trim() !== (item.draft ?? "").trim();
  const stale = item.status === "drafted" && (item.playbook_version ?? 0) < playbookVersion;

  async function approve() {
    if (!user) return;
    setBusy("approve");
    setError(null);
    try {
      try {
        sessionStorage.setItem("lore.passcode", passcode);
      } catch {
        /* not remembered */
      }
      const r = await approveTask(item.number, {
        user,
        draft: editing ? text : item.draft ?? "",
        rule: rule.trim() || undefined,
        passcode,
      });
      setResult(r);
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function redraft() {
    setBusy("redraft");
    setError(null);
    try {
      await redraftTask(item.number);
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="rounded-xl border border-line bg-surface shadow-[0_1px_0_rgba(0,0,0,0.02)]">
      <header className="flex flex-wrap items-start gap-x-3 gap-y-1.5 border-b border-line px-5 py-3.5">
        <div className="min-w-0 flex-1">
          <a href={item.url} target="_blank" rel="noreferrer" className="group block">
            <span className="font-mono text-xs text-muted">#{item.number}</span>{" "}
            <span className="text-[15px] font-medium text-ink group-hover:text-accent">{item.title}</span>
          </a>
          {item.body && <p className="mt-1 line-clamp-2 text-sm text-muted">{item.body}</p>}
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium ${status.cls}`}>
          {item.status === "claimed" && <span className="pulse-dot mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-accent align-middle" />}
          {status.label}
        </span>
      </header>

      {f && (
        <dl className="grid gap-x-6 gap-y-3 border-b border-line bg-paper/50 px-5 py-3.5 sm:grid-cols-2">
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted">Related past work</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {f.related_issues.length === 0 && <span className="text-sm text-muted">No similar issue in the graph.</span>}
              {f.related_issues.map((r) => (
                <span key={r.id} className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-0.5 text-sm">
                  <a href={r.url} target="_blank" rel="noreferrer" className="font-medium text-ink hover:text-accent">
                    #{r.number}
                  </a>
                  <span className="max-w-[16rem] truncate text-muted">{r.title}</span>
                  {r.fixed_by.map((p) => (
                    <a key={p.url} href={p.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                      fixed by PR #{p.url.split("/").pop()}
                    </a>
                  ))}
                  {r.state === "open" && <span className="text-xs text-pending">open</span>}
                  {r.duplicate && <span className="rounded bg-miss-soft px-1 text-xs text-miss">likely duplicate</span>}
                </span>
              ))}
            </dd>
          </div>
          {f.suggested_owner && <Who label={`Owner${f.module?.path ? ` · ${f.module.path}` : ""}`} p={f.suggested_owner} />}
          {f.suggested_reviewer && <Who label="Reviewer" p={f.suggested_reviewer} />}
          {f.paper_owner_warnings.map((w) => (
            <p key={w.id} className="rounded-md border border-pending-line bg-pending-soft px-3 py-2 text-sm text-pending sm:col-span-2">
              <span className="font-medium">Paper owner.</span> {w.text}.
            </p>
          ))}
          {f.decision_behind_fix && (
            <div className="min-w-0 sm:col-span-2">
              <dt className="text-[11px] font-medium uppercase tracking-wide text-muted">Decision behind the earlier fix</dt>
              <dd className="mt-0.5 text-sm text-ink-2">
                {f.decision_behind_fix.statement}{" "}
                {f.decision_behind_fix.url && (
                  <a href={f.decision_behind_fix.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                    source
                  </a>
                )}
              </dd>
            </div>
          )}
        </dl>
      )}

      <div className="px-5 py-4">
        {item.status === "open" || item.status === "claimed" ? (
          <p className="text-sm text-muted">
            {item.error ? (
              <span className="text-miss">
                Last draft failed ({item.attempts ?? 1}×): {item.error}. Steward retries on the next check.
              </span>
            ) : item.status === "claimed" ? (
              `Claimed by ${item.claimed_by}. Reading related work, owners and experts from the graph…`
            ) : (
              "On the work board. Steward picks it up on the next check."
            )}
          </p>
        ) : editing ? (
          <div className="space-y-2.5">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={Math.min(16, Math.max(6, text.split("\n").length + 1))}
              aria-label="Triage comment"
              className="w-full rounded-lg border border-line-strong bg-surface p-3 font-mono text-[13px] leading-relaxed outline-none focus:border-accent"
            />
            <label className="block">
              <span className="text-xs text-muted">
                Rule for next time <span className="text-muted/70">(optional; learned from your edit if empty)</span>
              </span>
              <input
                value={rule}
                onChange={(e) => setRule(e.target.value)}
                placeholder="e.g. Always ask for a regression test under tests/"
                className="mt-1 w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
              />
            </label>
          </div>
        ) : (
          <div className="rounded-lg border border-line bg-paper/40 px-4 py-3 text-[14px] leading-relaxed text-ink-2">
            <Markdown text={final} />
          </div>
        )}

        {item.status === "approved" && (
          <p className="mt-3 text-sm">
            {item.posted && item.comment_url ? (
              <span className="text-accent-ink">
                Approved by {item.approved_by} {ago(item.approved_at)} and{" "}
                <a href={item.comment_url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-2">
                  posted on GitHub
                </a>
                .
              </span>
            ) : (
              <span className="text-muted">
                Approved by {item.approved_by} {ago(item.approved_at)}. Dry run: not posted (DRY_RUN is on).
              </span>
            )}
          </p>
        )}
        {result?.feedback && (
          <p className="mt-2 rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
            Playbook v{result.feedback.playbook_version}
            {result.feedback.rule ? (
              <>
                {" "}learned{result.feedback.learned ? " from your edit" : ""}: <em>{result.feedback.rule}</em>
              </>
            ) : (
              ": your edit is stored as feedback (no general rule in it)."
            )}
          </p>
        )}
        {error && <p className="mt-2 text-sm text-miss">{error}</p>}

        {item.status === "drafted" && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              type="password"
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              placeholder="Approve passcode"
              aria-label="Approve passcode"
              autoComplete="off"
              className="w-40 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
            <button
              onClick={approve}
              disabled={!user || !passcode || busy !== null || !(editing ? text : item.draft)?.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-ink disabled:bg-line-strong"
            >
              {busy === "approve" ? "Approving…" : edited ? "Approve edit and post" : "Approve and post"}
            </button>
            <button
              onClick={() => {
                setEditing(!editing);
                setText(item.draft ?? "");
              }}
              disabled={busy !== null}
              className="rounded-lg border border-line-strong px-3 py-1.5 text-sm text-ink-2 hover:border-ink-2 hover:text-ink"
            >
              {editing ? "Cancel edit" : "Edit"}
            </button>
            <button
              onClick={redraft}
              disabled={busy !== null || editing}
              className={`rounded-lg px-3 py-1.5 text-sm ${stale ? "border border-pending-line text-pending hover:bg-pending-soft" : "text-muted hover:text-ink"}`}
              title={stale ? `Drafted with Playbook v${item.playbook_version ?? 0}; it's now v${playbookVersion}` : undefined}
            >
              {busy === "redraft" ? "Redrafting…" : stale ? `Redraft with Playbook v${playbookVersion}` : "Redraft"}
            </button>
            {!user && <span className="text-sm text-pending">Pick a username (top right) to approve.</span>}
            <span className="ml-auto text-xs text-muted">
              {item.model} · Playbook v{item.playbook_version ?? 0} · {ago(item.drafted_at)}
              {f && (
                <button onClick={() => setShowFacts(!showFacts)} className="ml-2 underline underline-offset-2 hover:text-ink">
                  {showFacts ? "hide" : "show"} tool calls
                </button>
              )}
            </span>
          </div>
        )}
        {showFacts && f && (
          <ol className="mt-3 space-y-1 rounded-lg bg-sunk px-4 py-3 font-mono text-xs text-ink-2">
            {f.tool_calls.map((c, i) => (
              <li key={i}>
                {i + 1}. {c.tool}({Object.entries(c.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}){" "}
                <span className="text-muted">→ {c.queries.join(", ")}</span>
              </li>
            ))}
            {f.rejected_links.length > 0 && <li className="text-miss">links dropped (no tool returned them): {f.rejected_links.join(" ")}</li>}
          </ol>
        )}
      </div>
    </article>
  );
}
