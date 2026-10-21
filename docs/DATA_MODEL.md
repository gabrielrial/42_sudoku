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
| `id` | `SERIAL` | primary key, internal only |
| `intra_id` | `INTEGER NOT NULL` | 42's own user id, from `/v2/me`. **Unique.** The stable identity. |
| `login` | `TEXT NOT NULL` | 42 login. **Unique.** Displayed on leaderboards (Q12). |
| `campus_id` | `INTEGER NOT NULL` | from the primary entry of `campus_users` (see below) |
| `campus_name` | `TEXT NOT NULL` | name of that campus, from `campus` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

The table keeps the minimum needed to identify a person and show them. Every
sign-in fetches `/v2/me` again and refreshes the row, so a column added later
fills itself as people log in; nothing is stored "just in case".

Every 42 account is assumed to have a primary campus (`campus_users[].is_primary`).
42's documentation does not say so. The callback rejects an account without one
with a clear error instead of failing on the constraint.

Nothing else from `/v2/me` is stored (`SECURITY.md`). No access token (D11), no
email, no avatar URL.

Login is matched on `intra_id`, never on `login`: 42 logins can in principle
change. `login`, `campus_id` and `campus_name` are refreshed on every sign-in.

The unique constraint on `login` can therefore collide: 42 renames someone and
gives their old login to somebody else, and the server only finds out when the
newcomer signs in. 42 is the authority (`DECISIONS.md` D21): the person signing
in takes the login, and the stale holder is renamed first to their current
login at 42 (`GET /v2/users/:id`). When that cannot be used — 42 fails or does
not know the account, or the login it gives is taken here as well — the stale
holder becomes `former-<intra_id>` until their own next sign-in sets it right.
The takeover is logged by `intra_id`. Nobody is refused a sign-in because of
somebody else's stale row.

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

## `oauth_states`

Short-lived rows bridging the redirect to 42 and the callback.

| Column | Type | Notes |
|---|---|---|
| `state` | `TEXT` | primary key, high-entropy random |
| `code_verifier` | `TEXT NOT NULL` | PKCE (RFC 7636): 128 random unreserved characters; only its S256 challenge leaves the server before the code exchange |
| `expires_at` | `TIMESTAMPTZ NOT NULL` | ten minutes after the login started |

Deleted on use. Single-use enforcement is the reason this is a table and not a
cookie: a cookie can be replayed, a deleted row cannot. Rows of abandoned
logins (the user never came back from 42) are deleted when the next login
starts, so the table stays small.

The row proves the server issued the `state`; it does not prove which browser
it was issued to. `/login` therefore also sets the `state` in a short-lived
cookie, and the callback requires the two to match (`API.md`). Without that, an
attacker could start a login of their own and send the victim a callback link
carrying the attacker's valid `state` (login CSRF).

No `redirect_to` for now: after signing in, the user always lands on the front
end's home page. Returning to the page the user came from is postponed; when it
is added, the target is stored here (server-side, validated once at `/login`)
and must be a same-origin path, to avoid an open redirect.

## `refresh_tokens`

One row per refresh token issued (`DECISIONS.md` D15).

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL` | primary key, internal only |
| `user_id` | `INTEGER NOT NULL` | FK → `users(id)` `ON DELETE CASCADE`. Indexed. |
| `token_hash` | `VARCHAR NOT NULL` | SHA-256 (hex) of the token. **Unique.** The token itself is never stored. |
| `family_id` | `UUID NOT NULL` | shared by every token descended from one sign-in. Indexed. |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `expires_at` | `TIMESTAMPTZ NOT NULL` | seven days after this token was issued |
| `used_at` | `TIMESTAMPTZ` | set when the token is rotated; `NULL` while it is the live one |

A family is one device's session. Rotation seals the current token (`used_at`)
and inserts its successor with the same `family_id`. Logout deletes the family;
so does presenting a sealed token again, which can only mean a copy exists.
Revocation is deletion: there is no `revoked_at`.

A sealed row has to stay while its token could still be presented: it is how
reuse is detected. Nothing deletes expired rows yet, and every refresh adds
one, so the table only grows; a periodic delete of rows past `expires_at` is
pending.

---

## Tables deliberately absent

- **`game_moves`** — no move log in the MVP (D14).
- **`app_sessions`** — requests are authenticated by a signed access JWT
  (D15), verified by its signature plus the user lookup the endpoints need
  anyway. What the server does keep is `refresh_tokens`, one row per refresh
  token; deleting the `users` row cascades to those and ends every session.
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
