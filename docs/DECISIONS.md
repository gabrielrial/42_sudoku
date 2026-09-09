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
| Login attempt | 5 requests/minute per IP |

The burst allowance is doing real work in the first row: a player clearing a
cascade of naked singles enters digits faster than one per second, and a strict
1/s limit would throttle honest play. Implement as a token bucket — refill 1/s,
bucket depth to be tuned — and have the client queue inputs rather than drop
them. The queue must never be allowed to reorder writes.

### D6 — Session binding and the day boundary
A session is permanently bound to the puzzle it started on. A new session may
only ever be created for **today's** puzzle; past days' puzzles are locked
forever.

Across the Europe/Berlin midnight boundary:

- An **active** session may continue and be completed.
- An **inactive** session is closed permanently and can never be resumed. The
  user plays the new day's puzzle instead.

"Active" means recent communication with the server — inputs and/or a heartbeat.
The threshold is not yet decided (Q1).

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
The client submits a full grid; the server does not auto-check as cells fill.
An incorrect submission leaves the game open for further attempts. The count of
failed attempts is stored. The endpoint is rate-limited per D5, which is what
stops repeated submission from becoming a slow brute-force channel.

### D14 — Game state is a snapshot, not a move log
One column on `GameSession` holding the current grid. No `GameMove` table in the
MVP. A move log can be added later if statistics or anti-cheat actually need
one; building it now is the premature abstraction the project rules warn about.

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
| Submissions column | Count of full-grid submissions made before completion |
| Membership | Every user who completes; no opt-out |
| Own row | Always visible to the user, whatever their rank; boards paginate |

"Submissions" counts **completion attempts** — how many times a player submitted
a full grid before getting it right — not individual mis-typed cells. Wrong
digits entered in a cell are never recorded anywhere. Displayed, never ranked on.

A day's boards become final at 02:00 the following day, because every session on
that date is closed by then (D6/Q1). No freeze mechanism is needed.

**Storage impact: none.** `started_at`, `completed_at`, `active_seconds` and
`failed_attempts` are already on `GameSession`. Phase 8 is queries, indexes and
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
React + TypeScript + Vite. Confirmed. A 9×9 grid does not discriminate between
frameworks and the decision is not worth further debate.

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
The folder is not a Git repository yet. Public or private? Which licence?
README aimed at whom?

### Q11 — Puzzle pre-generation operations
How many days ahead does the job generate? What happens if it fails and a day
has no puzzles — an error page, or on-demand generation as a fallback (which
would undermine A1)? Who is alerted?
