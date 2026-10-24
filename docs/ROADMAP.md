# Roadmap

**Current phase: Phase 4 — authentication, in progress.** Phases 0 to 2 are
on `main`. Phase 3 has not been started: Phase 4 was begun before it.

A demo board — one fixed puzzle you can fill in, nothing else — was pulled
forward from Phase 6 at the developer's request. See `DECISIONS.md` A5.

Each phase gets a branch, ends in a pull request with green CI, and is reviewed
before merge. Do not start a phase before the previous one is merged.

---

## Phase 0 — Setup and design (complete)

- Documentation split into `AGENTS.md` plus `docs/`.
- Thirteen questions answered and recorded in `DECISIONS.md`; four remain open
  and none of them blocks Phases 1–6.
- Data model specified in `DATA_MODEL.md`, API in `API.md`.
- Repository initialised.

Remaining from this phase, carried into Phase 1: the repository structure and
the tooling (Claude Code configuration, hooks, CI).

## Phase 1 — Foundation (complete)

Repository layout, backend and frontend skeletons, Docker Compose with
PostgreSQL, configuration through the environment, the error envelope, Alembic
wired (no migrations yet — models arrive in Phase 3), ruff/mypy/pytest
configuration, pre-commit hooks, GitHub Actions, `.claude/settings.json`.

Two pieces of real behaviour, because neither could wait:

- `app/clock.py` — every Europe/Berlin day boundary in one place, including the
  two-hour rollover deadline, with tests covering the 23- and 25-hour days in
  March and October.
- `app/config.py` — refuses to start if the fake identity provider is enabled
  outside development, or if `SECRET_KEY` is still a placeholder in production.

Exit conditions, both met: `docker compose up` gives a running application with
`/api/health/db` answering, and the test suite runs green in CI.

Five problems were hit getting here. They are written up in `LESSONS.md`, which
is worth a minute before starting Phase 2.

## Phase 2 — Sudoku engine (on `main`; one verification open)

Pure Python. No framework, no database, no HTTP. Board representation,
candidate handling, the technique ladder and grader, a separate counting solver
for uniqueness, and generation.

Built to `DIFFICULTY.md`, which is normative for this phase — including its
verification requirements, which are not optional. A broken grader fails
silently.

Deliberately placed before authentication: it is the only genuinely novel logic
in the project, it has zero external dependencies, and it is fully testable
offline. Nothing in this module should know that FastAPI exists.

Exit: comprehensive unit tests; a command-line call produces a graded puzzle of
each difficulty with a proven-unique solution.

Status: built in `backend/src/sudoku/` — `board`, `techniques`, `grader`,
`solver`, `generator` — with tests for each, and the command-line exit check:

    cd backend && PYTHONPATH=src python -m sudoku generate --difficulty hard

Measured on this generator: about 50 ms per candidate puzzle; of minimal
puzzles, roughly 41% Easy, 17% Medium, 0.5% Hard and 41% discarded as beyond
tier 3. Easy and Medium come in under a second, Hard in about ten seconds on
average — acceptable offline, so no digging bias yet.

The published-puzzle checks of `DIFFICULTY.md` landed on 2026-10-22 (Stage 3 of
`PLAN.md`): thirteen references rated by SudokuWiki's solver, in agreement with
this grader on every tier and, within tier 3, on every technique used.

## Phase 3 — Persistence and daily puzzles

Schema and migrations for puzzles. Pre-generation job. Date and timezone
handling. Unique constraint on `(puzzle_date, difficulty)`.

Exit: three puzzles exist for today and for the next N days; DST boundary tests
pass (last Sunday of March and of October).

Status (2026-10-23, Stage 4 of `PLAN.md`): `puzzles` and `puzzle_solutions`
with their constraints; `ensure_puzzles`, which fills what is missing and
verifies every puzzle before storing it; the `puzzles` compose service, which
runs it every hour for seven days ahead (Q11).

## Phase 4 — Authentication (in progress)

The 42 OAuth2 flow: redirect, `state` + PKCE, callback, `/v2/me`, local user
creation, the application session — a short access JWT and a rotating refresh
token, both in cookies (`DECISIONS.md` D15) — logout, protected endpoints.
42 accounts only (D16).

A dev-mode fake identity provider is built in this same phase, so that local
development, the test suite and CI never call 42.

Exit: a real 42 login works locally; after logout the refresh token is
rejected (the access token lapses within 15 minutes, D15); after the user is
deleted both are rejected; the full test suite passes with no network access.

Status:

- On `main`: the session (access and refresh tokens, rotation, theft
  detection, logout, `GET /api/users/me`); the `Origin` check against CSRF;
  the login rate limiter (D17); the common error
  envelope; `users` keyed on the 42 identity; `oauth_states` with the PKCE
  helpers.
- On `feature/oauth-completion` (Stage 1 of `PLAN.md`), not merged yet: the
  whole sign-in. PKCE sent to 42 (D18); the `state` cookie against login
  CSRF; every failure a redirect with `?login_error=`; returning users
  refreshed and reassigned logins resolved through 42 (D21); `/login`
  rate-limited; `APP_ENV` required and `?as=<login>` for the fake provider
  (D19). Tested through the fake provider and a simulated 42, without network.
- Then: register the application with 42 (Q3) and sign in for real, including
  the PKCE check in D18.
- A username/password login was built first, as a learning step towards the
  session design, and removed (D16).

## Phase 5 — Game API

Session creation with the locking rules from `GAME_RULES.md`, state retrieval,
input persistence, rate limiting, completion verification, server-side timing.

Exit: the whole loop is exercisable through the API alone, with tests covering
every rule in `GAME_RULES.md`.

Status (2026-10-24, Stage 5 of `PLAN.md`): built. Today's puzzles, starting,
resuming, inputs, heartbeats and completion, each with its rate limit and its
authorisation, and a test that walks them all looking for the solution.

## Phase 6 — Frontend

Login flow, home page, board, input, resume, heartbeat, timer display,
completion state.

The signed-in home page has five entries (`DECISIONS.md` Q7): Easy, Medium,
Hard, My statistics, Leaderboard. **Only the three difficulties are functional
in the MVP** — the last two are laid out but inactive until Phase 8, so that
nothing is rearranged when they arrive.

Responsive and usable on a phone (`DECISIONS.md` Q6): the board survives a 375px
viewport and input works through an on-screen number pad, with hardware keyboard
support retained on desktop.

Exit: **MVP complete.** A real 42 user can log in, get today's puzzle, play it,
leave the page, come back, finish it, and see the result persisted correctly.

## Phase 7 — Local network deployment

Run on a machine reachable from the LAN. Validate with several real users at
once before anything is public.

## Phase 8 — Statistics and leaderboard

Personal statistics: games played, completed, solving times, history. Then three
leaderboards, one per difficulty, ranked on official time (`DECISIONS.md` Q12).

Phase 5 already stores everything these need; this phase is queries, indexes and
interface. Not before the MVP.

## Phase 9 — Public deployment

Production Docker setup, continuous deployment, HTTPS, logging, backups. The
hosting provider is chosen at this point, not before.

---

## Out of scope until after MVP

Social features, notifications, more than one puzzle per day, difficulties
beyond the three, an admin interface, a native mobile app, pencil marks
(`DECISIONS.md` Q5).

The leaderboard is planned (Phase 8) but is not MVP.
