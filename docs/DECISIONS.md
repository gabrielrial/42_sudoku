# Decisions and open questions

Two lists. **Decided** is settled — treat these as given, do not relitigate them
in a working session. **Open** blocks or shapes work that is coming; answer
before the phase that needs it starts.

**Numbers are stable.** When an open question is answered it moves up into
Decided keeping its `Q` number, so that references from other documents never
go stale. Nothing is ever renumbered.

---

# Decided

### D1 — Application timezone is Europe/Berlin
All day boundaries are computed server-side in that zone. Storage is UTC
`timestamptz`; `puzzle_date` is a plain `DATE`.

### D2 — Solving time is authoritative on the server
`completed_at - started_at`, both written by the server. `started_at` on session
creation, `completed_at` only after the backend has verified the submitted grid.
The frontend timer is decoration and is never submitted or trusted.

### D3 — A game can never be restarted
Starting a puzzle is irreversible. No reset, no delete, no second attempt.

### D4 — Games are resumable within their own day
The server holds the authoritative state. Every input is sent to the server,
validated for legality, and persisted. Within the puzzle's own day, leaving the
page loses nothing. Across the day boundary, D6 applies.

### D5 — Rate limits
Server-side, enforced per session or per IP as noted. Configurable, and to be
reviewed during the LAN stage with real users.

| Endpoint | Limit |
|---|---|
| Game input | 1 request/second per session, with a small burst allowance |
| Completion submission | 5 requests/minute per session |
| Heartbeat | 2 requests/minute per session |
| Login attempt | 5 requests/minute per IP |

The burst allowance is doing real work in the first row: a player clearing a
cascade of naked singles enters digits faster than one per second, and a strict
1/s limit would throttle honest play. Implement as a token bucket — refill 1/s,
bucket depth to be tuned — and have the client queue inputs rather than drop
them. The queue must never be allowed to reorder writes.

Everything a signed-in player does is limited per game session, not per IP: a
whole 42 campus can reach the server from one public address. How the limiter
is built is D17.

### D6 — Session binding and the day boundary
A session is permanently bound to the puzzle it started on. A new session may
only ever be created for **today's** puzzle; past days' puzzles are locked
forever.

Across the Europe/Berlin midnight boundary:

- An **active** session may continue and be completed.
- An **inactive** session is closed permanently and can never be resumed. The
  user plays the new day's puzzle instead.

"Active" means recent communication with the server — inputs, full-grid
submissions and/or a heartbeat (D22). The threshold is Q1.

### D7 — Completion counts for the puzzle the game started on
Started 2026-09-09 23:55, completed 2026-09-10 00:05 → a completion of the
2026-09-09 puzzle, never the 2026-09-10 one. The binding is immutable.

### D8 — Deployment happens in three stages
Local → local network → public. Each stage begins only when the previous is
stable. The hosting provider is chosen at stage 3, not before.

### D9 — Pause cannot stop the official clock
It follows from D2. A pause button may hide the grid as a UI convenience, but it
must not imply that the recorded time stops.

### D10 — Two times are recorded, not one
`completed_at - started_at` is the **official** time: unfalsifiable, computed
from two server timestamps. An **active time** is accumulated from client
activity with idle gaps excluded and is **advisory only**. Any future ranking
decides for itself which to use; that decision stays open until Phase 8.

The same heartbeat that feeds active time is the activity signal for D6. One
mechanism, two purposes — but note that this makes it load-bearing for
correctness, not just for statistics.

### D11 — The 42 access token is not stored
Fetch `/v2/me` once at callback, persist the fields we need, discard the token.
The application then runs entirely on its own session. Storing a third-party
token is a liability with no MVP benefit, and 42's rate limit (2 requests/second,
1200/hour per application) means we should not be calling their API on normal
request paths anyway. Revisit only if a feature genuinely needs live 42 data.

### D12 — Any authenticated 42 account may play
No campus, staff or activity restriction in the MVP. Campus and account status
are stored so the policy can be tightened later without a migration.

### D13 — Completion is explicit, and failures are counted
The player asks for a check once the grid is full; the server does not
auto-check as cells fill. It checks the grid it already holds, not one sent with
the request (`LESSONS.md` D). An incorrect submission leaves the game open for
further attempts. Every submission is counted (`submission_count`, D22). The
endpoint is rate-limited per D5, which is what stops repeated submission from
becoming a slow brute-force channel.

### D14 — Game state is a snapshot, not a move log
One column on `GameSession` holding the current grid. No `GameMove` table in the
MVP. A move log can be added later if statistics or anti-cheat actually need
one; building it now is the premature abstraction the project rules warn about.

### D15 — Login sessions: a short access JWT and a rotating refresh token
Decided 2026-09-29, replacing a server-side `app_sessions` table. Revised
2026-10-01: the single seven-day JWT revoked through `users.token_version` was
replaced by the design below.

After the 42 callback the server issues two tokens, each in its own cookie.
Both cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production.

- **Access token:** cookie `access_token`, `Path=/`, 15 minutes. A JWT, HS256
  via PyJWT, signed with `SECRET_KEY`. The algorithm is pinned when decoding
  (`algorithms=["HS256"]`), never taken from the token header. Claims: `sub`
  (`str(users.id)`), `iat`, `exp`. Nothing else: the payload is readable by
  anyone holding the cookie, so it carries no personal data.
- **Refresh token:** cookie `refresh_token`, `Path=/api/auth`, so the browser
  sends it to the refresh and logout endpoints and nowhere else. An opaque
  random value (`secrets.token_urlsafe(32)`), valid seven days. The server
  keeps only its SHA-256 hash, in `refresh_tokens` (`DATA_MODEL.md`).
- **Verification:** every authenticated request checks the access token's
  signature and `exp`, then loads the user named by `sub`, which the game
  endpoints need anyway. No row gives `401`, so deleting a user ends their
  sessions (Q8).
- **Rotation:** `POST /api/auth/refresh` seals the presented refresh token
  (`used_at`), issues its successor in the same family with a fresh seven
  days, and issues a new access token. A user who comes back at least once a
  week stays signed in.
- **Theft detection:** presenting a sealed refresh token again means two
  parties hold a copy. The whole family — every token descended from that
  sign-in — is deleted and the request gets `401`. Thief and user are both
  signed out on that device; the user signs in with 42 again.
- **Logout** deletes the family of the refresh token it receives: this device
  only. Other devices keep their sessions.
- **Revocation** is deleting rows. There is no `revoked_at` column.
- **Emergency:** rotating `SECRET_KEY` invalidates every access token, forged
  ones included. It does not sign anyone out by itself — refresh tokens are not
  signed with it, so clients simply refresh back in. To sign everyone out, also
  delete every row of `refresh_tokens`.

Consequence for the front end: on `401 not_authenticated` it calls
`POST /api/auth/refresh` **once** and retries the request; if that also fails,
the user is signed out. Two refreshes must never run at the same time: both
would present the same token, and the second looks exactly like theft. One
shared in-flight request, awaited by every caller.

What this gives up, stated so nobody rediscovers it: after a logout, or after
a stolen refresh token is detected, the access token already issued stays
valid until it expires — up to 15 minutes. Closing that gap means a database
check on every request (a `sid` claim matched against `refresh_tokens`);
considered and parked on 2026-10-01.

### D16 — Only 42 accounts; no local accounts
Decided 2026-10-06.

The only way in is 42 OAuth. There is no sign-up form, no local username and no
password: a `users` row is created on a person's first successful 42 sign-in,
keyed on `intra_id`. The application is meant for the 42 community, not the
public, and 42 already authenticates its members.

The username/password login built during Phase 4 was a learning step towards
the session design (access and refresh tokens, rotation, cookies, CSRF, rate
limiting). Those parts stay; the sign-up and login endpoints, the password
columns, argon2 (`pwdlib`) and their tests are removed.

Who among 42 accounts may play is D12 (confirmed 2026-10-06: any 42 account).

### D17 — Rate limiting is an in-house token bucket
Decided 2026-10-01.

`app/services/rate_limit.py` implements D5's token bucket directly: one bucket
per key, refilled at a constant rate, its capacity being the burst allowed. A
refused request gets `429` with `Retry-After` in whole seconds, rounded up. The
clock is injectable, so the tests control time instead of sleeping. Buckets
that have refilled completely are forgotten, so the table of keys stays small.

Why not `slowapi`, the usual library for this in FastAPI: the limiter was
written to learn how rate limiting works inside, not because `slowapi` could not
do the job. It stays because it is already built and tested, it answers in the
common error envelope with `Retry-After` without any adapter, it adds no
dependency outside the agreed stack, and it is small enough to explain line by
line.

Accepted limits for deployment stages 1 and 2: the buckets live in the
process's memory. A restart empties them, and with several worker processes
each one counts on its own. Revisit if the API ever runs as more than one
process.

### D18 — PKCE with 42, although 42 does not document it
Decided 2026-10-10.

The login uses PKCE (RFC 7636, method `S256`) on top of `state` and the client
secret. The server creates the `code_verifier`, keeps it in `oauth_states`, and
sends 42 only its challenge in the authorize redirect; the verifier itself
goes to 42 in the code exchange. The browser never sees it.

42's documentation does not mention PKCE, so whether 42 checks it is unknown.
For a client that holds a secret, PKCE is defence in depth (OAuth 2.1 and
RFC 9700 recommend it anyway), and learning it is part of the point of this
project.

To be checked with the real application in Phase 4: exchange a code with a
**wrong** verifier. If 42 accepts it, PKCE protects nothing against 42, and
`SECURITY.md` must say so.

### D19 — The environment is always declared; the fake provider can play anyone
Decided 2026-10-20 (`PLAN.md` P4).

`APP_ENV` has no default, neither in `Settings` nor in the compose file. A
process that does not say which environment it is in refuses to start. The
fake identity provider is refused in `production` (unchanged); what this adds
is that forgetting `APP_ENV` on a LAN or public machine can no longer leave
the fake provider quietly letting anyone in.

In fake mode, `GET /api/auth/login?as=<login>` signs in as that made-up user,
so two people — or two browsers — can be tested against each other by hand
(authorisation between users, Phase 5). The login is validated; fake users
never share an `intra_id` with a real 42 account. The real provider ignores
`as`. The automated tests do not need it: they create their users directly.

### D20 — Database tests fail, never skip, without their database
Decided 2026-10-20 (`PLAN.md` P5, option A).

A test that needs PostgreSQL fails when `DATABASE_URL` is unreachable or does
not name a `*_test` database. There is no opt-out variable. A skipped
database test looks green and proves nothing (`LESSONS.md` 14). Running the
engine alone needs no database: `pytest tests/sudoku` never touches the
fixture.

### D21 — A login 42 has reassigned goes to its new holder
Decided 2026-10-21. Replaces `DATA_MODEL.md`'s earlier rule (keep the stored
login and log the collision), which said nothing about a newcomer and turned
that case into a `500`.

42 is the authority on who holds a login today. When the login of the person
signing in is held here by another account, that account is renamed to what 42
calls it now, and the person signing in takes the login. The `UNIQUE` on
`users.login` stays, so a leaderboard never shows two people under one name.

Finding out the other account's login is one call, `GET /v2/users/:id`, with
an application token (client credentials). The developer checked on 2026-10-20
that 42 serves that endpoint to an application token, and on 2026-10-21 that
42 issues that token for a form-encoded `POST /oauth/token` with
`grant_type=client_credentials`, `client_id` and `client_secret` — the
request the server sends. The token is fetched for
that call and discarded, as D11 asks of tokens, and the call happens only on a
collision, so the normal sign-in still makes exactly the two calls of D11.

Fallback, so that one person's stale row never locks another out:
`former-<intra_id>` when 42 fails or does not know the account, or when the
login it gives is taken here too. Chains of renames are not followed. The stale
holder's next sign-in replaces the placeholder with the truth.

### D22 — Game API details left open by the documents
Decided 2026-10-24, before Phase 5.

- **`submission_count` counts every full-grid submission, the correct one
  included.** A first-time solve is 1, which is what `API.md`'s example shows
  and what a "Submissions" column should mean to a reader.
- **Cell inputs: a token bucket of 10, refilled at 1 per second, per game
  session** (D5's "small burst allowance", made concrete). Someone clearing a
  cascade of singles types several digits a second; a bucket of 10 lets that
  through and still holds a script to one input a second over time.
- **A heartbeat or an input on a completed game answers `409 game_completed`**,
  as `API.md` already says for inputs. Nothing about a finished game changes.
- **`game_sessions.closed_at` exists from the first migration and stays empty in
  the MVP.** The nightly job that fills it serves Phase 8's statistics only;
  the MVP computes the closed state on read (Q1), which is the only source of
  truth anyway.
- **A full-grid submission is activity**, like an input (added 2026-10-25, from
  the Stage 5 review): pressing "check" is as plainly playing as typing a
  digit. It moves `last_activity_at` and adds active time. It opens nothing:
  five submissions a minute at most, and the 02:00 cap holds regardless.
- **Active time never exceeds official time.** Each gap is rounded to whole
  seconds on its own, so inputs 0.6 s apart could add up past the wall clock;
  on completion `active_seconds` is capped at `official_seconds`.

### Q1 — The activity rule behind D6 (answered)

| Parameter | Value |
|---|---|
| Inactivity threshold | 15 minutes without server contact |
| Heartbeat interval | 60 seconds while the game is open |
| Hard cap | 02:00 Europe/Berlin — two hours past rollover |
| Enforcement | Computed on read, plus a nightly job that materialises the state for statistics |

A session on a past date is closed when **either** it has been inactive for more
than 15 minutes **or** the clock passes 02:00 — whichever comes first. The hard
cap is checked independently of activity, so no amount of forged heartbeat
traffic extends a session past 02:00.

All values are configuration, not constants in code, and are revisited at the
LAN stage.

"Computed on read" means a session's closed state is derived from
`last_activity_at` and its puzzle date every time it is loaded, so it can never
drift out of sync. The nightly job exists only so that statistics can count
closed sessions without scanning; it never decides anything the read path
would decide differently.

### Q2 — Difficulty definition (answered)
Difficulty is the hardest technique a solver is forced to use to finish without
guessing. Three tiers: Easy = hidden singles; Medium = pairs, pointing pairs,
box-line reduction; Hard = triples and X-Wing. Anything the ladder cannot finish
is **discarded, not shipped as Hard**.

The full specification — ladder, grading algorithm, generation procedure,
metadata and verification requirements — is in `DIFFICULTY.md`, which is
normative for Phase 2.

### Q3 — The 42 OAuth application (answered: register it at Phase 4)
No application is registered yet, and none is needed until Phase 4. Registration
is self-service and instant (intra → Settings → API → Register a new app), so
doing it early buys nothing and means holding a secret for weeks before it is
used.

At Phase 4, register one application and note:

- the client ID (UID) and client secret — the secret goes into a local `.env`
  and nowhere else: not in the repository, not in a chat, not in a screenshot;
- scope `public`, which is all `/v2/me` needs;
- redirect URIs. One application can hold several, so a single registration can
  serve all three deployment stages: `localhost` for development, the LAN
  machine's address for stage 2, the public domain for stage 3. Add each one as
  its stage arrives.

### Q12 — Leaderboard (answered)
Three leaderboards, one per difficulty, each scoped to **a single day**:
"today's Hard leaderboard". All-time standing lives in My statistics as separate
aggregates (most completions, best average, longest streak), never as a
mixed-puzzle time ranking — different puzzles of the same tier are not equally
hard, so such a board would mostly measure which day a user played.

| Aspect | Decision |
|---|---|
| Ranking metric | Official time (`completed_at - started_at`) |
| Also displayed | Active time, as context |
| Tie-break | Earlier `completed_at` wins |
| Identity shown | 42 login |
| Submissions column | Count of full-grid submissions, the correct one included (D22) |
| Membership | Every user who completes; no opt-out |
| Own row | Always visible to the user, whatever their rank; boards paginate |

"Submissions" counts **completion attempts** — how many times a player submitted
a full grid, the correct one included, so a first-time solve shows 1 — not
individual mis-typed cells. Wrong digits entered in a cell are never recorded
anywhere. Displayed, never ranked on.

A day's boards become final at 02:00 the following day, because every session on
that date is closed by then (D6/Q1). No freeze mechanism is needed.

**Storage impact: none.** `started_at`, `completed_at`, `active_seconds` and
`submission_count` are already on `GameSession`. Phase 8 is queries, indexes and
interface only.

### Q13 — A puzzle is never visible before its session exists (answered: adopted)
Seeing the puzzle *is* starting the clock.

- `GET /api/puzzles/today` returns which difficulties exist today and the
  caller's status for each (not started / in progress / completed). **It never
  returns cells.**
- The grid is returned only by session creation and by `GET /api/games/{id}`,
  both of which imply `started_at` is already set.

This closes the solo pre-solving route: a player cannot study the grid on paper
and then start a session to type the answer in, because there is no way to see
it without the clock running, and D3 forbids spending a second attempt.

Residual, accepted: two users can collude — A starts and screenshots, B solves
offline and plays fast. That costs A their own attempt and requires
coordination.

Consequence for the signed-out page: it shows what the site is and a login
button, never a puzzle. This supersedes the earlier note under Q7.

### Q4 — Frontend stack (answered)
React + TypeScript + Vite. Confirmed. A 9×9 grid does not discriminate between
frameworks and the decision is not worth further debate.

### Q5 — Pencil marks (answered: after the MVP, but plan for them)
Not built in the MVP. The game-state snapshot format reserves room for them and
carries a version number from the first migration, so that adding them later is
a format upgrade rather than a redesign.

### Q6 — Mobile support (answered: yes)
The interface is responsive and usable on a phone. The board must survive a
375px viewport and input must work without a hardware keyboard — an on-screen
number pad, not a text field. Keyboard input remains supported on desktop.

### Q7 — Home page (answered)
The signed-in home page offers exactly five things:

1. Easy — play today's Easy puzzle
2. Medium — play today's Medium puzzle
3. Hard — play today's Hard puzzle
4. My statistics
5. Leaderboard

**MVP scope:** only items 1–3 are functional in the MVP. Statistics and the
leaderboard are Phase 8. The layout is designed with all five slots from the
start so that nothing is rearranged when they arrive, but the two unbuilt
entries are visibly inactive rather than broken links.

A *signed-out* visitor sees a short explanation of what the site is and a 42
login button — and no puzzle, per Q13.

### Q11 — Puzzle pre-generation operations (answered)
Decided 2026-10-23, with the measurements behind it: a day's three puzzles take
about 17 s to generate (Easy 0.2 s, Medium 0.5 s, Hard 16 s on average, 35 s at
worst), almost all of it spent finding a Hard.

| Question | Answer |
|---|---|
| How many days ahead | **7**: today and the six days after it always exist |
| What runs it | its own compose service, `puzzles`: same image and code as `api`, another command (`python -m app.jobs.generate_puzzles --every 3600`). Its own process, so a 16-second Hard never slows the API |
| How often | every hour. Idempotent: what already exists is left alone, so a restart or a second run is harmless |
| If a generation fails | retried with another seed; a day still missing is logged as a warning and tried again next hour |
| If a day has no puzzles anyway | `POST /api/games` answers `503 puzzle_unavailable` (`API.md`). No on-demand fallback: it would undermine A1 and make a player wait |
| Who is alerted | open: Q14 |

Generating on demand at midnight was rejected for the same reason as in A1: the
first player of the day would wait on a Hard.

---

## Adopted from the design review — say so if you disagree

Written into the docs, reversible now and expensive to reverse later.

### A1 — Puzzles are pre-generated and persisted, not derived from a seed
Deterministic regeneration from `date + difficulty` is not reproducible in
practice: any change to the generator, its libraries or the Python version
silently changes past puzzles and breaks stored games. Puzzles are generated
ahead of time, stored with their solution, unique on `(puzzle_date, difficulty)`,
and never regenerated. A seed may be recorded as metadata for traceability.

Generating a graded hard puzzle with a uniqueness proof takes real time, so lazy
generation at 00:00 would make every early user wait on the same cold start.

### A2 — The Sudoku engine is built before authentication
It is the only novel logic in the project, has no external dependencies, and is
fully testable offline. OAuth is high-friction, low-learning, and blocks nothing
once a dev-mode fake identity provider exists.

### A3 — A dev-mode fake identity provider exists from Phase 4 onward
So that local development, the test suite and CI never call the 42 API.

### A4 — No endpoint reports whether a single cell is correct
See `SECURITY.md` § "The solution oracle". Client-side duplicate highlighting
gives the player feedback without leaking anything.

### A5 — A demo board before Phase 6, with its puzzle in the bundle
Asked for by the developer during Phase 2: a front end showing one puzzle that
can be filled in — select a cell, type or tap a digit, erase — and nothing
more. No checking, no timer, no saving.

The puzzle is a constant in `frontend/src/game/demoPuzzle.ts`, generated by the
engine from a recorded seed, **givens only**. It deliberately does not come from
an endpoint: an endpoint that serves a puzzle outside a game session is exactly
what Q13 and `API.md`'s "deliberately absent" list rule out, and a temporary
one would be easy to forget. In Phase 6 the board takes its givens from
`POST /api/games` and the file is deleted.

This bends the rule that phases run in order. The board, number pad and
keyboard handling are Phase 6 work that will be kept; only the data source
changes.

---

# Open

Nothing here blocks Phases 1–6. All of it should be settled before Phase 9.

## Low — can be answered later, but do not forget

### Q8 — GDPR and privacy
Real identities of real EU students. Needed before stage 3: a short privacy
note, a documented deletion path, and a decision on how long data is kept.

### Q9 — Is this graded as a 42 curriculum project?
If so it may carry constraints — a required run command, a defence, forbidden
libraries — that change the setup.

### Q10 — Repository housekeeping
The repository exists, on GitHub (`gabrielrial/42_sudoku`). Still open: public
or private? Which licence? README aimed at whom?

### Q14 — Who is told when puzzle generation fails
Split from Q11 on 2026-10-23. Until stage 3 a failure is a warning in the log of
the `puzzles` service and nothing more. Before the public stage: who hears about
it, and how (mail, a chat message, a health check that turns red)?
