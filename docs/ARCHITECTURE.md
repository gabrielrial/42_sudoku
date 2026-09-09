# Architecture

## Stack (agreed — no justification needed to use these)

**Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic, pytest.
Type hints everywhere.

**Frontend:** React + TypeScript + Vite. Confirmed (`DECISIONS.md` Q4).
Chosen without a long evaluation: a 9×9 grid does not discriminate between
frameworks, and the decision is not worth the time it costs to debate.

**Infrastructure:** Docker, Docker Compose, Git, GitHub, GitHub Actions.
No Kubernetes, no service mesh, no message queue. If one is ever proposed, it
needs a concrete problem it solves.

## Shape

A modular monolith. One FastAPI application, internally separated by
responsibility, one database.

    Frontend (React)
        |  HTTP / JSON, session cookie
        v
    FastAPI application
        |
        +-- auth        42 OAuth2 flow, sessions, dependencies
        +-- users       local user records
        +-- puzzles     daily puzzle lookup, pre-generation job
        +-- games       sessions, inputs, completion, timing
        |
        v
    PostgreSQL

    sudoku/  <-- pure library. No FastAPI, no SQLAlchemy, no I/O.
                 Imported by puzzles. Testable on its own.

What that package must do is specified in `DIFFICULTY.md`.

The `sudoku` package is the important boundary. It takes and returns plain data
structures, has no framework imports, and can be tested with no database and no
web server. Everything else is ordinary web application plumbing.

A `statistics` module appears only in Phase 8. It is not part of the MVP and
should not exist as an empty package before then.

## Data model (draft — to be finalised in Phase 0)

Entities:

- **User** — one row per 42 identity. The 42 user id, login, display name, plus
  campus and account status (stored so that D12 can be tightened later without a
  migration). See `SECURITY.md` for what must not be stored.

- **Puzzle** — `puzzle_date`, `difficulty`, `givens`, `solution`, and metadata
  about how it was generated and graded (seed, generator version, techniques the
  grader needed). Unique on `(puzzle_date, difficulty)`.

- **GameSession** — `user_id`, `puzzle_id`, and:
  - `state` — a snapshot of the current grid (D14). No move log in the MVP.
  - `started_at`, `completed_at` — the official time is the difference (D2, D10).
  - `active_seconds` — accumulated active time, advisory only (D10).
  - `last_activity_at` — drives both active time and the D6 expiry rule.
  - `failed_attempts` — count of incorrect submissions (D13).
  - status — open / completed / closed-by-rollover. Derived on read from
    `last_activity_at` and the puzzle date (Q1); a nightly job materialises it
    for statistics only.

  Unique on `(user_id, puzzle_id)`, which is what enforces D3.

Still to decide before implementing:

- The exact snapshot format. It carries a version number from the first
  migration and reserves room for pencil marks, which arrive after the MVP
  (`DECISIONS.md` Q5).
- Indexes, exact column types, and the representation of a grid (81-character
  string vs. array).

All timestamps are `timestamptz` stored in UTC. `puzzle_date` is a plain `DATE`.
The Europe/Berlin rule is applied when computing "today", never in storage.

## API (draft — to be designed in Phase 0)

Sketch only. Naming, schemas, status codes and error shapes get designed before
anything is implemented.

    GET  /api/me
    GET  /api/puzzles/today            -> which difficulties exist + my status;
                                          NEVER the cells (Q13)
    POST /api/games                    -> create a session; returns the grid
    GET  /api/games/{id}               -> current state, for resuming
    PUT  /api/games/{id}/cells/{index} -> one input, legality-checked only
    POST /api/games/{id}/complete      -> submit the grid for verification
    POST /api/games/{id}/heartbeat     -> activity signal, every 60s (D6/Q1)
    GET  /api/me/games                 -> history (Phase 8)

Constraints on the design:

- No endpoint ever returns a solution, in whole or in part.
- No endpoint returns a puzzle's cells before a session for it exists (Q13).
- Every game endpoint authorises on session ownership, not just authentication.
- Input and completion endpoints are rate-limited.
- Completion is idempotent: submitting twice does not change `completed_at`.
- Every game endpoint rejects a session closed by rollover, distinctly from
  one that is merely completed — the client needs to tell the user why.

## Deployment

Three stages, in order. Each one is only started when the previous is stable.

**Stage 1 — Local development.** Everything on the developer's machine: backend,
frontend, PostgreSQL, via Docker Compose. This is the environment CI mirrors.

**Stage 2 — Local network.** The application runs on one machine on the LAN and
is reachable from other machines on that network. The point is validating with
several real users before going public. Notable consequence: the 42 OAuth
application needs a redirect URI for that machine's LAN address, and the app can
no longer assume `localhost`.

**Stage 3 — Public.** A publicly reachable server, with HTTPS, real secrets
management, backups and logging. The hosting provider is chosen when this stage
actually arrives — not earlier, and not in a way that adds complexity to stages
1 and 2.
