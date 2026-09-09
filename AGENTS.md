# AGENTS.md — Sudoku 42

Standing rules for anyone working in this repository, human or AI.

Keep this file short. Plans, designs, domain rules and decisions live in `docs/`.
This file holds only things that are true in every session.

## What this project is

A daily Sudoku web application for 42 School students. One puzzle per day per
difficulty (Easy / Medium / Hard), the same puzzle for everybody. Authentication
through the official 42 OAuth2 API. Application timezone: **Europe/Berlin**.

## Documentation index

| File | Contents | Read it when |
|---|---|---|
| `docs/ROADMAP.md` | Phases, MVP scope, current status | Starting any session |
| `docs/GAME_RULES.md` | Normative product behaviour | Touching puzzles, sessions or timing |
| `docs/DIFFICULTY.md` | How puzzles are graded and generated | Touching the Sudoku engine |
| `docs/ARCHITECTURE.md` | Stack, components, deployment | Making a structural change |
| `docs/DATA_MODEL.md` | Tables, columns, constraints | Touching the schema or a migration |
| `docs/API.md` | Endpoints, schemas, status codes | Touching an endpoint |
| `docs/SECURITY.md` | Threat model and required controls | Touching auth, input or game state |
| `docs/DECISIONS.md` | Decisions taken, and questions still open | Before assuming an answer |

`docs/GAME_RULES.md` and `docs/DIFFICULTY.md` are normative. If the code and one
of those files disagree, the file wins until it is explicitly changed — in its
own commit, with a reason.

## Session protocol

At the start of every session:

1. Run `git status` and `git log --oneline -10`.
2. Read `docs/ROADMAP.md` to find the current phase and what is already done.
3. Inspect the code before assuming anything about it. Never assume the
   repository is empty or that a feature is missing without looking.
4. Propose the next smallest useful step and get agreement before writing code.

## Working rules

- Work incrementally. One phase per branch, one logical change per commit.
- Implement the smallest change that satisfies the requirement.
- Do not touch unrelated code. Do not silently rewrite large sections.
- Tests are part of the change, not a follow-up.
- When a requirement is ambiguous and the answer materially affects architecture
  or behaviour, ask. Record the answer in `docs/DECISIONS.md`.
- Never invent external API behaviour, especially the 42 API. Consult the
  official documentation.
- If something cannot be verified — a doc behind a login, an unreachable
  service — say so plainly instead of asserting it.

## Dependencies

The agreed stack is listed in `docs/ARCHITECTURE.md` and needs no justification.
Anything beyond it does. Before adding a dependency, state: the problem it
solves, what the no-dependency alternative costs, and its maintenance and
security profile.

## Security floor

Full threat model in `docs/SECURITY.md`. Non-negotiable:

- No hard-coded secrets. Environment variables only. `.env.example` stays current.
- The complete solution never leaves the server. No exceptions, no "unnecessarily".
- The client is hostile. Assume every request is forged and every value tampered with.
- The backend is authoritative for game state, validation and timing.

## Before every commit

- Tests pass.
- Formatter and linter have run.
- A human has read the diff.
- No secrets, no `.env`, no tokens, no keys.

Never run `git push`, force-push, rewrite shared history, or open a pull request
unless explicitly asked to.

## Definition of Done

A feature is done when it is implemented; tests exist and pass; error cases are
handled; security implications were considered; documentation is updated if
behaviour changed; no unrelated code moved; **and the developer can explain how
it works.**

That last condition is not decoration. For the Sudoku engine and the OAuth flow
in particular: do not merge code you cannot explain.
