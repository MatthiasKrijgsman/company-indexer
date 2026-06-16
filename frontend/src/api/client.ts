// Tiny fetch wrapper. All API routes live under /companies and are reached
// same-origin via the Vite dev proxy (see vite.config.ts), so paths are
// relative — no base URL or CORS needed.

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      headers: { Accept: "application/json", ...init?.headers },
      ...init,
    });
  } catch (e) {
    // Network-level failure (API not running, proxy down, etc.).
    throw new ApiError(0, e instanceof Error ? e.message : "Network error");
  }

  if (!res.ok) {
    // FastAPI errors are { detail: ... }. Fall back to status text.
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON body — keep status text */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
