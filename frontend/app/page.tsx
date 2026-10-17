"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnswerCard, ProgressCard } from "@/components/Answer";
import { EvidenceGraph } from "@/components/EvidenceGraph";
import { Header, type Org } from "@/components/Header";
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

  useEffect(() => {
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
        <div className="border-b border-miss-line bg-miss-soft px-5 py-2 text-sm text-miss">
          Can&rsquo;t reach the Lore API ({apiDown}). Start it with{" "}
          <code className="font-mono text-xs">uvicorn lore.api.app:app --port 8000</code>.
        </div>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        {/* Chat */}
        <section className="flex min-h-0 flex-col border-line lg:border-r" aria-label="Questions and answers">
          <div className="scroll-quiet min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-6">
            {turns.length === 0 ? (
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
                    <div className="rounded-xl border border-miss-line bg-miss-soft px-5 py-3 text-sm text-miss">{t.error}</div>
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
            className="border-t border-line bg-surface/70 p-3"
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
        <section className="hidden min-h-0 bg-surface/40 lg:block" aria-label="Evidence path">
          <EvidenceGraph result={active} focusId={focusId} onFocus={setFocusId} />
        </section>
      </main>
    </div>
  );
}
