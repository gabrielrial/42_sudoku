// Who is signed in, and what a failed sign-in left in the URL. No React in
// here, so it can be tested without a browser.

import { ApiError, type Me } from "../api/client";

export type Session =
  | { kind: "loading" }
  | { kind: "signed_in"; me: Me }
  | { kind: "signed_out" }
  /** The API did not answer, or answered something other than yes or no. */
  | { kind: "unreachable" };

/**
 * Ask the API who this is (`GET /api/users/me`, API.md). A `401` that
 * survives the client's refresh means nobody is signed in: an ordinary
 * answer, not an error.
 */
export async function loadSession(getMe: () => Promise<Me>): Promise<Session> {
  try {
    return { kind: "signed_in", me: await getMe() };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return { kind: "signed_out" };
    return { kind: "unreachable" };
  }
}

// The codes `/api/auth/login` and `/api/auth/callback` can send back in
// `?login_error=` (API.md, D23). Anything else gets the generic message.
const LOGIN_ERRORS: Record<string, string> = {
  invalid_state: "That sign-in had expired or was already used. Please sign in again.",
  access_denied: "You declined access on 42. Sign in again whenever you want to play.",
  provider_error: "42 could not be reached. Try again in a moment.",
  no_primary_campus: "Your 42 account has no primary campus, which Sudoku 42 needs.",
  too_many_requests: "Too many sign-in attempts. Wait a minute, then try again.",
};
const GENERIC_LOGIN_ERROR = "Signing in did not work. Please try again.";

/**
 * The sign-in failure in `url`, if any, and the same URL without it: the
 * message is shown once, and a reload or a bookmark must not show it again.
 * Pure; the caller rewrites the address bar.
 */
export function takeLoginError(url: string): { message: string | null; cleaned: string } {
  const parsed = new URL(url);
  const code = parsed.searchParams.get("login_error");
  if (code === null) return { message: null, cleaned: url };
  parsed.searchParams.delete("login_error");
  return {
    message: Object.hasOwn(LOGIN_ERRORS, code) ? LOGIN_ERRORS[code]! : GENERIC_LOGIN_ERROR,
    cleaned: parsed.pathname + parsed.search + parsed.hash,
  };
}
