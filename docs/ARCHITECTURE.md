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

## Data model and API

Both are now specified in full:

- `DATA_MODEL.md` — tables, columns, types, constraints and indexes, and which
  product rules the database enforces directly.
- `API.md` — endpoints, request and response schemas, status codes, error
  shapes, and the endpoints deliberately not built.

All timestamps are `timestamptz` in UTC; `puzzle_date` is a bare `DATE`. The
Europe/Berlin rule is applied when computing "today", never in storage.

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
