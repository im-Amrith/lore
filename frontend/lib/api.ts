// Client for the Lore API (backend/lore/api/app.py). Shapes match docs/api_examples/.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Edge = { id: string; source: string; type: string; target: string };

export type Sentence = { text: string; cites: string[]; pending?: boolean };

export type Citation = { n: number; id: string; url: string | null };

export type LlmCall = {
  model?: string;
  endpoint?: string;
  prompt_tokens?: number | null;
  seconds?: number | null;
  cached?: boolean;
};

export type CypherRun = {
  tool: string;
  query: string;
  cypher: string;
  params: Record<string, unknown>;
  rows: number;
};

export type AskResult = {
  question: string;
  org: string;
  user: string;
  intent: string;
  found: boolean;
  not_found: string;
  answer: string;
  sentences: Sentence[];
  citations: Citation[];
  subgraph: { nodes: string[]; edges: Edge[] };
  path: Edge[];
  cypher: CypherRun[];
  tool_calls: { tool: string; args: Record<string, unknown>; error: string | null }[];
  llm_calls: LlmCall[];
  dropped: { text: string; cites: string[] }[];
  seconds: number;
  answer_cache?: boolean | null;
  // Added for the UI; older cached answers may lack them.
  sources?: Record<string, string>;
  labels?: Record<string, string>;
  decision_status?: Record<string, string>;
};

export type ProgressEvent =
  | { type: "tool"; n: number; tool: string; args: Record<string, unknown> }
  | { type: "llm"; step: string }
  | { type: "llm_done"; step: string; endpoint?: string; seconds?: number; cached?: boolean }
  | { type: "cache" };

export type User = { id: string; github_login: string | null; questions: number; last_asked: number | null };

export type Health = {
  orgs: Record<string, { graph: string; data_version?: string; missing?: boolean }>;
  sandbox_repo: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => fetch(`${API_URL}/health`).then((r) => json<Health>(r));

export const getUsers = () => fetch(`${API_URL}/users`).then((r) => json<{ users: User[] }>(r)).then((b) => b.users);

export const createUser = (id: string, github_login?: string) =>
  fetch(`${API_URL}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, github_login: github_login || null }),
  }).then((r) => json<{ id: string }>(r));

/** POST /ask/stream: calls onEvent for each progress line, resolves with the answer. */
export async function askStream(
  body: { org: string; user: string; question: string },
  onEvent: (e: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<AskResult> {
  const res = await fetch(`${API_URL}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) await json(res); // throws ApiError with the server's detail
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffer += value;
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === "answer") return event.data as AskResult;
      if (event.type === "error") throw new ApiError(event.status, event.detail);
      onEvent(event as ProgressEvent);
    }
    if (done) throw new ApiError(502, "the answer stream ended early");
  }
}

// ---------------------------------------------------------------- Triage inbox (M13)

export type Link = { id: string | null; url: string };

export type TriagePerson = {
  id: string;
  name: string;
  login: string | null;
  mention: string;
  why?: string;
  evidence?: Link[];
  text?: string;
};

export type TriageFacts = {
  issue: { id: string; number: number; title: string; url: string } | null;
  related_issues: {
    id: string;
    number: number;
    title: string;
    url: string;
    state: string;
    distance: number;
    duplicate: boolean;
    fixed_by: Link[];
  }[];
  likely_duplicates: { id: string; number: number }[];
  module: { id: string; path: string | null } | null;
  decision_behind_fix: { id: string; statement: string; rationale: string | null; source_id: string; url: string | null } | null;
  pending_proposals: { id: string; statement: string; source_id: string; url: string | null }[];
  suggested_owner: TriagePerson | null;
  paper_owner_warnings: TriagePerson[];
  suggested_reviewer: TriagePerson | null;
  codeowners_url: string | null;
  tool_calls: { tool: string; args: Record<string, unknown>; queries: string[] }[];
  rejected_links: string[];
  playbook_steps: string[];
};

export type TriageItem = {
  task_id: string;
  status: "open" | "claimed" | "drafted" | "approved";
  opened_at: number | null;
  claimed_by: string | null;
  draft: string | null;
  facts: TriageFacts | null;
  playbook_version: number | null;
  drafted_by: string | null;
  drafted_at: number | null;
  model: string | null;
  error: string | null;
  attempts: number | null;
  approved_draft: string | null;
  approved_by: string | null;
  approved_at: number | null;
  posted: boolean | null;
  dry_run: boolean | null;
  comment_url: string | null;
  issue_id: string;
  number: number;
  title: string;
  url: string;
  issue_state: string;
  body: string;
};

export type TriageInbox = {
  org: string;
  repo: string;
  items: TriageItem[];
  dry_run: boolean;
  poll_seconds: number;
  steward: {
    agent: string;
    last_tick: { at: number; loaded: string[]; opened: string[]; drafted: { task_id: string; status: string; error?: string }[] } | null;
    last_error: string | null;
  };
  cypher: CypherRun[];
};

export type Playbook = {
  name: string;
  steps: string[];
  version: number;
  feedback: { id: string; text: string; rule: string; at: number; by: string; task_id: string }[];
};

export type ApproveResult = {
  task: { task_id: string; status: string; posted: boolean; dry_run: boolean; comment_url: string | null };
  post: { dry_run: boolean; posted: boolean; comment_url?: string; would_post_to?: string; issue_url: string };
  feedback: { id: string; rule: string; learned: boolean; playbook_version: number; steps: string[] } | null;
};

const post = (path: string, body?: unknown) =>
  fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

// The API takes a sandbox issue number for a Task (POST /triage/9/approve).
const taskPath = (issueNumber: number) => String(issueNumber);

export const getTriage = () => fetch(`${API_URL}/triage`).then((r) => json<TriageInbox>(r));

export const getPlaybook = () => fetch(`${API_URL}/playbook`).then((r) => json<Playbook>(r));

export const syncTriage = () => post("/triage/sync").then((r) => json<unknown>(r));

export const redraftTask = (issueNumber: number) =>
  post(`/triage/${taskPath(issueNumber)}/redraft`).then((r) => json<unknown>(r));

export const approveTask = (issueNumber: number, body: { user: string; draft: string; rule?: string; passcode: string }) =>
  post(`/triage/${taskPath(issueNumber)}/approve`, body).then((r) => json<ApproveResult>(r));

// ---------------------------------------------------------------- Module page and risk map (M12)

export type DecisionRow = {
  id: string;
  statement: string;
  status: "active" | "superseded" | "proposed" | string;
  kind: string | null;
  confidence?: number;
  source_id?: string;
  source_url: string | null;
  superseded_by?: string | null;
};

export type ExpertRow = {
  person_id: string;
  person: string;
  name: string | null;
  score: number;
  authored: number;
  reviewed: number;
  commits: number | null;
  reviews: number | null;
  last_touch: number | null;
  evidence: string[];
  evidence_reviews: string[];
};

/** A CODEOWNERS owner; paper = listed but hasn't worked on the module lately. */
export type OwnerRef = { id: string; kind: "Person" | "Team" | string; name: string; members: number; paper: boolean };

export type ModulePage = {
  org: string;
  module: { id: string; path: string; repo: string; rank?: number; activity?: number };
  owners: {
    listed_owner: boolean;
    owners: OwnerRef[];
    paper_owners: string[];
    active_experts: { id: string; person: string; score: number; evidence: string[] }[];
    top_expert_is_owner: boolean | null;
    mismatch: boolean;
    codeowners_url: string | null;
    message?: string;
  };
  experts: ExpertRow[];
  decisions: { decisions: DecisionRow[]; pending_proposals: DecisionRow[]; history: DecisionRow[] };
  co_changed: {
    module_id: string;
    module: string;
    count: number;
    share_pct: number;
    experts: { id: string; person: string; score: number }[];
    decisions: DecisionRow[];
  }[];
  sources: Record<string, string>;
  cypher: CypherRun[];
};

export type RiskModule = {
  module_id: string;
  module: string;
  bus_factor: number;
  experts: string[];
  expert_ids: string[];
  share_pct: number[];
  total_score: number;
  owners?: string[];
  owner_not_expert?: boolean;
  single_expert: boolean;
};

export type RiskPage = {
  org: string;
  repo: string | null;
  modules: RiskModule[];
  single_expert_modules: string[];
  single_expert_not_owner?: string[];
  dormant_modules: number;
  bridge_people: { person: string; id: string; score: number }[];
  working_groups: { group_id: number; size: number; members: string[]; member_ids: string[] }[];
  thresholds: { min_score: number; min_share: number; window_days: number };
  cypher: CypherRun[];
};

export const getModule = (id: string, org?: string) =>
  fetch(`${API_URL}/module/${id.split("/").map(encodeURIComponent).join("/")}${org ? `?org=${encodeURIComponent(org)}` : ""}`).then(
    (r) => json<ModulePage>(r),
  );

export const getRisk = (org: string) => fetch(`${API_URL}/risk?org=${encodeURIComponent(org)}`).then((r) => json<RiskPage>(r));

/** The UI route for a module id: module:<repo>:<path> -> /module/<repo>/<path>?org=<org>. */
export function moduleHref(id: string, org?: string): string {
  const [, repo, ...rest] = id.split(":");
  const path = rest.join(":").replace(/^\/$/, "");
  return `/module/${[repo, ...path.split("/").filter(Boolean)].map(encodeURIComponent).join("/")}${org ? `?org=${encodeURIComponent(org)}` : ""}`;
}
