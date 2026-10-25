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
  returns a single boolean, and it is rate-limited and counted. The comparison
  is constant-time (`secrets.compare_digest`): an ordinary one stops at the
  first difference, and its timing would hint at how many leading cells are
  right.
- `tests/api/test_no_solution_leaks.py` walks every game endpoint before the
  solve, through success and every refusal — 404 (no such game, someone
  else's), 409, 410, 422 and 429, and a game still open past midnight — and
  checks each answer four ways: its status is the one the walk expects, so no
  part of the walk silently failed; the solution does not appear in it; every
  JSON key is one the API defines; and every grid in it is one the player
  already has. The last two catch a partial leak: a careless field — a hint, a
  count of right cells — fails by being there, whatever it carries, and an
  allowed one — a `state` with a solved cell filled in — fails by its value.

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
  single-use and verified, and bound by a short-lived cookie to the browser
  that started the login (no login CSRF with an attacker's own valid `state`).
  Whether 42 enforces PKCE is not documented; it is to be checked against the
  real application (`DECISIONS.md` D18).
- The user's 42 password is never seen, requested or stored.
- Client ID, client secret and the JWT signing key (`SECRET_KEY`) come from the
  environment. Never from source, never from a committed file.
- One 42 application for every deployment stage (`DECISIONS.md` Q3). What
  changes per stage is the redirect URI: each stage's callback is registered
  exactly on that application as the stage arrives, and each stage's
  `FORTYTWO_REDIRECT_URI` names it.
- The session is two tokens in two cookies (`DECISIONS.md` D15): a 15-minute
  access JWT and a 7-day refresh token that rotates on every use. Both
  `HttpOnly`, `Secure` in production, `SameSite=Lax`; the refresh cookie is
  scoped to `Path=/api/auth`. Never in `localStorage`, where any XSS can read
  them.
- Verification pins the algorithm to `HS256` and requires `sub`, `iat` and
  `exp`. A token naming any other algorithm, including `none`, is rejected.
- `SECRET_KEY` is at least 32 random bytes. Whoever holds it can mint a valid
  access token for any user. Rotating it invalidates every access token, forged
  ones included, but signs nobody out by itself: refresh tokens are not signed
  with it. To sign everyone out, also delete every row of `refresh_tokens`.
- The payload is readable, not encrypted: ids and timestamps only.
- Refresh tokens are stored as SHA-256 hashes, never in clear: a copy of the
  database holds no usable token. A refresh token presented twice means a copy
  exists, and its whole family is deleted.
- Logout and account deletion revoke through the database: logout deletes the
  device's refresh-token family; deleting a user cascades to their refresh
  tokens, and their access tokens fail at the user lookup. An access token
  already issued survives a logout for up to 15 minutes — the accepted cost in
  D15.
- CSRF: `SameSite=Lax`, plus an exact `Origin` check on every request that is
  not `GET`, `HEAD` or `OPTIONS` (`API.md`, Conventions).
- CORS configured to an explicit origin list. Never `*` with credentials.

## Authorisation

Authentication proves *who*. Every game endpoint additionally checks *what*:
the session being read or written belongs to the calling user. A valid token for
user A must never reach user B's game. This is tested, not assumed.

## Rate limiting

Figures are in `DECISIONS.md` D5: inputs 1/second per session with a burst
allowance, completions 5/minute per session, heartbeats 2/minute per session,
logins 5/minute per IP. All configurable and reviewed at the LAN stage. The
limiter itself is D17: in-house, in the process's memory.

Notes beyond the numbers:

- Game limits are per game session, never per IP: a whole campus may share one
  public address.
- Behind a reverse proxy (stage 2 onward) every request arrives from the
  proxy's address. The real client address must then come from the proxy's
  forwarded headers, trusted only from the proxy itself
  (`FORWARDED_ALLOW_IPS=<proxy IP>`, never `*`). Otherwise either every user
  shares one login bucket, or anyone can claim any address.

- The completion endpoint is the brute-force path. Its limit, plus the stored
  count of failed attempts, is what makes repeated full-grid submission useless.
- The heartbeat endpoint needs its own limit, and it is an abuse surface in its
  own right: a scripted client could heartbeat forever to keep a past-day
  session alive. The two-hour hard cap after rollover (`DECISIONS.md` Q1) is
  what closes that hole — it is checked independently of activity, so no amount
  of forged traffic extends a session past 02:00.

## Data handling

- Store the minimum from `/v2/me`: 42 user id, login, primary campus id and
  name (`DATA_MODEL.md`). Not the whole payload: no email, no phone, no avatar.
- Do not store the 42 access token unless a concrete need appears
  (`DECISIONS.md` D11). A third-party token in the database is a liability with
  no MVP benefit.
- The application token used to resolve a login collision (`DECISIONS.md` D21)
  is fetched for that one call and never stored either.
- Never log tokens, secrets, cookies, or authorization codes.
- GDPR applies — real people's identities, in the EU. A privacy note and a
  deletion path are needed before Stage 3 (`DECISIONS.md` Q8).

## Standard controls

Parameterised queries only (SQLAlchemy, never string-built SQL). Pydantic
validation at every boundary. HTTPS in production. Dependencies pinned and
scanned. Secrets scanning in pre-commit and CI.
