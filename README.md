# Sudoku 42

A daily Sudoku web application for 42 School students. One puzzle per day in
each of three difficulties — Easy, Medium and Hard — the same puzzle for
everyone, with authentication through the official 42 OAuth2 API.

Application timezone: Europe/Berlin.

**Status: Phase 2 built, in review.** The Sudoku engine generates and grades
puzzles; the front end shows one demo puzzle you can fill in, and nothing more
yet. See `docs/ROADMAP.md`.

## Running it locally

Needs Docker Desktop. Nothing else — Python, Node and PostgreSQL all live in
containers.

```bash
cp .env.example .env
openssl rand -hex 32          # paste the result into SECRET_KEY in .env
docker compose up --build     # first run takes a few minutes
```

| URL | What it proves |
|---|---|
| http://localhost:8000/api/health | the backend is up |
| http://localhost:8000/api/health/db | it reached PostgreSQL |
| http://localhost:5173 | the demo board: one puzzle to fill in |
| http://localhost:8000/api/docs | interactive API documentation |

`Ctrl-C` stops everything. `docker compose down -v` also deletes the database.

Source is bind-mounted, so edits reload without a rebuild. Changing a Dockerfile
or a dependency does need `docker compose up --build`.

### Checks

The same four the CI runs, against the running container:

```bash
docker compose exec api ruff check .
docker compose exec api ruff format .     # --check in CI; this one fixes
docker compose exec api mypy src
docker compose exec api pytest
```

Install the hooks once and formatting stops being something you think about:

```bash
pip install pre-commit && pre-commit install
```


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
| `docs/LESSONS.md` | Problems hit so far, and what fixed them |

`docs/GAME_RULES.md` and `docs/DIFFICULTY.md` are normative: if the code and one
of those files disagree, the file wins until it is explicitly changed.
