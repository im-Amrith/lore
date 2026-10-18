"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Header, type Org } from "@/components/Header";
import { Empty, ErrorBox, Loading, QueryToggle, useUser } from "@/components/States";
import { getHealth, getRisk, moduleHref, type RiskModule, type RiskPage } from "@/lib/api";
import { shortLabel } from "@/lib/nodes";

// Bus factor 1 = one person away from nobody knowing it; 0 = nobody has authored a real share lately.
const BANDS = [
  { key: "none", label: "0 · no recent expert", box: "border-line bg-sunk", num: "text-muted" },
  { key: "one", label: "1", box: "border-miss-line bg-miss-soft", num: "text-miss" },
  { key: "two", label: "2", box: "border-pending-line bg-pending-soft", num: "text-pending" },
  { key: "more", label: "3+", box: "border-accent/25 bg-accent-soft", num: "text-accent-ink" },
] as const;

const band = (m: RiskModule) => BANDS[Math.min(m.bus_factor, 3)];


function Tile({ m, org }: { m: RiskModule; org: string }) {
  const t = band(m);
  return (
    <Link
      href={moduleHref(m.module_id, org)}
      className={`flex min-w-0 flex-col rounded-lg border px-3 py-2.5 transition-shadow hover:shadow-[0_6px_18px_-10px_#1c22264d] ${t.box}`}
      title={`Bus factor ${m.bus_factor}: ${m.experts.join(", ")}`}
    >
      <div className="flex items-baseline gap-2">
        <span className="truncate font-mono text-[13px] text-ink">{shortLabel(m.module_id)}</span>
        <span className={`ml-auto shrink-0 text-lg font-semibold tabular-nums ${t.num}`}>{m.bus_factor}</span>
      </div>
      <span className={`truncate text-xs ${m.bus_factor ? "text-ink-2" : "text-muted"}`}>
        {m.bus_factor === 0 && "no recent expert"}
        {m.experts.map((e, i) => `${e}${m.share_pct[i] != null ? ` ${m.share_pct[i]}%` : ""}`).join(", ")}
      </span>
      {m.owner_not_expert && m.owners?.length ? (
        <span className="mt-0.5 truncate text-[11px] text-miss">listed owner: {m.owners.join(", ")}</span>
      ) : null}
    </Link>
  );
}

export function RiskView({ initialOrg }: { initialOrg?: string }) {
  const router = useRouter();
  const [user, setUser] = useUser();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [org, setOrg] = useState<string>(initialOrg ?? "");
  const [risk, setRisk] = useState<RiskPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then((h) => {
        const sandboxOwner = h.sandbox_repo?.split("/")[0];
        const list = Object.keys(h.orgs).map((id) => ({ id, label: id === sandboxOwner ? h.sandbox_repo.split("/")[1] ?? id : id }));
        setOrgs(list);
        setOrg((o) => list.find((x) => x.id.toLowerCase() === o.toLowerCase())?.id ?? list[0]?.id ?? "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const load = useCallback(() => {
    if (!org) return;
    setError(null);
    setRisk(null);
    getRisk(org)
      .then(setRisk)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [org]);

  useEffect(load, [load]);

  function chooseOrg(id: string) {
    setOrg(id);
    router.replace(`/risk?org=${encodeURIComponent(id)}`, { scroll: false });
  }

  const all = risk?.modules ?? [];
  const flagged = all.filter((m) => m.single_expert && m.owner_not_expert);
  const rest = all.filter((m) => m.bus_factor > 0 && !(m.single_expert && m.owner_not_expert));
  const dormant = all.filter((m) => m.bus_factor === 0);
  const counts = BANDS.map((b) => ({ ...b, n: all.filter((m) => band(m).key === b.key).length }));
  const maxBridge = Math.max(1, ...(risk?.bridge_people ?? []).map((b) => b.score));

  return (
    <div className="flex min-h-dvh flex-col">
      <Header orgs={orgs} org={org} onOrg={chooseOrg} user={user} onUser={setUser} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-5">
        <h1 className="font-serif text-[26px] leading-tight text-ink">Knowledge risk</h1>
        <p className="mt-1 text-sm text-muted">
          Bus factor per module: how many people have authored a real share of it in the last{" "}
          {risk?.thresholds.window_days ?? 180} days. Click a module to see who owns it on paper and who actually knows it.
        </p>

        <div className="mt-5">
          {error ? (
            <ErrorBox title="Can't load the risk map." message={error} onRetry={load} />
          ) : !risk ? (
            <Loading what="Running bus factor, betweenness and label propagation…" rows={3} />
          ) : risk.modules.length === 0 ? (
            <Empty title="No module has recent enough work to measure.">
              {risk.dormant_modules > 0 && `${risk.dormant_modules} modules are dormant: nobody authored a real share in the window.`}
            </Empty>
          ) : (
            <>
              {flagged.length > 0 && (
                <section aria-labelledby="flagged">
                  <h2 id="flagged" className="text-sm font-medium text-miss">
                    Single expert isn&rsquo;t the listed owner ({flagged.length})
                  </h2>
                  <p className="text-xs text-muted">One person holds the knowledge, and CODEOWNERS points somewhere else.</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {flagged.map((m) => (
                      <Tile key={m.module_id} m={m} org={risk.org} />
                    ))}
                  </div>
                </section>
              )}

              {rest.length > 0 && (
                <section aria-labelledby="modules" className={flagged.length ? "mt-6" : ""}>
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <h2 id="modules" className="text-sm font-medium text-ink">
                      {flagged.length ? "Other modules" : "Modules"}
                    </h2>
                    <span className="flex flex-wrap items-center gap-3 text-xs text-muted">
                      {counts.map((b) => (
                        <span key={b.key} className="flex items-center gap-1">
                          <span className={`h-2.5 w-2.5 rounded-sm border ${b.box}`} /> {b.label}: {b.n}
                        </span>
                      ))}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {rest.map((m) => (
                      <Tile key={m.module_id} m={m} org={risk.org} />
                    ))}
                  </div>
                </section>
              )}
              {dormant.length > 0 && (
                <section aria-labelledby="dormant" className="mt-6">
                  <h2 id="dormant" className="text-sm font-medium text-ink">
                    No recent expert ({dormant.length})
                  </h2>
                  <p className="text-xs text-muted">Nobody has authored a real share of these in the window; the code is there, the knowledge has gone quiet.</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {dormant.map((m) => (
                      <Tile key={m.module_id} m={m} org={risk.org} />
                    ))}
                  </div>
                </section>
              )}

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <section className="rounded-xl border border-line bg-surface px-5 py-4">
                  <h2 className="text-sm font-medium text-ink">Bridge people</h2>
                  <p className="text-xs text-muted">Betweenness on COLLABORATES: who connects groups that otherwise don&rsquo;t talk</p>
                  {risk.bridge_people.length === 0 ? (
                    <p className="mt-3 text-sm text-muted">Too few collaborations in this graph to find bridges.</p>
                  ) : (
                    <ol className="mt-3 space-y-2">
                      {risk.bridge_people.map((b) => (
                        <li key={b.id} className="text-sm">
                          <div className="flex items-baseline">
                            <span className="text-ink">{b.person}</span>
                            <span className="ml-auto text-xs tabular-nums text-muted">{b.score.toFixed(1)}</span>
                          </div>
                          <div className="mt-1 h-1.5 rounded-full bg-sunk">
                            <div className="h-1.5 rounded-full bg-accent" style={{ width: `${(100 * b.score) / maxBridge}%` }} />
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>

                <section className="rounded-xl border border-line bg-surface px-5 py-4">
                  <h2 className="text-sm font-medium text-ink">Working groups</h2>
                  <p className="text-xs text-muted">Label propagation on COLLABORATES: people who review each other&rsquo;s work</p>
                  {risk.working_groups.length === 0 ? (
                    <p className="mt-3 text-sm text-muted">No working groups found in this graph.</p>
                  ) : (
                    <ul className="mt-3 space-y-3">
                      {risk.working_groups.map((g) => (
                        <li key={g.group_id}>
                          <p className="text-xs text-muted">{g.size} people</p>
                          <p className="mt-1 flex flex-wrap gap-1.5">
                            {g.members.map((name) => (
                              <span key={name} className="rounded bg-sunk px-1.5 py-0.5 text-xs text-ink-2">
                                {name}
                              </span>
                            ))}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>

              <QueryToggle cypher={risk.cypher} />
            </>
          )}
        </div>
      </main>
    </div>
  );
}
