"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnswerCard, ProgressCard } from "@/components/Answer";
import { EvidenceGraph } from "@/components/EvidenceGraph";
import { Header, type Org } from "@/components/Header";
import { ErrorBox } from "@/components/States";
import { ApiError, askStream, getHealth, type AskResult, type ProgressEvent } from "@/lib/api";
import { EXAMPLES } from "@/lib/examples";

type Turn = {
  id: number;
  question: string;
  startedAt: number;
  events: ProgressEvent[];
  result?: AskResult;
  error?: string;
};

const store = {
  get: (k: string) => {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set: (k: string, v: string) => {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* private mode: fine, just not remembered */
    }
  },
};

let nextId = 1;

export default function AskPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [org, setOrg] = useState<string>("");
  const [user, setUser] = useState<string | null>(null);
  const [apiDown, setApiDown] = useState<string | null>(null);
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [activeId, setActiveId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  function connect() {
    setApiDown(null);
    getHealth()
      .then((h) => {
        const sandboxOwner = h.sandbox_repo?.split("/")[0];
        const list = Object.keys(h.orgs).map((id) => ({
          id,
          label: id === sandboxOwner ? h.sandbox_repo.split("/")[1] ?? id : id,
        }));
        setOrgs(list);
        const saved = store.get("lore.org");
        setOrg(list.find((o) => o.id === saved)?.id ?? list[0]?.id ?? "");
      })
      .catch((e) => setApiDown(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    connect();
    setUser(store.get("lore.user"));
  }, []);

  const turns = threads[org] ?? [];
  const active = turns.find((t) => t.id === activeId)?.result ?? [...turns].reverse().find((t) => t.result)?.result ?? null;
  const sandboxLabel = orgs.find((o) => o.id === org)?.label;
  const examples = useMemo(() => (org === "FalkorDB" ? EXAMPLES.FalkorDB : EXAMPLES.sandbox), [org]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, turns[turns.length - 1]?.events.length, turns[turns.length - 1]?.result]);

  function chooseOrg(id: string) {
    setOrg(id);
    setActiveId(null);
    store.set("lore.org", id);
  }

  function chooseUser(id: string) {
    setUser(id);
    store.set("lore.user", id);
  }

  async function ask(question: string) {
    const q = question.trim();
    if (!q || !user || busy) return;
    const id = nextId++;
    const forOrg = org;
    const update = (fn: (t: Turn) => Turn) =>
      setThreads((all) => ({ ...all, [forOrg]: (all[forOrg] ?? []).map((t) => (t.id === id ? fn(t) : t)) }));
    setThreads((all) => ({ ...all, [forOrg]: [...(all[forOrg] ?? []), { id, question: q, startedAt: Date.now(), events: [] }] }));
    setActiveId(id);
    setDraft("");
    setBusy(true);
    try {
      const result = await askStream({ org: forOrg, user, question: q }, (e) =>
        update((t) => ({ ...t, events: [...t.events, e] })),
      );
      update((t) => ({ ...t, result }));
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 429
          ? `Slow down a little: ${e.message}`
          : e instanceof ApiError && e.status === 503
            ? "Every free model is rate-limited right now. Try again in a minute."
            : e instanceof Error
              ? e.message
              : String(e);
      update((t) => ({ ...t, error: msg }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <Header orgs={orgs} org={org} onOrg={chooseOrg} user={user} onUser={chooseUser} />

      {apiDown && (
        <div className="border-b border-miss-line px-5 py-2">
          <ErrorBox title="Can't reach the Lore API." message={apiDown} onRetry={connect} />
        </div>
      )}

      {/* Wide: chat and graph side by side, each scrolling on its own. Below 1024 px: one column,
          the page scrolls, the graph sits under the chat and the composer stays pinned. */}
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:overflow-hidden">
        {/* Chat */}
        <section className="flex flex-col border-line lg:min-h-0 lg:border-r" aria-label="Questions and answers">
          <div className="scroll-quiet space-y-5 px-5 py-6 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
            {turns.length === 0 && !org ? (
              <p className="mx-auto flex max-w-md items-center gap-2 pt-10 text-sm text-muted" aria-live="polite">
                {apiDown ? (
                  "The API is unreachable, so there is nothing to ask yet."
                ) : (
                  <>
                    <span className="pulse-dot h-2 w-2 rounded-full bg-accent" />
                    Connecting to the graph…
                  </>
                )}
              </p>
            ) : turns.length === 0 ? (
              <div className="mx-auto max-w-md pt-10">
                <h1 className="font-serif text-[28px] leading-tight text-ink">
                  Ask about {sandboxLabel ?? org}&rsquo;s history.
                </h1>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">
                  Every answer is traced through the graph of pull requests, issues, decisions and people, and every
                  claim links to the GitHub page it came from.
                </p>
                <div className="mt-6 flex flex-col gap-2">
                  {examples.map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      disabled={!user || busy}
                      className="rounded-lg border border-line bg-surface px-3.5 py-2.5 text-left text-sm text-ink-2 transition-colors hover:border-accent/40 hover:text-ink disabled:opacity-50"
                    >
                      {q}
                    </button>
                  ))}
                </div>
                {!user && <p className="mt-4 text-sm text-pending">Pick a username (top right) to start asking.</p>}
              </div>
            ) : (
              turns.map((t) => (
                <div key={t.id} className="space-y-2.5">
                  <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2 text-[15px] text-surface">
                    {t.question}
                  </p>
                  {t.result ? (
                    <AnswerCard
                      r={t.result}
                      active={active === t.result}
                      onSelect={() => setActiveId(t.id)}
                      onFocus={setFocusId}
                    />
                  ) : t.error ? (
                    <ErrorBox title="No answer." message={t.error} onRetry={busy ? undefined : () => ask(t.question)} />
                  ) : (
                    <ProgressCard events={t.events} startedAt={t.startedAt} />
                  )}
                </div>
              ))
            )}
            <div ref={bottom} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(draft);
            }}
            className="sticky bottom-0 z-10 border-t border-line bg-surface/95 p-3 backdrop-blur lg:static lg:bg-surface/70"
          >
            <div className="flex items-end gap-2 rounded-xl border border-line-strong bg-surface px-3 py-2 focus-within:border-accent">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    ask(draft);
                  }
                }}
                rows={1}
                placeholder={user ? `Why… / Who knows… / Who owns… in ${sandboxLabel ?? org}` : "Pick a username to ask"}
                disabled={!user}
                aria-label="Your question"
                className="max-h-32 min-h-[24px] flex-1 resize-none bg-transparent py-1 text-[15px] outline-none placeholder:text-muted/70"
              />
              <button
                disabled={!user || busy || draft.trim().length < 3}
                className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-ink disabled:bg-line-strong"
              >
                {busy ? "Asking…" : "Ask"}
              </button>
            </div>
          </form>
        </section>

        {/* Evidence */}
        <section className="h-[min(560px,80dvh)] shrink-0 border-t border-line bg-surface/40 lg:h-auto lg:min-h-0 lg:border-t-0" aria-label="Evidence path">
          <EvidenceGraph result={active} focusId={focusId} onFocus={setFocusId} />
        </section>
      </main>
    </div>
  );
}
