// Layered top-down layout for the evidence graph, computed with dagre and applied as preset
// positions in Cytoscape.
//
// Edges keep their real direction on screen; only the layout orients them, from a lower layer to
// a higher one: Decision on top, then the PR / doc it was decided in (and the modules it affects,
// beside it), then issues and people, then commits. So person -PROPOSED-> decision lays out as
// decision above person, beside the PR, and for "who" answers the module sits above its experts.
// Each node's box includes its label, so labels can't overlap.

import { Graph, layout } from "@dagrejs/dagre";
import { kindOf, type Kind } from "./nodes";

const LAYER: Partial<Record<Kind, number>> = {
  decision: 0, module: 1, codeowners: 1, pr: 1, doc: 1, topic: 1, issue: 2, person: 2, team: 2, commit: 3,
};

export type LayoutNode = { id: string; label: string; size: number };
export type LayoutEdge = { source: string; target: string };

const LABEL_MAX = 130; // px, matches text-max-width in the graph style
const CHAR_W = 6.3; // px per character at the 11px label size
const LABEL_H = 18;

export function layeredPositions(nodes: LayoutNode[], edges: LayoutEdge[]): Record<string, { x: number; y: number }> {
  const g = new Graph();
  g.setGraph({ rankdir: "TB", nodesep: 34, ranksep: 74, edgesep: 18, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) {
    const width = Math.max(n.size, Math.min(LABEL_MAX, n.label.length * CHAR_W)) + 14;
    g.setNode(n.id, { width, height: n.size + LABEL_H + 6 });
  }
  const seen = new Set<string>();
  for (const e of edges) {
    const [a, b] = (LAYER[kindOf(e.source)] ?? 1) > (LAYER[kindOf(e.target)] ?? 1) ? [e.target, e.source] : [e.source, e.target];
    const key = a < b ? `${a}|${b}` : `${b}|${a}`; // PR -CLOSES-> issue and issue -REFERENCES-> PR: one layout edge
    if (a === b || seen.has(key) || !g.hasNode(a) || !g.hasNode(b)) continue;
    seen.add(key);
    g.setEdge(a, b, { minlen: 1, weight: kindOf(a) === "decision" ? 2 : 1 });
  }
  layout(g);

  const out: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    const box = g.node(n.id);
    // dagre centres the whole box; Cytoscape's position is the shape's centre, label below it.
    out[n.id] = { x: box.x, y: box.y - box.height / 2 + n.size / 2 + 3 };
  }
  return out;
}
