# Security

The governing assumption: **the user controls the client completely.** They can
read every line of JavaScript, edit any value in memory, replay and forge any
request, and script the API directly without a browser. Nothing the client sends
is evidence of anything.

## The solution oracle

The most likely way this application gets cheated is not a stolen token. It is
this: if any endpoint tells the client whether a single cell is correct, then
81 cells × 9 values = at most 729 requests reveals the entire solution. Give a
scripted client that ability and every puzzle is solved in seconds, with a
perfect record and an excellent time.

Therefore:

- The solution is never sent to the client, in whole or in part.
- No endpoint reports whether an individual cell is correct.
- The input endpoint validates **legality**, not **correctness** (see
  `GAME_RULES.md` § 3).
- Only the full-grid completion endpoint compares against the solution, it
  returns a single boolean, and it is rate-limited and counted.

Immediate feedback for the player, if wanted, is computed client-side from the
Sudoku rules alone: highlighting duplicate values in a row, column or box. That
leaks nothing, because it is derivable from what the player can already see.

## Pre-solving

The leaderboard ranks on official time (`completed_at - started_at`), which
cannot be forged downward — but it is defeated entirely by a player who solves
the grid on paper *before* starting, then types the answer in. Every timestamp
in that scenario is genuine; the server simply never saw the twenty minutes of
work.

The defence is not a timing metric, it is access control: the grid is only ever
returned once a session exists (`DECISIONS.md` Q13). No endpoint, signed in or
out, exposes a puzzle's cells beforehand. Combined with D3 — no restarts —
there is no way to look without committing.

## Authentication

- 42 OAuth2, authorization code flow, with `state` and PKCE. `state` is
  single-use and verified.
- The user's 42 password is never seen, requested or stored.
- Client ID, client secret and session secret come from the environment. Never
  from source, never from a committed file.
- Separate 42 applications for local development, the LAN stage and production,
  each with its own redirect URI registered exactly.
- Session cookies: `HttpOnly`, `Secure` in production, `SameSite=Lax`.
- CSRF protection on state-changing endpoints if cookie authentication is used.
- CORS configured to an explicit origin list. Never `*` with credentials.

## Authorisation

Authentication proves *who*. Every game endpoint additionally checks *what*:
the session being read or written belongs to the calling user. A valid token for
user A must never reach user B's game. This is tested, not assumed.

## Rate limiting

Figures are in `DECISIONS.md` D5: inputs 1/second per session with a burst
allowance, completions 5/minute per session, logins 5/minute per IP. All
configurable and reviewed at the LAN stage.

Two notes beyond the numbers:

- The completion endpoint is the brute-force path. Its limit, plus the stored
  count of failed attempts, is what makes repeated full-grid submission useless.
- The heartbeat endpoint needs its own limit, and it is an abuse surface in its
  own right: a scripted client could heartbeat forever to keep a past-day
  session alive. The two-hour hard cap after rollover (`DECISIONS.md` Q1) is
  what closes that hole — it is checked independently of activity, so no amount
  of forged traffic extends a session past 02:00.

## Data handling

- Store the minimum from `/v2/me`: 42 user id, login, display name. Not the
  whole payload.
- Do not store the 42 access token unless a concrete need appears
  (`DECISIONS.md` D11). A third-party token in the database is a liability with
  no MVP benefit.
- Never log tokens, secrets, cookies, or authorization codes.
- GDPR applies — real people's identities, in the EU. A privacy note and a
  deletion path are needed before Stage 3 (`DECISIONS.md` Q8).

## Standard controls

Parameterised queries only (SQLAlchemy, never string-built SQL). Pydantic
validation at every boundary. HTTPS in production. Dependencies pinned and
scanned. Secrets scanning in pre-commit and CI.
