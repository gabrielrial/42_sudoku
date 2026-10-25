# Problems hit, and what fixed them

A running record, so the same hour is not lost twice. Newest phase last.

---

# Phase 1 — operational

## 1. Git could not run: stale `.git/index.lock`

**Symptom.** The first `git add` printed `unable to unlink … Operation not
permitted`, and every command after it failed with *"Another git process seems
to be running in this repository."*

**Cause.** Git writes `.git/index.lock` and removes it on success. The assistant's
sandboxed shell cannot delete files in a connected folder by default, so the lock
survived and jammed everything behind it.

**Fix.** Grant file-deletion permission for the folder. The grant is **per
session**, so it will be needed again in every new chat — ask for it at the
start rather than discovering it mid-commit.

## 2. No PyPI and no npm registry from either shell

**Symptom.** `pip install` and `npm install` both returned 403 from the egress
proxy, in the cloud workspace and on the machine's sandboxed shell alike.

**Consequence.** ruff, mypy, pytest and `tsc` were never executed before the
first push. Three of the bugs below would have been caught in seconds locally.

**How it was handled.** Verify what can be verified without installing anything:
every Python file parsed with `ast`, `pyproject.toml` and the frontend JSON
validated, line lengths checked, and the two pure-stdlib modules (`clock.py` and
the import-boundary test) run by hand. The boundary test was also checked
against a deliberate violation, so it was not passing vacuously.

**Lesson.** State plainly what was not verified instead of implying it was. CI
was the first real execution, and it found real problems.

## 3. Frontend loaded but said "Backend: unreachable"

**Symptom.** `localhost:5173` rendered the page; every API call failed.

**Cause.** `vite.config.ts` proxied `/api` to `http://localhost:8000`. **Inside a
container, `localhost` is that container** — not the host, not a sibling. The
backend was never there.

**Fix.** `API_TARGET: http://api:8000` in the compose file: on a compose network
services are reachable by service name. The `localhost` fallback stays in
`vite.config.ts`, because it is correct when running `npm run dev` on the host.

**Lesson.** Container-to-container traffic uses service names on internal ports;
the browser uses published ports on `localhost`. Confusing the two is the most
common Docker mistake, and it will return at Phase 7 (LAN deployment).

## 4. `npm ci` failed — no lockfile

**Symptom.** The frontend CI job failed regardless of the code.

**Cause.** `npm ci` requires `package-lock.json`, and none existed because the
npm registry was unreachable when the scaffolding was written.

**Fix.** `npm install` in `frontend/`, commit the lockfile. Re-run it whenever a
dependency changes, or the lockfile and `package.json` drift apart and `npm ci`
rejects them again.

## 5. `npm install` run in the wrong directory

**Symptom.** `ENOENT: no such file or directory, open '…/42_sudoku/package.json'`,
then stray `package-lock.json` files appeared in the repository root and in
`docs/`.

**Cause.** The command was run from the project root instead of `frontend/`.
npm failed to find a manifest but still wrote a lockfile where it stood.

**Fix.** Run it in `frontend/`; delete the strays. Note that `npm install && cd ..`
correctly skipped the `cd` because npm failed — the `&&` did its job.

## 6. `git push` rejected: no upstream

**Symptom.** *"The current branch main has no upstream branch."*

**Fix.** `git push --set-upstream origin main`, once. Plain `git push` afterwards.

## 7. TypeScript: `Cannot find name 'process'`

**Symptom.** The frontend CI job failed at the typecheck step.

**Cause.** `vite.config.ts` reads `process.env.API_TARGET`. `process` is a Node
global, and `tsconfig.json` listed only `vite/client` under `types`, so
TypeScript did not know it existed. The code ran fine; the types were incomplete.

**Fix.** Add `@types/node` and `"node"` to the `types` array.

## 8. `ruff format --check` failed on one line

**Symptom.** CI stopped at step 2 of 4. A hand-wrapped `raise ValueError(...)`
in `config.py` spanning three lines "would be reformatted".

**Cause.** The statement is 99 characters — inside the 100-character limit — so
the formatter collapses it. The hand-wrapping was simply wrong about where the
boundary fell.

**Fix.** Collapse it. Better fix: `pip install pre-commit && pre-commit install`,
after which staged Python is formatted automatically and this class of failure
never reaches CI again.

**Lesson.** Do not hand-format what a formatter owns.

---

# Phase 4 — operational

## 9. Commits that left CI red

**Symptom.** Several Phase 4 commits failed CI: files committed before
`ruff format` ran (`0502db8`, and again on 2026-10-10); a commit holding the
tests but not the implementation (`5c32d19`); a `raise not_authenticated`
without parentheses, which turned a `401` into a `500`.

**Fix.** Before every commit, in the container: `ruff format .`,
`ruff check --fix .`, `mypy src`, the tests. Lesson 8's `pre-commit install`
makes the first two automatic.

## 10. Failing tests deleted "because they did not pass"

**Symptom.** 2026-10-08: four commits pushed, all red. Removing the sign-up
schema also removed `PASSWORD_MAX_LENGTH`, which login still used; the length
check was then dropped from login, two tests failed, and they were deleted.

**Fix.** Rebuilt as a single commit with `git reset --soft` and pushed with
`git push --force-with-lease`.

**Lesson.** A test that fails after a change is usually right. Delete a test
only when it has become obsolete, and in the same commit as the change that
made it so.

## 11. `Any` made mypy blind

**Symptom.** `get_user_by_email` used `User.email`, which never existed, and
neither mypy nor anything else complained.

**Cause.** Models declared with `Column(...)` on a `declarative_base()` class
were `Any` to mypy, so no attribute of `User` was checked at all.

**Fix.** SQLAlchemy 2.0 models: `DeclarativeBase` and `Mapped[...]`.

**Lesson.** An `Any` is not a missing error; it is a region where the type
checker cannot see.

## 12. A new file left out of a commit

**Symptom.** 2026-10-10: the `users` change was pushed without its migration.

**Cause.** A new file is untracked (`??`); `git add -u` and `git commit -a`
only pick up files git already knows. CI did not notice either, because the
tests build the schema with `create_all`, not from the migrations.

**Lesson.** Read `git status` just before `git commit`. `--amend` replaces the
last commit; a plain `commit` adds another.

## 13. An empty migration was merged

**Symptom.** 2026-10-12: PR #10 was merged with a migration that created
nothing. `oauth_states` existed only in the tests.

**Cause.** `models/__init__.py` named `"OAuthState"` in `__all__` without
importing it. `__all__` imports nothing, so autogenerate never saw the table.
`ruff check` reported it (F822) and the warning was ignored. The tests passed
because they import the model directly, and `alembic check` passed because the
table already existed in the development database.

**Fix.** Import the model, generate the migration again, through a new pull
request: `main` is not rewritten.

**Lesson.** Read every generated migration before applying it. A downgrade and
upgrade round trip proves something only if you watch the table disappear and
come back (`\dt`). Do not merge a branch until it is complete and reviewed.

## 14. Database tests skipped, not failed

**Symptom.** 2026-10-01: "6 passed, 49 skipped" looked green.

**Cause.** The database tests need `sudoku_test`, and `make` had deleted it
along with the rest of the volume. Without it they skip.

**Fix.** `docker compose exec db createdb -U sudoku sudoku_test` after every
`make` (`README.md`, Checks). Read the skip count every time.

**Since 2026-10-21 (Stage 2):** the fixture fails instead of skipping (D20);
PostgreSQL creates `sudoku_test` itself on a fresh volume (`db-init/`); and
plain `make` no longer deletes the volume at all.

## 15. Rewriting pushed history

After `reset --soft` or `--amend` on a branch that was already pushed, a
"non-fast-forward" rejection is expected. The answer is
`git push --force-with-lease`, never `git pull`, which would merge the old
history back in — and only on a branch nobody else uses. Look at the command
before pressing Enter, and at `git log -1` after: one amended commit went out
with another project's message, recalled from the shell history.

## 16. The `.venv` is not the container

`pip show` in the Mac's `.venv` says nothing about the environment the tests
and CI use. Ask the container: `docker compose exec api pip show <package>`.

## 17. zsh and pasted comments

The developer's zsh does not treat `#` as a comment in pasted commands, so a
line with a trailing comment fails. Paste commands without comments, one at a
time.

## 18. A tuned `.env` turned the suite red

Once compose passed every setting to the container, a longer
`GAME_INACTIVITY_MINUTES` in `.env` reached the tests, which assert the decided
values: four failed on correct code. `tests/conftest.py` now runs the suite on
each setting's declared default. A test that needs another value says so with
`model_copy`, never through the environment.

## 19. `PGTZ` beat `options=-c timezone=UTC`

The connection's startup option was meant to fix the session zone to UTC;
`PGTZ` in the process's environment overrode it. A setting made by a `SET`
once the connection is open cannot be overridden from outside — and it must be
committed, or the pool's first rollback undoes it. `test_time_zones.py` tries
both ways in: `ALTER DATABASE ... SET timezone` and `PGTZ`.

---

# Design corrections

Not bugs — reasoning that was wrong and got caught before it became code.

## A. "Official time stops cheating"

Official time (`completed_at - started_at`) cannot be forged *downward*, which is
why it ranks the leaderboard. But it is **not** a defence against solving the
puzzle on paper first and then typing the answer in: every timestamp in that
scenario is genuine, and the resulting time is excellent.

The actual defence is access control, not timing — a puzzle's cells are never
returned before a session exists (`DECISIONS.md` Q13), so seeing the puzzle is
starting the clock.

## B. Server-authoritative time plus resume made times meaningless

Recording `completed_at - started_at` while allowing indefinite resume meant a
game left open overnight recorded an eleven-hour "solving time". Resolved by
recording two figures — official and active — and by the rollover rules in
`GAME_RULES.md` that close a past-day session after 15 minutes idle or at 02:00,
whichever comes first.

## C. Per-cell validation would have been an oracle

An endpoint reporting whether a single cell is correct turns 729 requests into a
full solution. Hence: the server validates that an input is *legal*, never that
it is *correct* (`SECURITY.md`).

## D. `POST /complete` originally took the grid in the body

Which creates two notions of "the submitted grid" that can disagree — and the
client's copy is the untrustworthy one. The endpoint now takes no body and
verifies the state the server already holds.

## E. The `state` row alone did not stop login CSRF

The first OAuth design kept `state` only in `oauth_states`. That proves the
server issued it, not to which browser. An attacker could start a login, take
the valid `state`, and send a victim the callback link with the attacker's own
code: the victim ends up signed in to the attacker's account. PKCE does not
help, because code and verifier both belong to the attacker. Hence the
short-lived `state` cookie that ties the callback to the browser that started
the login (`DATA_MODEL.md`, `oauth_states`).

## F. A label next to a puzzle is not a rating

The first plan for `DIFFICULTY.md`'s published-puzzle check took SudokuWiki's
"X-Wing exemplars" at their word: "require the X-Wing strategy at some point
but are otherwise trivial". The grader discarded all ten. Its own solver, asked
for the solve path, needs a Chute Remote Pair for the first one — a technique
beyond tier 3 — so the grader was right and the label was not. The reference is
now what an independent solver actually did, recorded with its version.
