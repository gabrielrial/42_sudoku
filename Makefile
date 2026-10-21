# Makefile
#
#   make           start (or restart) keeping the data, then migrate
#   make all       the same
#   make migrate   apply pending Alembic migrations
#   make test      the backend tests, against the sudoku_test database
#   make check     what CI checks: lint, format, types, tests, front-end build
#   make down      stop the containers, keeping the data
#   make re        from zero: deletes the database, rebuilds, starts, migrates
#   make fclean    stop and delete containers AND the database volume
#   make logs      follow the logs of every service
#
# The database lives in the Docker volume "postgres-data". Deleting that
# volume is what "from zero" means: every table and every row is gone. Only
# `make re` and `make fclean` do it, and only when asked for by name.
# The test database comes back on its own afterwards (db-init/).

COMPOSE := docker compose

.DEFAULT_GOAL := all
.PHONY: all up migrate test check down clean fclean re logs ps

all: up migrate

# --wait returns once the containers are running (and db is healthy), so the
# migration below never runs against a database that is still starting.
up:
	$(COMPOSE) up -d --build --wait

migrate:
	$(COMPOSE) exec api alembic upgrade head

# The api container's own DATABASE_URL, with the database swapped for
# sudoku_test: the tests drop and recreate the schema of whatever they use.
test:
	$(COMPOSE) exec -T api sh -c 'DATABASE_URL="$${DATABASE_URL%/*}/sudoku_test" pytest -rs'

check:
	$(COMPOSE) exec -T api ruff check .
	$(COMPOSE) exec -T api ruff format --check .
	$(COMPOSE) exec -T api mypy src
	$(MAKE) test
	$(COMPOSE) run --rm --no-deps web npm run build

down:
	$(COMPOSE) down

clean: down

# --volumes deletes the named volume postgres-data: the whole database.
fclean:
	$(COMPOSE) down --volumes --remove-orphans

re: fclean all

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps
