// Suggested questions per org, from docs/golden_set.yaml (hand-checked answers).
export const EXAMPLES: Record<string, string[]> = {
  FalkorDB: [
    "Why did the Rust engine drop all_nodes_matrix?",
    "Why does the engine now fold MVCC deltas on every write?",
    "Who should I ask about indexes in the Rust engine?",
    "Who owns the query planner?",
    "Which parts of the engine depend on a single person?",
    "Why was Bolt support removed?",
  ],
  sandbox: [
    "Why do we cache links in Redis?",
    "Who owns analytics?",
    "Which modules depend on one person?",
    "What changed since I last asked?",
  ],
};
