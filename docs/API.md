# API

JSON over HTTP under `/api`. FastAPI, Pydantic models at every boundary.

## Conventions

**Authentication** is two cookies (`DECISIONS.md` D15), both `HttpOnly`,
`SameSite=Lax`, and `Secure` in production:

| Cookie | `Path` | Lifetime | Contents |
|---|---|---|---|
| `access_token` | `/` | 15 minutes | JWT, HS256, signed with `SECRET_KEY`; claims `sub`, `iat`, `exp` |
| `refresh_token` | `/api/auth` | 7 days, renewed on each rotation | opaque random value; the server stores only its SHA-256 |

On each request the server checks the access token's signature and expiry and
loads the user named by `sub`. Every endpoint below except the auth ones
requires it, and answers `401 not_authenticated` without it or when any of
those checks fails. The client then calls `POST /api/auth/refresh` once and
retries.

**Authorisation** is separate and always checked: a game endpoint verifies the
session belongs to the calling user, and answers `404` — not `403` — when it does
not. A `403` would confirm that someone else's game exists at that id.

**CSRF**: `SameSite=Lax` blocks cross-site cookie-bearing `POST`s. On top of
that, every request other than `GET`, `HEAD` and `OPTIONS` must carry an
`Origin` header exactly equal to the configured front-end origin
(`FRONTEND_ORIGIN`). Requests failing that check get `403 forbidden_origin`.
The check is a dependency of the whole application, so a new endpoint cannot
forget it. Nothing that changes state is a `GET`, except the two OAuth
endpoints: the browser reaches them by navigation, and `state` protects them.

**Errors** all share one shape:

    { "error": { "code": "puzzle_not_started", "message": "Human-readable." } }

`code` is stable and machine-readable; `message` is for developers, not for
display. The client decides what the user sees from `code`.

Codes that apply to every endpoint:

| Status | `code` | When |
|---|---|---|
| `401` | `not_authenticated` | no session, a bad or expired token, any refresh failure |
| `403` | `forbidden_origin` | the `Origin` check above |
| `404` | `not_found` | no such route |
| `405` | `method_not_allowed` | the route exists, the method does not |
| `422` | `invalid_request` | body or parameters fail validation |
| `429` | `too_many_requests` | over a rate limit; carries `Retry-After` |
| `503` | `database_unavailable` | `/api/health/db` cannot reach PostgreSQL |

Each game endpoint below lists its own codes.

**Times** are ISO-8601 with offset. Durations are integer seconds.

**Rate limits** are per D5: game input 1/second per session with burst,
completion 5/minute per session, login 5/minute per IP, heartbeat 2/minute per
session. Exceeding one gives `429 too_many_requests` with `Retry-After`, in
whole seconds rounded up.

---

## Authentication

### `GET /api/auth/login`

Starts the 42 OAuth2 flow. Generates `state` and a PKCE `code_verifier`, stores
them in `oauth_states`, sets the `state` in a short-lived `HttpOnly` cookie
(`Path=/api/auth/callback`, ten minutes), and answers `302` to 42's authorize
endpoint with the `state` and the verifier's S256 `code_challenge`. Takes no
parameters: after signing in, the user always lands on the front end's home
page (a `?next=` is postponed; see `DATA_MODEL.md`, `oauth_states`).

PKCE is `DECISIONS.md` D18. Limited to 5 requests/minute per IP (D5).

### `GET /api/auth/callback?code=…&state=…`

Checks that the `state` in the URL matches the `state` cookie, validates and
**deletes** the `state` row (single use, ten-minute expiry), clears the cookie,
exchanges the code with 42 using the PKCE verifier, fetches `/v2/me`, upserts
the user on `intra_id` (refreshing `login` and campus for a returning user),
discards the 42 token (D11), issues the two session tokens (D15), sets both
cookies, and answers `302` to the front end's home page.

Failure — bad or expired state, a missing `state` cookie, denied consent, 42
unreachable, an account without a primary campus — redirects to the front end
with an error code in the query string. No stack traces, no token values, ever.

### `POST /api/auth/refresh`

No body; reads the `refresh_token` cookie. Rotates it (D15): the presented
token is sealed, its successor in the same family replaces it, and a new access
token is issued. Sets both cookies.

    ← 200  { "login": "grial", "campus_name": "Berlin" }

Every failure — no cookie, an unknown, expired or already-used token — is
`401 not_authenticated`. An already-used token also deletes its whole family:
someone else holds a copy.

The client must never run two refreshes at once (D15).

### `POST /api/auth/logout`

Deletes the family of the presented refresh token — this device only — and
clears both cookies. `204`, always: without a cookie, or with an unknown one,
it only clears the cookies.

The access token already issued stays valid until it expires, at most 15
minutes later. That is the accepted cost in D15.

### `GET /api/users/me`

    ← 200  { "login": "grial", "campus_name": "Berlin" }

The front end calls it on load to find out whether there is a session.

---

## Puzzles

### `GET /api/puzzles/today`

The home page's data. **Never returns cells** (Q13).

    { "date": "2026-09-09",
      "puzzles": [
        { "difficulty": "easy",   "status": "completed",
          "game_id": "…", "official_seconds": 412, "active_seconds": 388 },
        { "difficulty": "medium", "status": "in_progress", "game_id": "…" },
        { "difficulty": "hard",   "status": "not_started", "game_id": null }
      ] }

`status` is `not_started`, `in_progress`, `completed` or `closed`. `closed`
appears when a session was killed by the rollover rule (D6) — the user gets no
second attempt, so the interface must say so rather than offering "Play".

That there is no `GET /api/puzzles/{id}` is deliberate: nothing outside a game
should be able to address a puzzle at all.

---

## Games

### `POST /api/games`

    → { "difficulty": "hard" }

Creates today's session for that difficulty and returns the grid. This is the
only moment a puzzle becomes visible, and it is the moment `started_at` is set
(D2, Q13).

    ← 201
      { "game_id": "…", "difficulty": "hard", "date": "2026-09-09",
        "givens":  "003020600…",
        "state":   "003020600…",
        "started_at": "2026-09-09T21:14:03+02:00" }

| Condition | Response |
|---|---|
| A session already exists | `409 game_already_exists` with `game_id`, so the client can resume |
| No puzzle generated for today | `503 puzzle_unavailable` (Q11) |
| Unknown difficulty | `422` |

There is no way to create a session for a past date; the endpoint takes a
difficulty, not a date. That is D6 expressed as an API shape rather than a check.

### `GET /api/games/{id}`

Resuming. Returns everything needed to rebuild the board.

    ← 200
      { "game_id": "…", "difficulty": "hard", "date": "2026-09-09",
        "givens": "003020600…", "state": "043020690…",
        "status": "in_progress",
        "started_at": "…", "completed_at": null,
        "official_seconds": null, "active_seconds": 512,
        "submission_count": 0 }

| Condition | Response |
|---|---|
| Not the caller's game, or no such game | `404 game_not_found` |
| Closed by the rollover rule | `410 game_closed` |

`410 Gone` is the right code and worth the precision: the game existed, the user
owned it, and it can never be interacted with again.

### `PUT /api/games/{id}/cells/{index}`

One input. `index` is `0`–`80`.

    → { "value": 7 }        // or { "value": null } to clear
    ← 204

Validates **legality only** (`GAME_RULES.md` §3): the game is the caller's and
open, the cell is not a given, the value is 1–9 or null. It never reveals
whether the value is correct, and a wrong digit is not recorded anywhere.

Also updates `last_activity_at` and accumulates `active_seconds`.

| Condition | Response |
|---|---|
| Cell is a given | `409 cell_is_given` |
| Game already completed | `409 game_completed` |
| Game closed by rollover | `410 game_closed` |
| Bad index or value | `422` |
| Over the rate limit | `429` |

### `POST /api/games/{id}/heartbeat`

    ← 204

No body. Says only "the player is here". The server does the arithmetic:

    delta = now - last_activity_at
    if delta <= 90s:  active_seconds += delta      # continuous play
    else:             active_seconds += 0          # an idle gap
    last_activity_at = now

**Active time is therefore computed by the server, not reported by the client.**
The client cannot state a duration; it can only prove presence at an instant.
A script can still hold a session open by heartbeating without playing, but that
only ever makes a time worse, and the 02:00 cap bounds it regardless (Q1).

### `POST /api/games/{id}/complete`

    ← 200  { "correct": true,
             "official_seconds": 1187, "active_seconds": 964,
             "submission_count": 2 }

    ← 200  { "correct": false, "submission_count": 3 }

**No request body.** The server checks the grid it already has in `state`
against `puzzle_solutions`. The client's job is to have synced its cells first;
there is no second, parallel notion of "the submitted grid" that could disagree
with the stored one.

On success it sets `completed_at` and returns the official time. On failure it
increments `submission_count` and says nothing about *which* cells are wrong —
that would be the oracle from `SECURITY.md`.

Idempotent: calling it again on a completed game returns the same result and
does not move `completed_at` (D13).

| Condition | Response |
|---|---|
| Grid not yet full | `409 grid_incomplete` |
| Game closed by rollover | `410 game_closed` |
| Over the rate limit | `429` |

---

## Phase 8 — not built in the MVP

### `GET /api/leaderboard?date=&difficulty=`

One day, one difficulty (Q12). Ranked by `official_seconds` ascending, ties
broken by earlier `completed_at`. Paginated, and the response always carries the
caller's own row and rank even when it falls outside the requested page.

    { "date": "…", "difficulty": "hard",
      "entries": [ { "rank": 1, "login": "grial",
                     "official_seconds": 1187, "active_seconds": 964,
                     "submission_count": 1 } ],
      "me": { "rank": 47, … },
      "page": 1, "total": 312 }

### `GET /api/me/statistics`

Games played and completed, per difficulty; best, median and recent times;
current and longest streak; history.

---

## Endpoints deliberately absent

| Not built | Why |
|---|---|
| `GET /api/puzzles/{id}` | Puzzles are not addressable outside a game (Q13) |
| Anything returning a solution | The one hard rule in `SECURITY.md` |
| Any per-cell "is this right?" check | The oracle (A4) |
| `DELETE /api/games/{id}` | Games cannot be restarted or abandoned (D3) |
| A move history endpoint | No move log (D14) |
