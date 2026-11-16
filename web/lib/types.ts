// Mirrors app/retrieval/models.py, app/ingestion/models.py, and app/generation/models.py.
// Keep in sync with those Pydantic models — this file has no build-time link to them.

export type ChatRole = "user" | "assistant";

export interface ChatTurn {
  role: ChatRole;
  content: string;
}

export interface SearchHit {
  chunk_id: string;
  source_url: string;
  title: string | null;
  page_number: number | null;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface PolicyGateResult {
  passed: boolean;
  violations: string[];
}

export interface GenerationResult {
  query: string;
  in_scope: boolean;
  // "in_scope": grounded in retrieved documents. "general_finance": answered from the
  // LLM's own knowledge, no retrieval or sources. "courtesy" / "out_of_scope": the
  // router's short reply.
  route: "in_scope" | "general_finance" | "courtesy" | "out_of_scope";
  answer: string;
  sources: SearchHit[];
  policy: PolicyGateResult | null;
  // Authoritative next-turn conversation state: resend these verbatim as `history` /
  // `history_summary` on the next request instead of replaying the full on-screen
  // transcript — the backend has already capped `history` and folded anything older
  // into `history_summary` (see app/generation/memory.py). Already includes this turn's
  // query + answer.
  history: ChatTurn[];
  history_summary: string | null;
}

export interface QueryRequest {
  query: string;
  history?: ChatTurn[];
  history_summary?: string | null;
  provider?: string;
  model?: string;
}

// One entry in the on-screen conversation. Extends the wire ChatTurn with everything
// the UI needs to render an assistant turn's citations/warnings/timing, and to show a
// pending or failed turn before/without a GenerationResult ever arriving.
export interface ConversationMessage extends ChatTurn {
  id: string;
  result?: GenerationResult;
  latencyMs?: number;
  error?: string;
  // Set when `error` is specifically "couldn't reach the API" (as opposed to a request
  // the backend received but rejected) — lets the UI show a distinct, retryable card
  // instead of a generic error line.
  errorKind?: "offline";
  pending?: boolean;
}

export const PROVIDERS = ["default", "ollama", "openai", "anthropic"] as const;
export type Provider = (typeof PROVIDERS)[number];
