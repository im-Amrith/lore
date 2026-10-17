"use client";

import { useEffect, useState } from "react";
import type { AskResult, Citation, ProgressEvent, Sentence } from "@/lib/api";
import { KIND_COLOR, kindOf, longLabel, shortLabel, truncate } from "@/lib/nodes";

const INTENT_LABEL: Record<string, string> = {
  why: "Why", "who-knows": "Who knows", owns: "Who owns", risk: "Knowledge risk", impact: "Impact",
  onboarding: "Onboarding", changed: "What changed", triage: "Triage", general: "General",
};

/** Which model wrote the answer: the last LLM call (the compose step). */
function answeredBy(r: AskResult): string | null {
  const last = r.llm_calls[r.llm_calls.length - 1];
  const ep = last?.endpoint ?? last?.model;
  if (!ep) return null;
  const [provider, ...model] = ep.split(":");
  return model.length ? `${model.join(":").replace(/^openai\//, "")} · ${provider}` : ep;
}

function Cite({ c, label, onFocus }: { c: Citation; label: string; onFocus: (id: string | null) => void }) {
  const chip =
    "inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 align-[2px] font-sans text-[10px] font-semibold tabular-nums";
  return c.url ? (
    <a
      href={c.url}
      target="_blank"
      rel="noreferrer"
      title={`${label} (opens GitHub)`}
      onMouseEnter={() => onFocus(c.id)}
      onMouseLeave={() => onFocus(null)}
      className={`${chip} bg-accent-soft text-accent-ink ring-1 ring-accent/20 hover:bg-accent hover:text-white`}
    >
      {c.n}
    </a>
  ) : (
    <span
      title={label}
      onMouseEnter={() => onFocus(c.id)}
      onMouseLeave={() => onFocus(null)}
      className={`${chip} bg-sunk text-muted ring-1 ring-line`}
    >
      {c.n}
    </span>
  );
}

function SentenceLine({ s, r, onFocus }: { s: Sentence; r: AskResult; onFocus: (id: string | null) => void }) {
  const byId = new Map(r.citations.map((c) => [c.id, c]));
  return (
    <>
      {s.text}{" "}
      <span className="whitespace-nowrap">
        {s.cites.map((id) => {
          const c = byId.get(id);
          return c ? <Cite key={id} c={c} label={shortLabel(id, r.labels)} onFocus={onFocus} /> : null;
        })}
      </span>{" "}
    </>
  );
}

function Sources({ r, onFocus }: { r: AskResult; onFocus: (id: string | null) => void }) {
  if (!r.citations.length) return null;
  return (
    <ol className="mt-4 space-y-1.5 border-t border-line pt-3 text-[13px]">
      {r.citations.map((c) => {
        const short = shortLabel(c.id, r.labels);
        const long = longLabel(c.id, r.labels);
        const status = r.decision_status?.[c.id];
        return (
          <li
            key={c.id}
            className="flex items-baseline gap-2"
            onMouseEnter={() => onFocus(c.id)}
            onMouseLeave={() => onFocus(null)}
          >
            <span className="w-4 shrink-0 text-right font-semibold tabular-nums text-muted">{c.n}</span>
            <span className="relative top-[-1px] h-2 w-2 shrink-0 rounded-full" style={{ background: KIND_COLOR[kindOf(c.id)] }} />
            <span className="min-w-0">
              {c.url ? (
                <a href={c.url} target="_blank" rel="noreferrer" className="font-medium text-ink hover:text-accent hover:underline">
                  {short}
                  <span className="ml-0.5 text-muted">↗</span>
                </a>
              ) : (
                <span className="font-medium text-ink">{short}</span>
              )}
              {long && <span className="text-muted"> · {truncate(long, 110)}</span>}
              {status && status !== "active" && (
                <span className="ml-1.5 rounded bg-pending-soft px-1 text-[11px] text-pending">
                  {status === "proposed" ? "proposed, not merged" : status}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function QueryPanel({ r }: { r: AskResult }) {
  return (
    <div className="mt-3 space-y-3">
      {r.cypher.map((c, i) => (
        <div key={i} className="overflow-hidden rounded-lg border border-line bg-sunk/60">
          <div className="flex flex-wrap items-baseline gap-x-2 border-b border-line px-3 py-1.5 text-xs">
            <span className="text-muted">{c.tool} ›</span>
            <span className="font-mono font-medium text-ink">{c.query}</span>
            <span className="ml-auto text-muted">{c.rows} row{c.rows === 1 ? "" : "s"}</span>
          </div>
          <pre className="scroll-quiet max-h-64 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink-2">
            {c.cypher.trim()}
          </pre>
          <div className="scroll-quiet overflow-x-auto border-t border-line px-3 py-1.5 font-mono text-[11px] text-muted">
            params {JSON.stringify(c.params)}
          </div>
        </div>
      ))}
    </div>
  );
}

export function AnswerCard({
  r, active, onSelect, onFocus,
}: {
  r: AskResult;
  active: boolean;
  onSelect: () => void;
  onFocus: (id: string | null) => void;
}) {
  const [showQuery, setShowQuery] = useState(false);
  const model = answeredBy(r);
  const regular = r.sentences.filter((s) => !s.pending);
  const pending = r.sentences.filter((s) => s.pending);

  return (
    <article
      onClick={onSelect}
      className={`rounded-xl border bg-surface px-5 py-4 transition-shadow ${
        active ? "border-line-strong shadow-[0_1px_0_#0000000a,0_8px_24px_-12px_#1c22262e]" : "cursor-pointer border-line opacity-80 hover:opacity-100"
      }`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="rounded-full bg-sunk px-2 py-0.5 font-medium text-ink-2">{INTENT_LABEL[r.intent] ?? r.intent}</span>
        {r.answer_cache && (
          <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent-ink" title="Served from the answer cache: same question, same graph data">
            cached
          </span>
        )}
        {model && <span title="The model that wrote this answer">{r.answer_cache ? "first answered by " : "answered by "}{model}</span>}
        <span className="ml-auto tabular-nums">{r.seconds.toFixed(1)} s</span>
      </div>

      {!r.found ? (
        <div className="rounded-lg border border-miss-line bg-miss-soft px-4 py-3">
          <p className="text-sm font-semibold text-miss">Not found</p>
          <p className="mt-1 font-serif text-[15px] leading-relaxed text-ink-2">
            {r.not_found || "No path in the graph answers this question."} Lore won&rsquo;t guess.
          </p>
          {r.sentences.length > 0 && (
            <>
              <p className="mt-3 text-xs font-medium uppercase tracking-wide text-miss/80">Nearest evidence</p>
              <ul className="mt-1 space-y-1 font-serif text-[15px] leading-relaxed text-ink">
                {r.sentences.map((s, i) => (
                  <li key={i}>
                    <SentenceLine s={s} r={r} onFocus={onFocus} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <p className="font-serif text-[16.5px] leading-[1.7] text-ink">
          {regular.map((s, i) => (
            <SentenceLine key={i} s={s} r={r} onFocus={onFocus} />
          ))}
        </p>
      )}

      {r.found && pending.length > 0 && (
        <div className="mt-3 rounded-lg border border-pending-line bg-pending-soft px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-pending">Draft PR proposes changing this · not merged</p>
          <p className="mt-1 font-serif text-[15px] leading-relaxed text-ink-2">
            {pending.map((s, i) => (
              <SentenceLine key={i} s={s} r={r} onFocus={onFocus} />
            ))}
          </p>
        </div>
      )}

      <Sources r={r} onFocus={onFocus} />

      <div className="mt-3 flex items-center gap-4 text-xs">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowQuery((v) => !v);
          }}
          aria-expanded={showQuery}
          className="font-medium text-accent hover:underline"
        >
          {showQuery ? "Hide query" : `Show query (${r.cypher.length})`}
        </button>
        <span className="text-muted">tools: {r.tool_calls.map((t) => t.tool).join(" → ")}</span>
      </div>
      {showQuery && <QueryPanel r={r} />}
    </article>
  );
}

const STEP_LABEL: Record<string, string> = {
  "pick tools": "Choosing tools",
  "pick again": "Results were empty; choosing again",
  "write answer": "Writing the answer from the results",
};

function describeArgs(args: Record<string, unknown>): string {
  const v = Object.values(args)[0];
  return v === undefined ? "" : truncate(typeof v === "string" ? v : JSON.stringify(v), 60);
}

/** While the Navigator works: each tool and LLM step as it streams in. */
export function ProgressCard({ events, startedAt }: { events: ProgressEvent[]; startedAt: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const steps: { key: string; text: string; detail?: string; done: boolean }[] = [];
  for (const e of events) {
    if (e.type === "cache") steps.push({ key: "cache", text: "Found in the answer cache", done: true });
    if (e.type === "tool") {
      steps.forEach((s) => (s.done = true));
      steps.push({ key: `t${e.n}`, text: e.tool, detail: describeArgs(e.args), done: true });
    }
    if (e.type === "llm") steps.push({ key: `l${steps.length}`, text: STEP_LABEL[e.step] ?? e.step, done: false });
    if (e.type === "llm_done") {
      const s = [...steps].reverse().find((x) => !x.done);
      if (s) {
        s.done = true;
        s.detail = [e.endpoint?.split(":").slice(1).join(":").replace(/^openai\//, ""), e.cached ? "cached" : `${e.seconds} s`]
          .filter(Boolean)
          .join(" · ");
      }
    }
  }
  if (!steps.length) steps.push({ key: "start", text: "Starting", done: false });

  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-5 py-4" aria-live="polite">
      <div className="mb-2 flex items-center text-xs text-muted">
        <span className="pulse-dot mr-2 h-2 w-2 rounded-full bg-accent" />
        Tracing through the graph
        <span className="ml-auto tabular-nums">{((now - startedAt) / 1000).toFixed(1)} s</span>
      </div>
      <ol className="space-y-1 text-sm">
        {steps.map((s) => (
          <li key={s.key} className="flex items-baseline gap-2">
            <span className={`w-3 shrink-0 text-center ${s.done ? "text-accent" : "pulse-dot text-muted"}`}>{s.done ? "✓" : "•"}</span>
            <span className={s.text.includes("_") ? "font-mono text-[13px] text-ink" : "text-ink-2"}>{s.text}</span>
            {s.detail && <span className="truncate text-xs text-muted">{s.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}
