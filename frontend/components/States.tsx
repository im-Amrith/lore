"use client";

// Shared loading / error / empty states for the screens, so every page says what is happening.

import { useEffect, useState } from "react";
import type { CypherRun } from "@/lib/api";

export function Loading({ what, rows = 3 }: { what: string; rows?: number }) {
  return (
    <div aria-live="polite" aria-busy="true" className="space-y-3">
      <p className="flex items-center gap-2 text-sm text-muted">
        <span className="pulse-dot h-2 w-2 rounded-full bg-accent" />
        {what}
      </p>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="pulse-dot h-16 rounded-xl border border-line bg-surface/70" style={{ animationDelay: `${i * 150}ms` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border border-miss-line bg-miss-soft px-4 py-2.5 text-sm text-miss">
      <span className="font-medium">{title}</span>
      <span className="min-w-0 flex-1 break-words text-miss/90">{friendly(message)}</span>
      {onRetry && (
        <button onClick={onRetry} className="rounded-md border border-miss-line bg-surface px-2.5 py-0.5 text-xs font-medium hover:border-miss">
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong px-6 py-8 text-center">
      <p className="text-[15px] text-ink-2">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}

/** "Failed to fetch" means the API is unreachable, which the reader can't act on as-is. */
function friendly(message: string): string {
  return /failed to fetch|networkerror|load failed/i.test(message)
    ? "The Lore API isn't reachable right now. It may be restarting; try again in a few seconds."
    : message;
}

/** The Cypher that produced a screen, as on the Ask screen's "Show query". */
export function QueryToggle({ cypher }: { cypher: CypherRun[] }) {
  const [open, setOpen] = useState(false);
  if (!cypher.length) return null;
  return (
    <div className="mt-8">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="text-xs font-medium text-accent hover:underline">
        {open ? "Hide query" : `Show query (${cypher.length})`}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {cypher.map((c, i) => (
            <div key={i} className="overflow-hidden rounded-lg border border-line bg-sunk/60">
              <div className="flex flex-wrap items-baseline gap-x-2 border-b border-line px-3 py-1.5 text-xs">
                <span className="text-muted">{c.tool} ›</span>
                <span className="font-mono font-medium text-ink">{c.query}</span>
                <span className="ml-auto text-muted">
                  {c.rows} row{c.rows === 1 ? "" : "s"}
                </span>
              </div>
              <pre className="scroll-quiet max-h-64 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink-2">{c.cypher.trim()}</pre>
              <div className="scroll-quiet overflow-x-auto border-t border-line px-3 py-1.5 font-mono text-[11px] text-muted">
                params {JSON.stringify(c.params)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** The username kept in localStorage by the Ask screen. */
export function useUser(): [string | null, (id: string) => void] {
  const [user, setUser] = useState<string | null>(null);
  useEffect(() => {
    try {
      setUser(localStorage.getItem("lore.user"));
    } catch {
      /* private mode */
    }
  }, []);
  return [
    user,
    (id: string) => {
      setUser(id);
      try {
        localStorage.setItem("lore.user", id);
      } catch {
        /* not remembered */
      }
    },
  ];
}

/** "PR #15" for a GitHub pull/issue/commit URL. */
export function urlLabel(url: string): string {
  const m = url.match(/\/(pull|issues)\/(\d+)/);
  if (m) return `${m[1] === "pull" ? "PR" : "Issue"} #${m[2]}`;
  const c = url.match(/\/commit\/([0-9a-f]{7})/);
  if (c) return c[1];
  return url.split("/").pop() || url;
}

export function ago(epoch: number | null | undefined): string {
  if (!epoch) return "";
  const days = Math.round((Date.now() / 1000 - epoch) / 86400);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : days < 60 ? `${days} days ago` : `${Math.round(days / 30)} months ago`;
}
