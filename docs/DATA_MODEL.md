# Data model

PostgreSQL. SQLAlchemy models, Alembic migrations. All timestamps are
`timestamptz` stored in UTC; only `puzzle_date` is a bare `DATE`, because a
puzzle belongs to a Europe/Berlin calendar day rather than an instant (D1).

Enumerated values are `TEXT` with a `CHECK` constraint rather than native
Postgres enums. The value sets are closed and tiny, and `CHECK` constraints are
far less painful to migrate than enum types.

Grids are fixed-width strings of 81 characters, read left to right, top to
bottom. `'1'`–`'9'` are digits; `'0'` is an empty cell. A string is used rather
than an array because it is compact, trivially comparable, and cheap to validate
with a regular expression.

---

## `users`

One row per 42 identity.

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL` | primary key, internal only |
| `intra_id` | `INTEGER NOT NULL` | 42's own user id, from `/v2/me`. **Unique.** The stable identity. |
| `login` | `TEXT NOT NULL` | 42 login. **Unique.** Displayed on leaderboards (Q12). |
| `display_name` | `TEXT` | `displayname` from `/v2/me` |
| `campus_id` | `INTEGER` | stored so D12 can be narrowed later without a migration |
| `campus_name` | `TEXT` | |
| `is_staff` | `BOOLEAN NOT NULL DEFAULT false` | `staff?` from `/v2/me` |
| `intra_active` | `BOOLEAN NOT NULL DEFAULT true` | `active?` from `/v2/me`. Named to avoid confusion with session activity. |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `last_login_at` | `TIMESTAMPTZ` | |

Nothing else from `/v2/me` is stored (`SECURITY.md`). No access token (D11), no
email, no avatar URL.

Login is matched on `intra_id`, never on `login`: 42 logins can in principle
change. The `login` column is refreshed on every sign-in. Its unique constraint
can therefore collide in the pathological case where one user takes a login
another has released — if that happens, keep the stored value and log it rather
than failing the sign-in.

## `puzzles`

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL` | primary key, never exposed by the API |
| `puzzle_date` | `DATE NOT NULL` | Europe/Berlin calendar day |
| `difficulty` | `TEXT NOT NULL` | `CHECK (difficulty IN ('easy','medium','hard'))` |
| `givens` | `CHAR(81) NOT NULL` | `CHECK (givens ~ '^[0-9]{81}$')` |
| `clue_count` | `SMALLINT NOT NULL` | |
| `hardest_technique` | `TEXT NOT NULL` | the tier-deciding technique (`DIFFICULTY.md`) |
| `technique_counts` | `JSONB NOT NULL DEFAULT '{}'` | how often each technique fired |
| `generator_version` | `TEXT NOT NULL` | so a grader change is traceable |
| `seed` | `BIGINT` | traceability only; puzzles are never regenerated (A1) |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

- `UNIQUE (puzzle_date, difficulty)` — the constraint that makes "one puzzle per
  day per difficulty" a database guarantee rather than a convention.
- `INDEX (puzzle_date)`.

## `puzzle_solutions`

| Column | Type | Notes |
|---|---|---|
| `puzzle_id` | `BIGINT` | primary key, FK → `puzzles(id)` `ON DELETE CASCADE` |
| `solution` | `CHAR(81) NOT NULL` | `CHECK (solution ~ '^[1-9]{81}$')` |

**Why the solution lives in its own table.** It is the one secret in the system
(`SECURITY.md`). Keeping it off `puzzles` means the ordinary read path — listing
today's puzzles, loading a game — never has it in memory, and leaking it takes a
deliberate join rather than a careless `SELECT *` reaching a response model that
was not narrowed. One table and one join on the completion path is a small price
for making the mistake structurally hard.

Only the completion check and the generator ever read this table.

## `game_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | primary key, `gen_random_uuid()`. Exposed in URLs. |
| `user_id` | `BIGINT NOT NULL` | FK → `users(id)` `ON DELETE CASCADE` |
| `puzzle_id` | `BIGINT NOT NULL` | FK → `puzzles(id)` `ON DELETE RESTRICT` |
| `state` | `CHAR(81) NOT NULL` | current grid; `CHECK (state ~ '^[0-9]{81}$')` |
| `state_version` | `SMALLINT NOT NULL DEFAULT 1` | format version (Q5) |
| `started_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | official clock starts here (D2) |
| `completed_at` | `TIMESTAMPTZ` | set only after verification (D2) |
| `last_activity_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | inputs and heartbeats |
| `active_seconds` | `INTEGER NOT NULL DEFAULT 0` | server-accumulated (D10) |
| `submission_count` | `INTEGER NOT NULL DEFAULT 0` | full-grid submissions (Q12) |
| `closed_at` | `TIMESTAMPTZ` | materialised by the nightly job; advisory |

- `UUID` rather than a serial: session ids appear in URLs, and sequential ids
  invite enumeration. Authorisation blocks it anyway, but there is no reason to
  publish a count of how many games exist.
- `UNIQUE (user_id, puzzle_id)` — this single constraint enforces D3. One game
  per user per puzzle, forever, no restarts.
- `INDEX (user_id)` for a user's history.
- `INDEX (puzzle_id, completed_at)` for the daily leaderboards, ideally partial:
  `WHERE completed_at IS NOT NULL`.

### Derived status

A session's status is **computed on read** (Q1), never trusted from a column:

    completed        completed_at IS NOT NULL
    closed           not completed, and the puzzle's date is in the past, and
                       (last_activity_at < now - 15 minutes
                        OR now >= puzzle_date + 1 day + 2 hours)
    in_progress      otherwise

`closed_at` exists only so the nightly job can materialise this for statistics
without re-deriving it across the whole table. It is never the source of truth.
Once a day has passed 02:00 the two can no longer disagree.

### Pencil marks

Not built in the MVP (Q5). They arrive as a new nullable `notes JSONB` column
with `state_version` bumped to 2 — an additive migration, not a redesign. That
is the entire reason `state_version` exists now.

## `app_sessions`

The application's own login sessions, kept server-side rather than as a
self-contained signed cookie, so that logout genuinely revokes and a deleted
user's sessions die with them (Q8).

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | primary key |
| `user_id` | `BIGINT NOT NULL` | FK → `users(id)` `ON DELETE CASCADE` |
| `token_hash` | `TEXT NOT NULL` | **Unique.** SHA-256 of the cookie value. |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `expires_at` | `TIMESTAMPTZ NOT NULL` | |
| `last_seen_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

The cookie carries a high-entropy random token; only its hash is stored, so a
database dump does not hand over live sessions. No IP address or user agent is
recorded — neither is needed, and both are personal data.

## `oauth_states`

Short-lived rows bridging the redirect to 42 and the callback.

| Column | Type | Notes |
|---|---|---|
| `state` | `TEXT` | primary key, high-entropy random |
| `code_verifier` | `TEXT NOT NULL` | PKCE |
| `redirect_to` | `TEXT` | where to send the user after login |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `expires_at` | `TIMESTAMPTZ NOT NULL` | ten minutes |

Deleted on use. Single-use enforcement is the reason this is a table and not a
cookie: a cookie can be replayed, a deleted row cannot.

---

## Tables deliberately absent

- **`game_moves`** — no move log in the MVP (D14).
- **`statistics`** — Phase 8 computes from `game_sessions`; no derived table
  until a query is actually too slow.
- **`leaderboard`** — a query, not a table. Same reasoning.

## Constraints that carry product rules

Worth stating plainly, because these are the rules the database itself enforces
rather than the application:

| Rule | Enforced by |
|---|---|
| One puzzle per day per difficulty (A1) | `UNIQUE (puzzle_date, difficulty)` |
| One game per user per puzzle, no restarts (D3) | `UNIQUE (user_id, puzzle_id)` |
| A game is bound to its puzzle forever (D6/D7) | `puzzle_id` never updated; `ON DELETE RESTRICT` |
| Grids are well-formed | `CHECK` regexes on `givens`, `state`, `solution` |

Everything else — the rollover rule, the rate limits, completion verification —
is application logic, and is tested as such.
