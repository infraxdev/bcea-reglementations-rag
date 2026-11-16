import type { GenerationResult, QueryRequest } from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function postQuery(
  req: QueryRequest,
  signal?: AbortSignal,
): Promise<GenerationResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ApiError(
      0,
      `Can't reach the API at ${API_BASE_URL}. Is the backend running?`,
    );
  }

  if (!response.ok) {
    // FastAPI's HTTPException body is {"detail": "..."}; fall back to the raw
    // response text if the body isn't the shape we expect.
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body, keep statusText
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as GenerationResult;
}
