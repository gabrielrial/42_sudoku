# Sudoku 42

A daily Sudoku web application for 42 School students. One puzzle per day in
each of three difficulties — Easy, Medium and Hard — the same puzzle for
everyone, with authentication through the official 42 OAuth2 API.

Application timezone: Europe/Berlin.

**Status: Phase 4 (authentication) in progress.** The Sudoku engine generates
and grades puzzles; sessions work, and signing in with 42 is being built. The
front end shows one demo puzzle you can fill in, and nothing more yet. See
`docs/ROADMAP.md`.

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

The first time, and after every new migration, create the tables from another
terminal:

```bash
docker compose exec api alembic upgrade head
```

`Ctrl-C` stops everything. `docker compose down -v` also deletes the database.

The `Makefile` wraps this: plain `make` (or `make all`) starts and migrates,
keeping the data. `make re` starts from zero and **deletes the database**; so
does `make fclean`. Only those two, typed on purpose, ever delete it.

Source is bind-mounted, so edits reload without a rebuild. Changing a Dockerfile
or a dependency does need `docker compose up --build`.

### Checks

What CI checks, against the running containers:

```bash
make check     # lint, format, types, tests, front-end build
make test      # the tests alone
```

To let the formatter fix things instead of only checking:
`docker compose exec api ruff format .`

The database tests use their own database, `sudoku_test`, which PostgreSQL
creates the first time it starts on an empty volume (`db-init/`), so it comes
back after `make re`. Without it the database tests **fail**, never skip
(`DECISIONS.md` D20), with a message saying how to fix it. On a volume made
before `db-init/` existed, create it once:

```bash
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" sudoku_test'
```

`pytest tests/sudoku` runs the engine alone and needs no database. Only the two
published-puzzle checks in `test_verification.py` should skip.

After changing a model, `docker compose exec api alembic check` must print
"No new upgrade operations detected" once the new migration is applied. Read
every generated migration before applying it.

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
