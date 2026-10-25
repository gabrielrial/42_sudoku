// The only module that knows the shape of the API. Everything else imports
// from here, so an endpoint change has one place to land.
//
// Sessions (DECISIONS.md D15): a 15-minute access cookie and a rotating
// refresh cookie, both HttpOnly, so this code never sees a token. A request
// answered `401` refreshes once and is retried once; if the refresh fails too,
// the session is over and every `onSignedOut` listener hears about it.

const BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

/** Where the browser is sent to sign in: a navigation, never a `fetch`. */
export const LOGIN_URL = `${BASE}/auth/login`;

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Runs `task` while no other holder of the lock runs. */
export type Lock = <T>(task: () => Promise<T>) => Promise<T>;

/**
 * One refresh at a time across every tab of this site. Tabs share the
 * cookies, so two refreshes at once would present the same refresh token,
 * and the second looks exactly like theft: the server signs the user out
 * (D15). Serialised, the second tab's refresh sends the cookie the first one
 * just received, which is an ordinary rotation.
 */
function browserLock<T>(task: () => Promise<T>): Promise<T> {
  if (typeof navigator === "undefined" || !navigator.locks) return task();
  // The lock is held until `task` settles; `request` resolves to its result.
  return navigator.locks.request("sudoku42-refresh", task) as Promise<T>;
}

export interface ClientOptions {
  fetch?: typeof fetch;
  lock?: Lock;
  base?: string;
}

export interface Me {
  login: string;
  campus_name: string;
}

export interface Health {
  status: string;
  date: string;
}

export function createClient({
  fetch: send = (input, init) => fetch(input, init),
  lock = browserLock,
  base = BASE,
}: ClientOptions = {}) {
  const signedOutListeners = new Set<() => void>();
  // One refresh in flight in this tab, awaited by every request that hit a
  // 401 meanwhile; the lock does the same across tabs.
  let refreshing: Promise<boolean> | null = null;

  function call(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    return send(`${base}${path}`, { ...init, headers, credentials: "include" });
  }

  function refresh(): Promise<boolean> {
    refreshing ??= lock(async () => (await call("/auth/refresh", { method: "POST" })).ok).finally(
      () => {
        refreshing = null;
      },
    );
    return refreshing;
  }

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response = await call(path, init);
    if (response.status === 401) {
      // Once, and never for the session endpoints themselves: no loops.
      if (!path.startsWith("/auth/") && (await refresh())) response = await call(path, init);
      if (response.status === 401) signedOutListeners.forEach((listener) => listener());
    }
    return read<T>(response);
  }

  return {
    /** Called whenever the API says the session is over. Returns an unsubscribe. */
    onSignedOut(listener: () => void): () => void {
      signedOutListeners.add(listener);
      return () => signedOutListeners.delete(listener);
    },
    request,
    getHealth: () => request<Health>("/health"),
    /** The signed-in user; `401 not_authenticated` when nobody is. */
    getMe: () => request<Me>("/users/me"),
    logout: () => request<void>("/auth/logout", { method: "POST" }),
  };
}

async function read<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = "unknown_error";
    let message = response.statusText;
    try {
      const body = (await response.json()) as ApiErrorBody;
      code = body.error.code;
      message = body.error.message;
    } catch {
      // Not every failure carries the envelope (a proxy 502, say).
    }
    throw new ApiError(code, response.status, message);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** The application's client. Tests build their own with `createClient`. */
export const api = createClient();
