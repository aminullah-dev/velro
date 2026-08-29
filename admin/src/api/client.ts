/**
 * The API client.
 *
 * One envelope shape for every response, success or failure. Errors carry a
 * stable code and a structured context, never a rendered sentence -- the panel
 * resolves the code to a message in the locale the operator is reading, exactly
 * as both mobile apps do.
 */

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  message: string | null;
  meta: Record<string, unknown>;
}

export interface ApiErrorBody {
  code: string;
  message_key?: string;
  context?: Record<string, unknown>;
  request_id?: string | null;
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly httpStatus: number,
    readonly context: Record<string, unknown> = {},
    readonly requestId: string | null = null,
  ) {
    super(`${code} (HTTP ${httpStatus})`);
    this.name = "ApiError";
  }

  static offline() {
    return new ApiError("NETWORK_OFFLINE", 0);
  }

  get isAuthFailure() {
    return ["TOKEN_INVALID", "TOKEN_EXPIRED", "REFRESH_TOKEN_REVOKED"].includes(this.code);
  }
}

const BASE = "/api/v1";
const ACCESS_KEY = "velro.access";
const REFRESH_KEY = "velro.refresh";

export const session = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  save(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  get isSignedIn() {
    return Boolean(localStorage.getItem(ACCESS_KEY));
  },
};

/** Notified when the session ends, so the shell can return to sign-in. */
type Listener = () => void;
const signedOutListeners = new Set<Listener>();
export function onSignedOut(listener: Listener): () => void {
  signedOutListeners.add(listener);
  // Returns void, not the Set's boolean: this is used directly as a React
  // effect cleanup, which must not return a value.
  return () => {
    signedOutListeners.delete(listener);
  };
}

let refreshing: Promise<boolean> | null = null;

/**
 * Refresh once, and share the attempt.
 *
 * A dashboard fires several requests at once; without this they would each
 * start their own refresh and all but one would be rotated out from under the
 * others.
 */
async function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing;
  const token = session.refresh;
  if (!token) return false;

  refreshing = (async () => {
    try {
      const response = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!response.ok) return false;
      const body = (await response.json()) as Envelope<{
        access_token: string;
        refresh_token: string;
      }>;
      if (!body.data) return false;
      session.save(body.data.access_token, body.data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();

  return refreshing;
}

async function toError(response: Response): Promise<ApiError> {
  let body: { error?: ApiErrorBody } | null = null;
  try {
    body = await response.json();
  } catch {
    // A response that is not JSON at all -- a proxy error page, usually.
    return new ApiError("INTERNAL_ERROR", response.status);
  }
  const error = body?.error;
  if (!error) return new ApiError("INTERNAL_ERROR", response.status);
  return new ApiError(
    error.code,
    response.status,
    error.context ?? {},
    error.request_id ?? null,
  );
}

async function send<T>(
  path: string,
  init: RequestInit,
  retryOnAuthFailure = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  const token = session.access;
  if (token) headers.set("authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    // No network at all. Distinct from a server error, and the banner says so.
    throw ApiError.offline();
  }

  if (response.status === 401 && retryOnAuthFailure) {
    if (await refreshSession()) return send<T>(path, init, false);
    session.clear();
    signedOutListeners.forEach((listener) => listener());
    throw new ApiError("TOKEN_EXPIRED", 401);
  }

  if (!response.ok) throw await toError(response);

  const body = (await response.json()) as Envelope<T>;
  if (body.data === null || body.data === undefined) {
    throw new ApiError("INTERNAL_ERROR", response.status);
  }
  return body.data;
}

/** Same as [send], but keeps `meta` -- pagination totals live there. */
async function sendWithMeta<T>(path: string): Promise<{ data: T; meta: Record<string, unknown> }> {
  const headers = new Headers({ "content-type": "application/json" });
  const token = session.access;
  if (token) headers.set("authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { headers });
  } catch {
    throw ApiError.offline();
  }
  if (response.status === 401) {
    if (await refreshSession()) return sendWithMeta<T>(path);
    session.clear();
    signedOutListeners.forEach((listener) => listener());
    throw new ApiError("TOKEN_EXPIRED", 401);
  }
  if (!response.ok) throw await toError(response);

  const body = (await response.json()) as Envelope<T>;
  return { data: (body.data ?? []) as T, meta: body.meta ?? {} };
}

export const api = {
  get: <T>(path: string) => send<T>(path, { method: "GET" }),
  list: <T>(path: string) => sendWithMeta<T>(path),
  post: <T>(path: string, body?: unknown) =>
    send<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    send<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};

export function query(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}
