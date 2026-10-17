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
