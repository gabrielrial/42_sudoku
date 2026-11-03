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
  error: { code: string; message: string; [field: string]: unknown };
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
    /** The envelope's other fields, e.g. the `game_id` of a `409` (API.md). */
    readonly details: Readonly<Record<string, unknown>> = {},
    /** A `429`'s `Retry-After`: whole seconds until a retry can succeed. */
    readonly retryAfterSeconds: number | null = null,
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
export function browserLock<T>(task: () => Promise<T>): Promise<T> {
  // Web Locks exist only in a secure context (HTTPS, or localhost). Without
  // them, refreshes are serialised within each tab only (D15, PLAN.md P2).
  if (typeof navigator === "undefined" || !navigator.locks) return task();
  // The lock is held until `task` settles; `request` resolves to its result.
  return navigator.locks.request("sudoku42-refresh", task) as Promise<T>;
}

export interface ClientOptions {
  fetch?: typeof fetch;
  lock?: Lock;
  base?: string;
  timeoutMs?: number;
}

/** A request with no answer by then is given up: a half-open connection on a
 * phone would otherwise hold everything queued behind it. */
export const REQUEST_TIMEOUT_MS = 15_000;

export interface Me {
  login: string;
  campus_name: string;
}

export interface Health {
  status: string;
  date: string;
}

export type Difficulty = "easy" | "medium" | "hard";

/** One difficulty of today, from the caller's side. Never its cells (Q13). */
export interface TodayPuzzle {
  difficulty: Difficulty;
  status: "not_started" | "in_progress" | "completed";
  game_id: string | null;
  official_seconds: number | null;
  active_seconds: number | null;
}

/** A game of an earlier day, still open past midnight. */
export interface ContinuingGame {
  game_id: string;
  difficulty: Difficulty;
  date: string;
}

export interface Today {
  date: string;
  puzzles: TodayPuzzle[];
  continuing: ContinuingGame[];
}

export interface GameStarted {
  game_id: string;
  difficulty: Difficulty;
  date: string;
  givens: string;
  state: string;
  started_at: string;
}

/** `POST /api/games/{id}/complete`: one boolean, never which cells (API.md).
 * The times come only with a right answer. */
export interface CompletionResult {
  correct: boolean;
  submission_count: number;
  official_seconds?: number;
  active_seconds?: number;
}

export interface GameView {
  game_id: string;
  difficulty: Difficulty;
  date: string;
  givens: string;
  state: string;
  status: "in_progress" | "completed";
  started_at: string;
  completed_at: string | null;
  official_seconds: number | null;
  active_seconds: number;
  submission_count: number;
}

export function createClient({
  fetch: send = (input, init) => fetch(input, init),
  lock = browserLock,
  base = BASE,
  timeoutMs = REQUEST_TIMEOUT_MS,
}: ClientOptions = {}) {
  const signedOutListeners = new Set<() => void>();
  // One refresh in flight in this tab, awaited by every request that hit a
  // 401 meanwhile; the lock does the same across tabs.
  let refreshing: Promise<boolean> | null = null;

  function call(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    // A timed-out request rejects like a lost connection, and is retried as one.
    const signal = init.signal ?? AbortSignal.timeout(timeoutMs);
    return send(`${base}${path}`, { ...init, headers, signal, credentials: "include" });
  }

  /**
   * `true` once refreshed, `false` when the session is over. Only a `401`
   * says that: any other failure (a 502 while the API restarts, say) is
   * thrown as it came, so the caller retries or reports it, and a valid
   * session is not thrown away with the inputs waiting on it.
   */
  function refresh(): Promise<boolean> {
    refreshing ??= lock(async () => {
      const response = await call("/auth/refresh", { method: "POST" });
      if (response.status === 401) return false;
      await read<unknown>(response);
      return true;
    }).finally(() => {
      refreshing = null;
    });
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
    /** The account and everything of theirs, for good (D30). */
    deleteAccount: () => request<void>("/users/me", { method: "DELETE" }),
    getToday: () => request<Today>("/puzzles/today"),
    /** Shows the grid and starts its clock, for good (D2, D3, Q13). */
    startGame: (difficulty: Difficulty) =>
      request<GameStarted>("/games", { method: "POST", body: JSON.stringify({ difficulty }) }),
    getGame: (gameId: string) => request<GameView>(`/games/${encodeURIComponent(gameId)}`),
    /** Legality only: the answer never says whether the digit is right (API.md). */
    putCell: (gameId: string, cell: number, value: number | null) =>
      request<void>(`/games/${encodeURIComponent(gameId)}/cells/${cell}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    /** Empties every cell the player filled; the clock goes on (D27). */
    clearCells: (gameId: string) =>
      request<void>(`/games/${encodeURIComponent(gameId)}/cells`, { method: "DELETE" }),
    heartbeat: (gameId: string) =>
      request<void>(`/games/${encodeURIComponent(gameId)}/heartbeat`, { method: "POST" }),
    /** Checks the grid the server holds; nothing is sent with it. */
    complete: (gameId: string) =>
      request<CompletionResult>(`/games/${encodeURIComponent(gameId)}/complete`, {
        method: "POST",
      }),
  };
}

async function read<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = "unknown_error";
    let message = response.statusText;
    let details: Record<string, unknown> = {};
    try {
      const { code: bodyCode, message: bodyMessage, ...rest } = (
        (await response.json()) as ApiErrorBody
      ).error;
      code = bodyCode;
      message = bodyMessage;
      details = rest;
    } catch {
      // Not every failure carries the envelope (a proxy 502, say).
    }
    const retryAfter = Number(response.headers.get("Retry-After") ?? Number.NaN);
    throw new ApiError(
      code,
      response.status,
      message,
      details,
      Number.isFinite(retryAfter) ? retryAfter : null,
    );
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** The application's client. Tests build their own with `createClient`. */
export const api = createClient();
