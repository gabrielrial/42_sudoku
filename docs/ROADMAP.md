# Roadmap

**Current phase: Phase 1 — foundation.** Phase 0 is complete; no application
code exists yet.

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

## Phase 1 — Foundation

Repository, backend and frontend skeletons, Docker Compose with PostgreSQL,
configuration and environment handling, linting and formatting, test
infrastructure, CI.

Exit: `docker compose up` gives a running (empty) application; the test suite
runs in CI.

## Phase 2 — Sudoku engine

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

## Phase 3 — Persistence and daily puzzles

Schema and migrations for puzzles. Pre-generation job. Date and timezone
handling. Unique constraint on `(puzzle_date, difficulty)`.

Exit: three puzzles exist for today and for the next N days; DST boundary tests
pass (last Sunday of March and of October).

## Phase 4 — Authentication

The 42 OAuth2 flow: redirect, `state` + PKCE, callback, `/v2/me`, local user
creation, application session, protected endpoints.

A dev-mode fake identity provider is built in this same phase, so that local
development, the test suite and CI never call 42.

Exit: a real 42 login works locally; the full test suite passes with no network
access.

## Phase 5 — Game API

Session creation with the locking rules from `GAME_RULES.md`, state retrieval,
input persistence, rate limiting, completion verification, server-side timing.

Exit: the whole loop is exercisable through the API alone, with tests covering
every rule in `GAME_RULES.md`.

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
