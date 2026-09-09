# API

JSON over HTTP under `/api`. FastAPI, Pydantic models at every boundary.

## Conventions

**Authentication** is a session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` in
production, `Path=/`. It carries a random token whose SHA-256 is stored in
`app_sessions`. Every endpoint below except the auth ones requires it and answers
`401` without it.

**Authorisation** is separate and always checked: a game endpoint verifies the
session belongs to the calling user, and answers `404` — not `403` — when it does
not. A `403` would confirm that someone else's game exists at that id.

**CSRF**: `SameSite=Lax` blocks cross-site cookie-bearing `POST`s. On top of
that, every state-changing request must carry an `Origin` header matching the
configured front-end origin. Requests failing that check get `403`.

**Errors** all share one shape:

    { "error": { "code": "puzzle_not_started", "message": "Human-readable." } }

`code` is stable and machine-readable; `message` is for developers, not for
display. The client decides what the user sees from `code`.

**Times** are ISO-8601 with offset. Durations are integer seconds.

**Rate limits** are per D5: game input 1/second per session with burst,
completion 5/minute per session, login 5/minute per IP, heartbeat 2/minute per
session. Exceeding one gives `429` with `Retry-After`.

---

## Authentication

### `GET /api/auth/login`

Starts the 42 OAuth2 flow. Generates `state` and a PKCE `code_verifier`, stores
them in `oauth_states`, and answers `302` to 42's authorize endpoint. Optional
`?next=` records where to land afterwards; only same-origin paths are accepted.

### `GET /api/auth/callback?code=…&state=…`

Validates and **deletes** the `state` row (single use, ten-minute expiry),
exchanges the code with 42 using the PKCE verifier, fetches `/v2/me`, upserts
the user on `intra_id`, discards the 42 token (D11), creates an `app_sessions`
row, sets the cookie, and answers `302` to the front end.

Failure — bad state, expired state, denied consent, 42 unreachable — redirects
to the front end with an error code in the query string. No stack traces, no
token values, ever.

### `POST /api/auth/logout`

Deletes the `app_sessions` row and clears the cookie. `204`. Idempotent.

### `GET /api/me`

    { "login": "grial", "display_name": "Gabriel R.", "campus_name": "Berlin" }

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
