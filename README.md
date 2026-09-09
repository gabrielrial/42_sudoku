# Sudoku 42

A daily Sudoku web application for 42 School students. One puzzle per day in
each of three difficulties — Easy, Medium and Hard — the same puzzle for
everyone, with authentication through the official 42 OAuth2 API.

Application timezone: Europe/Berlin.

**Status: design complete, no application code yet.** See `docs/ROADMAP.md`.

## Documentation

| File | Contents |
|---|---|
| `AGENTS.md` | Standing rules for working in this repository |
| `docs/ROADMAP.md` | Phases, MVP scope, current status |
| `docs/GAME_RULES.md` | Normative product behaviour |
| `docs/DIFFICULTY.md` | How puzzles are graded and generated |
| `docs/ARCHITECTURE.md` | Stack, components, deployment |
| `docs/DATA_MODEL.md` | Tables, columns, constraints |
| `docs/API.md` | Endpoints, schemas, status codes |
| `docs/SECURITY.md` | Threat model and required controls |
| `docs/DECISIONS.md` | Decisions taken, and questions still open |

`docs/GAME_RULES.md` and `docs/DIFFICULTY.md` are normative: if the code and one
of those files disagree, the file wins until it is explicitly changed.
