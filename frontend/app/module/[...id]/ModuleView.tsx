"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { ago, Empty, ErrorBox, Loading, QueryToggle, urlLabel, useUser } from "@/components/States";
import { ApiError, getModule, moduleHref, type DecisionRow, type ModulePage } from "@/lib/api";
import { shortLabel } from "@/lib/nodes";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-accent-soft text-accent-ink",
  proposed: "bg-pending-soft text-pending",
  superseded: "bg-sunk text-muted line-through decoration-muted/50",
};

function Decision({ d }: { d: DecisionRow }) {
  const label = d.status === "proposed" ? "proposed · not merged" : d.status;
  return (
    <li className="flex gap-3 py-2.5">
      <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[d.status] ?? "bg-sunk text-muted"}`}>
        {label}
      </span>
      <div className="min-w-0">
        <p className={`font-serif text-[15px] leading-relaxed ${d.status === "superseded" ? "text-muted" : "text-ink"}`}>{d.statement}</p>
        {d.source_url && d.source_id && (
          <a href={d.source_url} target="_blank" rel="noreferrer" className="text-xs text-muted hover:text-accent hover:underline">
            {shortLabel(d.source_id)} ↗
          </a>
        )}
      </div>
    </li>
  );
}

export function ModuleView({ moduleId, org }: { moduleId: string; org?: string }) {
  const [user, setUser] = useUser();
  const [page, setPage] = useState<ModulePage | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);

  const load = useCallback(() => {
    setError(null);
    setPage(null);
    getModule(moduleId, org)
      .then(setPage)
      .catch((e) => setError({ status: e instanceof ApiError ? e.status : 0, message: e instanceof Error ? e.message : String(e) }));
  }, [moduleId, org]);

  useEffect(load, [load]);

  return (
    <div className="flex min-h-dvh flex-col">
      <Header user={user} onUser={setUser} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-5">
        <Link href={`/risk${org ? `?org=${encodeURIComponent(org)}` : ""}`} className="text-sm text-muted hover:text-ink">
          ← Risk map
        </Link>
        <h1 className="mt-2 break-words font-mono text-[22px] font-medium text-ink">{shortLabel(page?.module.id ?? moduleId)}</h1>

        <div className="mt-5">
          {error?.status === 404 ? (
            <Empty title="No such module in the graph.">
              Lore only knows the modules it mapped from the repo&rsquo;s file tree. Try the{" "}
              <Link href="/risk" className="text-accent hover:underline">
                risk map
              </Link>{" "}
              to pick one.
            </Empty>
          ) : error ? (
            <ErrorBox title="Can't load this module." message={error.message} onRetry={load} />
          ) : !page ? (
            <Loading what="Walking owners, experts, decisions and co-changes…" rows={4} />
          ) : (
            <Body p={page} />
          )}
        </div>
      </main>
    </div>
  );
}

function Body({ p }: { p: ModulePage }) {
  const o = p.owners;
  const paper = new Set(o.paper_owners);
  const ownerIds = new Set(o.owners.map((x) => x.id));
  const top = p.experts[0];
  const all = [...p.decisions.decisions, ...p.decisions.pending_proposals, ...p.decisions.history];
  const repoUrl = p.sources[p.module.id];

  return (
    <>
      <p className="-mt-3 text-sm text-muted">
        {p.module.repo} · {p.org}
        {repoUrl && (
          <>
            {" · "}
            <a href={repoUrl} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
              on GitHub ↗
            </a>
          </>
        )}
      </p>

      {o.mismatch && top && (
        <div className="mt-4 rounded-lg border border-pending-line bg-pending-soft px-4 py-2.5 text-sm text-pending">
          {o.listed_owner
            ? `CODEOWNERS lists ${o.owners.map((x) => x.name).join(", ")}, but the person who actually works here is ${top.name ?? top.person}.`
            : `No owner is listed in CODEOWNERS; the person who actually works here is ${top.name ?? top.person}.`}
        </div>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-sm font-medium text-ink">Listed owners</h2>
          <p className="text-xs text-muted">
            from{" "}
            {o.codeowners_url ? (
              <a href={o.codeowners_url} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
                CODEOWNERS ↗
              </a>
            ) : (
              "CODEOWNERS"
            )}
          </p>
          {o.owners.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{o.message ?? "Nobody is listed."}</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {o.owners.map((x) => (
                <li key={x.id} className="flex flex-wrap items-baseline gap-2 text-sm">
                  <span className="font-medium text-ink">{x.kind === "Team" ? "@" : ""}{x.name}</span>
                  {x.kind === "Team" && <span className="text-xs text-muted">team · {x.members} known members</span>}
                  {paper.has(x.name) && (
                    <span className="rounded bg-pending-soft px-1.5 text-[11px] text-pending" title="Listed, but hasn't authored or reviewed here in the window">
                      paper owner
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-sm font-medium text-ink">Who actually knows it</h2>
          <p className="text-xs text-muted">EXPERT_IN score from authored commits and reviews, with the PRs behind it</p>
          {p.experts.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Nobody has authored or reviewed real work here.</p>
          ) : (
            <ol className="mt-3 divide-y divide-line">
              {p.experts.map((e) => (
                <li key={e.person_id} className="py-2">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-medium text-ink">{e.name ?? e.person}</span>
                    {ownerIds.has(e.person_id) && <span className="rounded bg-accent-soft px-1.5 text-[11px] text-accent-ink">listed owner</span>}
                    <span className="ml-auto text-xs tabular-nums text-muted">score {e.score.toFixed(1)}</span>
                  </div>
                  <p className="text-xs text-muted">
                    {[e.commits && `${e.commits} commit${e.commits === 1 ? "" : "s"}`, e.reviews && `${e.reviews} review${e.reviews === 1 ? "" : "s"}`]
                      .filter(Boolean)
                      .join(" · ")}
                    {e.last_touch ? ` · last ${ago(e.last_touch)}` : ""}
                  </p>
                  {(e.evidence.length > 0 || e.evidence_reviews.length > 0) && (
                    <p className="mt-1 flex flex-wrap gap-1.5 text-xs">
                      {e.evidence.map((u) => (
                        <a key={u} href={u} target="_blank" rel="noreferrer" className="rounded bg-sunk px-1.5 py-0.5 text-ink-2 hover:text-accent">
                          {urlLabel(u)} ↗
                        </a>
                      ))}
                      {e.evidence_reviews.map((u) => (
                        <a key={u} href={u} target="_blank" rel="noreferrer" className="rounded bg-sunk px-1.5 py-0.5 text-muted hover:text-accent" title="reviewed">
                          reviewed {urlLabel(u)} ↗
                        </a>
                      ))}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section className="mt-4 rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-sm font-medium text-ink">Decisions on this module</h2>
        <p className="text-xs text-muted">
          {p.decisions.decisions.length} active · {p.decisions.pending_proposals.length} proposed · {p.decisions.history.length} superseded
        </p>
        {all.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No decisions were extracted from PRs, issues or ADRs that touch this module.</p>
        ) : (
          <ul className="mt-1 divide-y divide-line">
            {all.map((d) => (
              <Decision key={d.id} d={d} />
            ))}
          </ul>
        )}
      </section>

      <section className="mt-4 rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-sm font-medium text-ink">Usually changes together with</h2>
        <p className="text-xs text-muted">CO_CHANGED: modules touched in the same commits</p>
        {p.co_changed.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No other module changes in the same commits often enough to count.</p>
        ) : (
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {p.co_changed.map((c) => (
              <li key={c.module_id}>
                <Link
                  href={moduleHref(c.module_id, p.org)}
                  className="block rounded-lg border border-line px-3 py-2 transition-colors hover:border-accent/40"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="truncate font-mono text-sm text-ink">{shortLabel(c.module_id)}</span>
                    <span className="ml-auto shrink-0 text-xs tabular-nums text-muted">
                      {c.count} commits · {c.share_pct}%
                    </span>
                  </div>
                  {c.experts.length > 0 && <p className="truncate text-xs text-muted">knows it: {c.experts.map((e) => e.person).join(", ")}</p>}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <QueryToggle cypher={p.cypher} />
    </>
  );
}
