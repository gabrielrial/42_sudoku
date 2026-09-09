# Game rules (normative)

This file defines how the product behaves. Code must match it. To change
behaviour, change this file first, in a commit that explains why.

Application timezone: **Europe/Berlin**. Every "day", "today" or "date" below
means a calendar date in that timezone, computed on the server. Users never
supply a date.

---

## 1. Daily puzzles

- Exactly three puzzles exist per date: Easy, Medium, Hard.
- All users get the same puzzle for a given (date, difficulty).
- Every puzzle is valid Sudoku with exactly one solution.
- Puzzles are generated ahead of time and persisted. They are never regenerated
  on demand and never change after creation.

## 2. Starting a game

A puzzle's cells are not visible until its session exists. Listing today's
puzzles tells the user which difficulties are available and what they have
already started or finished; it never returns the grid. Seeing the puzzle is
starting the clock.

- A user may start at most one game session per (user, puzzle).
- **A game session can never be restarted, reset or deleted.** Starting is
  irreversible.
- A user may hold sessions for all three difficulties of the same day.
- A session may only be created for **today's** puzzle. Once the date rolls over
  in Europe/Berlin, the previous day's puzzles are locked: no new session may
  ever be created for them.
- On creation the server records `started_at` and permanently binds the session
  to that specific puzzle. **The binding is immutable.**

## 3. Playing, activity and resuming

- The server holds the authoritative game state.
- Every user input is sent to the server, validated, and persisted.
- Input requests are rate-limited server-side. A client cannot submit inputs
  faster than the limit, whatever it sends.

### Within the puzzle's own day

The user may leave and return freely. The game is restored from the server's
stored state, not from anything the client kept. There is no time pressure and
no penalty for closing the tab.

### Across the Europe/Berlin midnight boundary

A session is tied to the day it belongs to. After the rollover:

- **An active session may continue.** A user who is mid-play at 00:00 keeps
  playing and may finish the previous day's puzzle.
- **An inactive session is closed permanently.** A user who left the puzzle and
  comes back the next day cannot resume it. That puzzle is gone for them. They
  play the new day's puzzle instead.

> 2026-09-09 23:55 — the user starts the September 9 Hard puzzle.
> 2026-09-10 00:00 — the date changes.
> Still playing → they may continue and finish the **September 9** puzzle.
> Left and returned on September 10 → the session is closed. They start the
> **September 10** puzzle.

### What "active" means

The server cannot see whether a browser tab is open. Activity is defined by
recent communication with the server — game inputs and/or a periodic heartbeat
from the client.

The client sends a heartbeat every **60 seconds** while a game is open. Inputs
count as activity too.

A past-day session is closed when **either** of these is true, whichever comes
first:

- it has been inactive for more than **15 minutes**; or
- the clock passes **02:00 Europe/Berlin** — a hard cap of two hours past the
  rollover, applied regardless of activity or heartbeats.

All three values are configuration, not constants in code. The closed state is
computed on read from `last_activity_at` and the puzzle's date, so it cannot
drift; a nightly job materialises it for statistics only.

Two properties the eventual rule must have:

- The check is **continuous, not a single test at midnight.** A session on a
  past date that goes idle at 00:30 is closed at 00:30 + threshold, not given
  the rest of the window.
- A user may hold a continuing past-day session *and* start today's puzzles at
  the same time. These are different puzzles and do not conflict.

### What "validating an input" means

The server checks that an input is **legal**, not whether it is **correct**.

Legal means: the session exists and belongs to the caller; the session is not
completed and not closed; the target cell is not a given; the value is 1–9 or
empty; the request is within the rate limit.

The server does **not** tell the client whether a value matches the solution.
See `SECURITY.md` § "The solution oracle" for why this distinction is
load-bearing.

## 4. Completion and timing

- The official solving time is authoritative on the server:
  `completed_at - started_at`.
- An **active time** is recorded alongside it, accumulated from client activity
  with idle gaps excluded. It is advisory only. The official time is the
  unfalsifiable one; active time is the honest-looking one.
- The frontend timer is decoration. It is never trusted, never submitted, and
  never used to compute a stored time.
- `completed_at` is written only after the backend has verified the submitted
  grid against the stored solution.
- Completion is explicit: the client submits a full grid. An incorrect
  submission leaves the game open; the attempt is counted and stored.
- Only **full-grid submissions** are counted. A wrong digit typed into a cell is
  an ordinary input, is never flagged as wrong (the server does not know or say
  whether a cell is correct), and is never recorded as an error.
- Completion is idempotent. Submitting a correct grid twice does not move
  `completed_at`.
- A game is recorded against the puzzle it was started on, regardless of when it
  is completed. A game started on September 9 and finished at 00:05 on
  September 10 is a completion of the **September 9** puzzle. Never the
  September 10 one.
- Because the official time is pure wall-clock between two server timestamps,
  **pausing has no effect on it.** A pause button may exist as a UI convenience
  (hiding the grid), but it does not stop the official clock. Do not build a
  pause feature that implies otherwise.

## 5. Known consequences of these rules

Written down so they are not discovered by surprise in three months.

- The heartbeat is load-bearing twice over: it drives the active-time figure
  *and* it decides whether a past-day session survives. If it stops, a session
  in progress can die. The threshold must be generous enough for genuine
  thinking time on a hard puzzle — several minutes of staring at a grid is
  normal play, not idleness.
- There is no way to abandon a game deliberately. Within its own day, an
  unfinished session simply stays unfinished, and because restarting is
  forbidden, the user cannot try that puzzle again.
- A session can end in one of three terminal states: completed, closed by
  rollover, or still open on the current day. Statistics need to distinguish
  the second from the third.
- The official time of a game that survives midnight can still be large. Active
  time exists so that comparisons remain meaningful.
