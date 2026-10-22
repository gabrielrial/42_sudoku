# Plan to a playable, deployable MVP

Working plan, written 2026-10-20 from a full review of the code and the docs.
`ROADMAP.md` says *what* each phase delivers; this file says *in which steps*
we get there from where the code is today, and what is still undecided.

Update it at the end of every stage: tick the stage, note what changed in the
plan and why. When an open question below is answered, record the answer in
`DECISIONS.md` (as a new `D` entry, or by moving the `Q` up) and strike it here.

Legend: 🔐 security · 🧩 Sudoku engine · 🔑 42 OAuth. Stages carrying one of
these are reviewed line by line by the developer before they are accepted
(`AGENTS.md`, Definition of Done).

---

## Where the code is (2026-10-20)

- Phase 2 (engine) on `main`, except the published-puzzle verification of
  `DIFFICULTY.md`: its two tests are always skipped.
- Phase 3 (persisted daily puzzles) not started.
- Phase 4 (auth) half done. On `main`: session tokens (D15), `Origin` check,
  rate limiter (D17, not attached to any route), `users` keyed on `intra_id`,
  `oauth_states`. On `feature/identity-provider`: identity provider interface,
  first `/login` and `/callback`.
- `feature/identity-provider` is behind `main` by `008c9c1 doc: updated`: its
  copy of `docs/` is stale. Read `docs/` from `main` until it is merged.
- Checks on the branch: ruff fails (1, from `68325ed`), format and mypy pass,
  pytest 227 passed / 2 skipped.

Update 2026-10-21: Stage 1's code is done on `feature/oauth-completion`
(1a–1f); items 1–9 below are fixed there. Pytest: 312 passed, 2 skipped.

## Known problems, by impact

Necessary — bugs and security holes:

1. ✅ Commit `68325ed` ("fix: variable name") in `identity_provider.py`:
   `campus_info["comapus"]` (`KeyError` on every real login) and an unused
   import (ruff F401, so CI is red). The previous `campus_info["id"]` was
   correct. Fixed in Stage 1a.
2. ✅ PKCE is not actually used: the challenge is never sent to 42, and the
   verifier `finish_login` returns is thrown away instead of being sent in the
   code exchange (D18 decided, not implemented).
3. ✅ No `state` cookie: login CSRF (`LESSONS.md` E) is open.
4. ✅ A failed callback leaves its `state` reusable: the row deletion is rolled
   back when 42 fails, because nothing commits it before the provider call.
5. ✅ Callback failures are a JSON `401` or a `500` (no httpx timeout, uncaught
   `HTTPStatusError`/`ValueError`/`KeyError`); `API.md` requires a redirect to
   the front end with an error code. `?error=access_denied` is not handled.
6. ✅ The authorize URL is concatenated, not URL-encoded.
7. ✅ A returning user's `login` and campus are not refreshed; the `login` unique
   collision of `DATA_MODEL.md` is not handled.
8. ✅ The login rate limit is not attached to `/login`.
9. ✅ The fake identity provider is only refused in `production`, and compose
   enables it by default: a LAN deployment with `APP_ENV=development` lets
   anyone in. It also hard-codes `localhost:8001` and a plausible real login.
10. `Secure` cookies are tied to `APP_ENV=production`: over plain HTTP on the
    LAN the browser drops them and nobody can sign in.
11. ✅ Tests build the schema with `create_all`; migrations are never exercised
    in CI (how `LESSONS.md` 12 and 13 got through).
12. ✅ "0 skipped" does not hold: the published-puzzle tests always skip, and
    every database test skips (not fails) without `sudoku_test` — which plain
    `make` deletes.

Desirable:

- `Settings()` built directly in `routers/auth.py` and `get_provider`, instead
  of `get_settings()`; several modules read settings at import time.
- The callback commits twice (user, then token): not atomic.
- Typos and Spanish in docstrings (`identity_provider.py`, `dependencies.py`).
- `refresh_tokens` and expired `oauth_states` are never purged.
- Frontend Dockerfile uses `npm install`, not `npm ci`.
- Merged branches never deleted.

## Code and docs that disagree (as on `main`)

| Where | Disagreement |
|---|---|
| `API.md`, `DATA_MODEL.md`, `SECURITY.md` vs `auth.py` | `state` cookie, PKCE, error redirects, refreshing a returning user, `/login` rate limit: documented, not built |
| `GAME_RULES.md` §4, D13 vs `API.md`, `LESSONS.md` D | "the client submits a full grid" vs `/complete` with no body. `GAME_RULES.md` is normative: fix it in its own commit |
| Q12 vs `DATA_MODEL.md` | `failed_attempts` vs `submission_count` |
| Q1 vs `clock.py`, `API.md` | "all values are configuration" vs constant `ROLLOVER_GRACE_HOURS` and a fixed 90 s heartbeat gap |
| `DATA_MODEL.md` | `game_sessions.user_id BIGINT` vs `users.id` `SERIAL`; `TEXT` vs `VARCHAR` in the models |
| `.env.example` | redirect on port 8001 vs `API_PORT=8000`; comment says the fake provider is refused outside development, code refuses it only in production |
| `DECISIONS.md`, Open | "nothing here blocks Phases 1–6", but Q11 shapes Phase 3 |
| `DIFFICULTY.md` | published-puzzle verification required, not done |
| `ARCHITECTURE.md` | draws modules by domain (auth, users, puzzles, games); the code is organised by layer (`api/`, `services/`, `database/`) |

## Not verifiable from here

- 42's OAuth guide (`api.intra.42.fr/apidoc/guides/web_application_flow`)
  redirects to the intra login. Whether 42 checks PKCE is unconfirmed.
- Confirmed by the developer's first real sign-in (2026-10-21): 42 accepts the
  form-encoded code exchange (RFC 6749 §4.1.3), and `/v2/me` carries the
  fields the code reads (`campus_users[].is_primary`, `campus[]`).
- D18's wrong-verifier test needs the registered application: developer only.

---

## Before Stage 1 (developer)

- [x] `68325ed`: fixed in Stage 1a. It reached `main` with the merge of
  `feature/identity-provider` (2026-10-20), so `main`'s CI is red until 1a lands.
- [x] `feature/identity-provider` merged into `main` (2026-10-20); Stage 1
  continues on `feature/oauth-completion`.
- [x] P4 and P5 answered (2026-10-20), recorded as D19 and D20.

## Stages

Each stage: one branch, one logical change per commit. At the end: what
changed, why, how to test it, a proposed commit message; then wait for the OK.
Checks before "done": ruff, ruff format, mypy, pytest with 0 failures and the
skip count read (0 once Stage 3 lands).

### Stage 1 — Finish the 42 sign-in 🔑🔐 · `feature/oauth-completion`

**Code done 2026-10-21 (1a–1f).** Left for the developer: register the
app, a real sign-in, the wrong-verifier check. Two changes to the plan on
the way: 1d asks 42 for a stale holder's current login instead of keeping
the stored one (D21); the fake provider redirects to the callback by path
rather than a URL taken from the settings.

| Commit | Change | Tests |
|---|---|---|
| 1a | Provider: `campus_id` from `campus_info["id"]` again (undoes `68325ed`); authorize URL built with `urlencode`, carrying the S256 `code_challenge`; code exchange form-encoded with `code_verifier`; httpx timeouts; one typed `IdentityProviderError`; fake provider's URL derived from settings and an obviously fake login; `get_settings()` everywhere | `httpx.MockTransport` (no new dependency): exact request shapes, `/v2/me` parsing, no primary campus, 42 down or 4xx |
| 1b | `state` cookie at `/login` (`Path=/api/auth/callback`, 10 min, HttpOnly, Lax), compared with `secrets.compare_digest`; `state` deletion committed before calling 42 | missing or different cookie rejected; replay after a failed callback rejected |
| 1c | Every failure → `302` to `FRONTEND_ORIGIN/?login_error=<code>`; `error=access_denied` handled; user and token in one commit | one test per error code; no detail leaks |
| 1d | Upsert refreshes a returning user; a login 42 reassigned goes to its new holder, the stale holder renamed from `GET /v2/users/:id` or to `former-<intra_id>` (D21) | returning user with a new login or campus; takeover by a newcomer and by a returning user; every fallback; no extra call to 42 without a collision |
| 1e | Rate limit on `/login` | `429` on the real route |
| 1f | P4: `APP_ENV` required, with no default in `Settings` or compose, so a deployment that forgets it does not start; fake provider honours `?as=<login>` (validated format, fake users kept apart from real `intra_id`s), ignored outside fake mode | missing `APP_ENV` refuses to start; fake refused in production; `?as=` gives two distinct users; `?as=` ignored by the real provider |

Done: login → callback → `/api/users/me` through the fake provider in one
test; every case in `API.md` tested. Then, by the developer: register the app
(Q3), a real sign-in, D18's wrong-verifier check.

### Stage 2 — Test and tooling floor · `chore/test-hardening`

**Done 2026-10-21.** `make check` runs what CI runs. Not done: running the
migration round trip locally as part of `make check`; it runs in CI.

- `docker-entrypoint-initdb.d` script that creates `sudoku_test`.
- Database fixture fails instead of skipping, with no opt-out (P5, option A):
  an unreachable database, or a `DATABASE_URL` not ending in `_test`, is an
  error. `pytest tests/sudoku` still runs the engine alone, since it never uses
  the fixture.
- `make test`, `make check`; non-destructive default goal (per P6).
- CI: `alembic upgrade head` + `alembic check` on an empty database.
- `npm ci` in the frontend Dockerfile.

Done: removing `sudoku_test` fails the suite; a migration out of step with the
models fails CI.

### Stage 3 — Published-puzzle verification 🧩 · `test/published-puzzles`

**Done 2026-10-22.** Changed on the way: the reference is SudokuWiki's solve
path, not the "exemplar" labels, which its own solver contradicts; the two
Hard references are generated puzzles rated by that solver, since no published
one fits. Recorded in `DIFFICULTY.md`. pytest: 0 skipped.

Puzzles copied exactly from a cited source (per P8), each checked for a unique
solution before it is added. Done: pytest reports 0 skipped, and the grader
keeps the source's relative order. If it does not, that is a finding to
discuss, not a test to loosen.

### Stage 4 — Phase 3: daily puzzles 🧩🔐 · `feature/daily-puzzles`

| Commit | Change | Tests |
|---|---|---|
| 4a | `puzzles`, `puzzle_solutions` models + migration (CHECKs, `UNIQUE (puzzle_date, difficulty)`, cascade FK) | constraints enforced by the database; read path never loads the solution |
| 4b | Idempotent `ensure_puzzles(db, start, days)` and CLI `python -m app.jobs.generate_puzzles` | idempotency, DST dates, metadata stored, uniqueness re-proved on insert |
| 4c | Scheduling per Q11 / P1 | under compose: puzzles exist for today and the next N days |

Done: `ROADMAP.md` Phase 3 exit; the solution exists only in `puzzle_solutions`.

### Stage 5 — Phase 5: game API 🔐 · `feature/game-api`

| Commit | Change |
|---|---|
| 5a | `game_sessions` + migration; pure `session_status(...)`; thresholds become settings (ends the `clock.py` constant) |
| 5b | `GET /api/puzzles/today` (never cells), `POST /api/games` (today only; unique race → `409`; `503` without a puzzle) |
| 5c | `GET /api/games/{id}`: `404` when not yours, `410` when closed |
| 5d | `PUT /cells/{index}` (legality, row lock, per-session rate limit, active time) and heartbeat |
| 5e | `POST /complete` (no body, idempotent, counts submissions, rate-limited, no oracle) |

Before 5e: fix `GAME_RULES.md` §4, D13 and Q12 in a separate docs commit.
Tests: every rule of `GAME_RULES.md` — two-user authorisation; rollover at
00:00, after 15 idle minutes and at 02:00, DST days included; no response ever
carries the solution. Done: the whole loop works through the API alone.

### Stage 6 — Phase 6: front end · `feature/frontend-mvp`

- 6a API client and session: `/users/me` on load, login button, one shared
  refresh on `401` (D15), `login_error` messages, routing without a dependency.
  Proposed dependency (P7): **vitest**, dev only — tests the single-flight
  refresh and the input queue; alternative is Node's test runner with
  experimental TypeScript stripping, more fragile; maintained by the Vite team,
  never shipped to production.
- 6b Home page, five slots, two inactive (Q7).
- 6c Game page wired: ordered `PUT` queue honouring `Retry-After`, 60 s
  heartbeat, decorative timer, completed and closed states; delete
  `demoPuzzle.ts`.
- 6d Check at 375 px.

Done: `ROADMAP.md` Phase 6 exit, by hand with the fake provider and with 42.

### Stage 7 — Phase 7: LAN deployment 🔐 · `deploy/lan`

Deployment compose: uvicorn without `--reload`, migrations on start, built
front end served per P3, `FORWARDED_ALLOW_IPS`, HTTPS or `COOKIE_SECURE` per
P2, stricter fake-provider guard per P4, purge of expired `refresh_tokens` and
`oauth_states` in the scheduled job.

Review D5's login limit there: it is per IP, and a whole 42 campus usually
reaches the internet through one public address — five sign-ins a minute
for everybody on it. Behind a proxy, every user also shares the proxy's
address unless `FORWARDED_ALLOW_IPS` is set (`SECURITY.md`).

Done: several real users play at once from the LAN, signed in with 42.

---

## Open questions

Already in `DECISIONS.md`: Q8 (GDPR, before stage 3), Q9 (42 curriculum
project?), Q10 (public or private, licence), **Q11 (pre-generation: how many
days ahead, what if it fails, who is alerted) — blocks Stage 4.**

New, numbered `P` so they cannot collide with `DECISIONS.md`:

| # | Question | Needed by | Proposal |
|---|---|---|---|
| P1 | How the generation job runs: compose service looping, host cron calling a CLI, or a thread at API start-up | Stage 4 | compose service + idempotent CLI |
| P2 | Cookies on the LAN: HTTPS through a proxy (Caddy, mkcert), or a `COOKIE_SECURE` setting independent of `APP_ENV` | Stage 7 | — |
| P3 | Serving the built front end: FastAPI `StaticFiles` (one origin, nothing new) or an nginx/Caddy container | Stage 7 | FastAPI |
| ~~P4~~ | ~~Fake provider: deployments must declare their environment; fake accepts `?as=<login>` to test with several users~~ | Stage 1 | **Answered 2026-10-20: yes to both** — D19 (Stage 1f) |
| ~~P5~~ | ~~Database tests without `sudoku_test`: always fail, or fail unless an opt-out variable is set~~ | Stage 2 | **Answered 2026-10-20: always fail (A)** — D20 |
| ~~P6~~ | ~~Makefile default goal: `all` instead of the destructive `re`~~ | Stage 2 | **Answered 2026-10-21: `all`** |
| P7 | Front-end tests with vitest, or none | Stage 6 | vitest |
| ~~P8~~ | ~~Source for published puzzles~~ | Stage 3 | **Answered 2026-10-22: SudokuWiki's solver** (`DIFFICULTY.md`, verification) |
| P9 | Delete merged branches | any time | developer's call |
| P10 | `/login` over its limit answers a JSON `429`, which a browser shows raw; or redirect to `/?login_error=too_many_requests` like the callback | Stage 6 | redirect |

## Inputs wanted from the developer

Things only the developer can provide, which would remove guesswork:

- 42's OAuth guide and the `/v2/me` page, exported or pasted into
  `docs/reference/` (they sit behind the intra login).
- One real `/v2/me` response with personal data removed, as a test fixture.
- After registration (Q3): the redirect URIs registered — never the secret.
- At Stage 7: the LAN machine, its address, and whether a certificate is possible.
