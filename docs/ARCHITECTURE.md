# Architecture

## Stack (agreed — no justification needed to use these)

**Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic, PyJWT, httpx, pytest.
Type hints everywhere.

httpx is the HTTP client. FastAPI's `TestClient` is built on it, so the API
tests need it in any case, and the backend uses it to talk to 42: the code
exchange and `/v2/me`. It comes from Encode, the team behind Starlette and
uvicorn. It is a runtime dependency, not only a test one, because the 42 login
uses it in production. The standard library's `urllib` could make those two
calls, but would not remove httpx, which the tests still need.

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
        |  HTTP / JSON, session in two HttpOnly cookies (D15)
        v
    FastAPI application
        |
        +-- auth        42 OAuth2 flow, session tokens, dependencies
        +-- users       local user records
        +-- puzzles     daily puzzle lookup, pre-generation job
        +-- games       sessions, inputs, completion, timing
        |
        v
    PostgreSQL

    sudoku/  <-- pure library. No FastAPI, no SQLAlchemy, no I/O.
                 Imported by puzzles. Testable on its own.

Two processes run this code, as two compose services built from one image:
`api` serves HTTP; `puzzles` runs `python -m app.jobs.generate_puzzles --every
3600`, which keeps today and the next days stocked with puzzles
(`DECISIONS.md` Q11). Generating a Hard takes about 16 seconds of CPU, so it
never happens inside a request.

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

Every database connection, the migrations' included, sets its session time zone
to UTC as soon as it opens (`make_engine`). PostgreSQL hands a `timestamptz`
back labelled with the session's zone, and Python subtracts two datetimes in the
same zone as wall-clock times: in a Berlin session, two real hours across the
end of summer time come out as one. Durations are also computed in absolute
time (`clock.seconds_between`), so either layer alone keeps them right.

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
