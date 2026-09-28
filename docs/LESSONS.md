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
