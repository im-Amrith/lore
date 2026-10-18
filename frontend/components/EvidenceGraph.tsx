"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Core, ElementDefinition } from "cytoscape";
import Link from "next/link";
import { moduleHref, type AskResult } from "@/lib/api";
import { layeredPositions } from "@/lib/layout";
import { KIND_COLOR, KIND_NAME, kindOf, longLabel, shortLabel, type Kind } from "@/lib/nodes";

const SIZE_ON = 26;
const SIZE_OFF = 14;
const MAX_FIT_ZOOM = 1.3;

const SHAPE: Partial<Record<Kind, string>> = {
  decision: "round-diamond", pr: "round-rectangle", issue: "ellipse", person: "ellipse",
  module: "round-tag", doc: "round-rectangle", commit: "ellipse", team: "round-hexagon", codeowners: "round-tag",
};

/** The answer's subgraph. "Path" = the edges that touch a cited node (what the answer stands on). */
function elements(
  r: AskResult,
  showAll: boolean,
): { els: ElementDefinition[]; counts: Map<Kind, number>; positions: Record<string, { x: number; y: number }> } {
  const cited = new Set(r.citations.map((c) => c.id));
  const pathIds = new Set(r.path.map((e) => e.id));
  const onPath = new Set<string>([...cited]);
  r.path.forEach((e) => (onPath.add(e.source), onPath.add(e.target)));

  // By default: the walked path and the cited nodes, i.e. what the answer stands on plus the
  // nodes directly attached to it. "All" adds everything else the tools retrieved (other
  // search hits, READMEs, unrelated decisions and PRs).
  const shown = new Set<string>(onPath);
  if (showAll) {
    r.subgraph.edges.forEach((e) => (shown.add(e.source), shown.add(e.target)));
    r.subgraph.nodes.forEach((n) => shown.add(n));
  }
  shown.delete("codeowners");

  const counts = new Map<Kind, number>();
  const els: ElementDefinition[] = [];
  for (const id of shown) {
    const kind = kindOf(id);
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
    els.push({
      data: { id, label: shortLabel(id, r.labels), color: KIND_COLOR[kind], shape: SHAPE[kind] ?? "ellipse" },
      classes: [onPath.has(id) ? "on" : "off", cited.has(id) ? "cited" : ""].join(" "),
    });
  }
  const edges = r.subgraph.edges.filter((e) => shown.has(e.source) && shown.has(e.target));
  for (const e of edges) {
    els.push({
      data: { id: e.id, source: e.source, target: e.target, label: e.type.toLowerCase().replace(/_/g, " ") },
      classes: pathIds.has(e.id) ? "on" : "off",
    });
  }
  const positions = layeredPositions(
    [...shown].map((id) => ({ id, label: shortLabel(id, r.labels), size: onPath.has(id) ? SIZE_ON : SIZE_OFF })),
    edges,
  );
  return { els, counts, positions };
}

export function EvidenceGraph({
  result, focusId, onFocus,
}: {
  result: AskResult | null;
  focusId: string | null;
  onFocus: (id: string | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const built = useMemo(() => (result ? elements(result, showAll) : null), [result, showAll]);

  useEffect(() => {
    if (!box.current || !built) return;
    let disposed = false;
    import("cytoscape").then(({ default: cytoscape }) => {
      if (disposed || !box.current) return;
      cy.current?.destroy();
      const inst = cytoscape({
        container: box.current,
        elements: built.els,
        minZoom: 0.3,
        maxZoom: 2.5,
        wheelSensitivity: 0.25,
        style: [
          {
            selector: "node",
            style: {
              shape: "data(shape)" as never,
              "background-color": "data(color)",
              label: "data(label)",
              color: "#3d474e",
              "font-family": "Inter, system-ui, sans-serif",
              "font-size": 10,
              "text-valign": "bottom",
              "text-margin-y": 5,
              "text-wrap": "ellipsis",
              "text-max-width": "130px",
              width: SIZE_OFF,
              height: SIZE_OFF,
              opacity: 0.4,
            },
          },
          {
            selector: "node.on",
            style: {
              width: SIZE_ON, height: SIZE_ON, opacity: 1, "font-size": 11, color: "#1c2226",
              "border-width": 2, "border-color": "#fffefb",
              "text-background-color": "#fffefb", "text-background-opacity": 0.85, "text-background-padding": "2px",
            },
          },
          { selector: "node.cited", style: { "border-width": 3, "border-color": "#0e6e64" } },
          { selector: "node.focus", style: { "overlay-color": "#0e6e64", "overlay-opacity": 0.18, "overlay-padding": 8 } },
          {
            selector: "edge",
            style: {
              width: 1, "line-color": "#d6d0c4", "curve-style": "bezier",
              "target-arrow-shape": "triangle", "target-arrow-color": "#d6d0c4", "arrow-scale": 0.7,
            },
          },
          {
            selector: "edge.on",
            style: {
              width: 2.5, "line-color": "#0e6e64", "target-arrow-color": "#0e6e64", "arrow-scale": 1,
              label: "data(label)", "font-size": 9, color: "#0a524a", "text-rotation": "autorotate",
              "text-background-color": "#f6f4ef", "text-background-opacity": 1, "text-background-padding": "2px",
              "z-index": 10,
            },
          },
        ],
        layout: { name: "preset", positions: built.positions, fit: true, padding: 32 } as never,
      });
      // A short path would be fitted at a huge zoom; keep it at reading size, centred.
      if (inst.zoom() > MAX_FIT_ZOOM) {
        inst.zoom(MAX_FIT_ZOOM);
        inst.center();
      }
      inst.on("tap", "node", (e) => setPicked(e.target.id()));
      inst.on("tap", (e) => e.target === inst && setPicked(null));
      inst.on("mouseover", "node", (e) => onFocus(e.target.id()));
      inst.on("mouseout", "node", () => onFocus(null));
      cy.current = inst;
    });
    return () => {
      disposed = true;
    };
    // onFocus is a state setter: stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [built]);

  useEffect(() => () => cy.current?.destroy(), []);
  useEffect(() => setPicked(null), [result]);

  // Hovering a citation in the answer lights its node here.
  useEffect(() => {
    const inst = cy.current;
    if (!inst) return;
    inst.nodes().removeClass("focus");
    if (focusId) inst.getElementById(focusId).addClass("focus");
  }, [focusId, built]);

  if (!result) {
    return (
      <div className="flex h-full items-center justify-center p-10 text-center text-sm text-muted">
        <p className="max-w-xs leading-relaxed">
          The evidence path appears here: the decisions, pull requests, issues and people an answer was traced
          through, with the walked path drawn in <span className="font-medium text-accent">teal</span>.
        </p>
      </div>
    );
  }

  const url = picked ? result.sources?.[picked] ?? result.citations.find((c) => c.id === picked)?.url : null;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-line px-4 py-2 text-xs text-muted">
        <span className="font-medium text-ink-2">Evidence path</span>
        <span>
          {result.path.length} edge{result.path.length === 1 ? "" : "s"} walked · {result.citations.length} cited
        </span>
        <label className="ml-auto flex cursor-pointer items-center gap-1.5">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-accent" />
          all retrieved nodes
        </label>
        <button
          onClick={() => {
            const inst = cy.current;
            if (!inst) return;
            inst.fit(undefined, 32);
            if (inst.zoom() > MAX_FIT_ZOOM) {
              inst.zoom(MAX_FIT_ZOOM);
              inst.center();
            }
          }}
          className="rounded px-1.5 py-0.5 hover:bg-sunk hover:text-ink">
          Fit
        </button>
      </div>
      <div ref={box} className="min-h-0 flex-1" role="img" aria-label="Graph of the nodes and edges this answer walked" />
      <div className="flex min-h-11 items-center gap-3 border-t border-line px-4 py-2 text-xs">
        {picked ? (
          <>
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: KIND_COLOR[kindOf(picked)] }} />
            <span className="font-medium text-ink">{shortLabel(picked, result.labels)}</span>
            <span className="truncate text-muted">{longLabel(picked, result.labels) ?? KIND_NAME[kindOf(picked)]}</span>
            {kindOf(picked) === "module" && (
              <Link href={moduleHref(picked, result.org)} className="ml-auto shrink-0 font-medium text-accent hover:underline">
                Module page →
              </Link>
            )}
            {url && (
              <a href={url} target="_blank" rel="noreferrer" className={`${kindOf(picked) === "module" ? "" : "ml-auto "}shrink-0 font-medium text-accent hover:underline`}>
                Open on GitHub ↗
              </a>
            )}
          </>
        ) : (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted">
            {[...(built?.counts ?? new Map()).entries()].map(([k, n]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR[k as Kind] }} />
                {KIND_NAME[k as Kind]} {n}
              </span>
            ))}
            <span className="text-muted/80">· click a node for its source</span>
          </div>
        )}
      </div>
    </div>
  );
}
