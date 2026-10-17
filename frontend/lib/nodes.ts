// Node ids follow CLAUDE.md: pr:<owner>/<repo>#<n>, issue:..., person:<login>, person:name:<slug>,
// module:<repo>:<path>, decision:<hash>, doc:..., chunk:..., commit:<sha>, team:<org>/<slug>.

export type Kind =
  | "decision" | "pr" | "issue" | "person" | "module" | "doc" | "commit" | "team" | "topic" | "codeowners" | "other";

export function kindOf(id: string): Kind {
  if (id === "codeowners") return "codeowners";
  const prefix = id.split(":", 1)[0];
  if (prefix === "chunk") return "doc";
  return (["decision", "pr", "issue", "person", "module", "doc", "commit", "team", "topic"] as const).includes(
    prefix as never,
  )
    ? (prefix as Kind)
    : "other";
}

export const KIND_NAME: Record<Kind, string> = {
  decision: "Decision", pr: "Pull request", issue: "Issue", person: "Person", module: "Module", doc: "Doc",
  commit: "Commit", team: "Team", topic: "Topic", codeowners: "CODEOWNERS", other: "Node",
};

// Muted, distinguishable hues; the walked path itself is drawn in the accent.
export const KIND_COLOR: Record<Kind, string> = {
  decision: "#0e6e64", pr: "#4a5c9e", issue: "#8a4f80", person: "#9a6a1c", module: "#4d6b4f",
  doc: "#6b7280", commit: "#8b8478", team: "#9a6a1c", topic: "#6b7280", codeowners: "#4d6b4f", other: "#8b8478",
};

const titleCase = (s: string) => s.replace(/(^|[-\s])(\w)/g, (_, sep, c) => (sep ? " " : "") + c.toUpperCase());

/** The short name of a node: "PR #2678", "Issue #1", "AviAvni", "Priya Raman", "graph/src/parser". */
export function shortLabel(id: string, labels?: Record<string, string>): string {
  const kind = kindOf(id);
  const num = id.match(/#(\d+)$/)?.[1];
  switch (kind) {
    case "pr":
      return `PR #${num}`;
    case "issue":
      return `Issue #${num}`;
    case "person":
      return id.startsWith("person:name:") ? titleCase(id.slice("person:name:".length)) : id.slice("person:".length);
    case "module": {
      const path = id.split(":").slice(2).join(":");
      return path === "/" ? `${id.split(":")[1]} (root)` : path;
    }
    case "team":
      return "@" + id.slice("team:".length);
    case "commit":
      return id.slice("commit:".length, "commit:".length + 7);
    case "codeowners":
      return "CODEOWNERS";
    case "doc":
      return (id.split(":").slice(2).join(":") || id).replace(/#\d+$/, "");
    case "decision":
      return labels?.[id] ? truncate(labels[id], 34) : "Decision";
    default:
      return labels?.[id] ? truncate(labels[id], 34) : id;
  }
}

/** The longer description shown next to a source: the PR title, the decision statement. */
export function longLabel(id: string, labels?: Record<string, string>): string | null {
  const l = labels?.[id];
  if (!l) return null;
  return l === shortLabel(id, labels) ? null : l;
}

export const truncate = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
