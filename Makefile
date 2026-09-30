# Makefile
#
#   make           from zero: deletes the database, rebuilds, starts, migrates
#   make all       start (or restart) keeping the data, then migrate
#   make migrate   apply pending Alembic migrations
#   make down      stop the containers, keeping the data
#   make fclean    stop and delete containers AND the database volume
#   make logs      follow the logs of every service
#
# The database lives in the Docker volume "postgres-data". Deleting that
# volume is what "from zero" means: every table and every row is gone.

COMPOSE := docker compose

.DEFAULT_GOAL := re
.PHONY: all up migrate down clean fclean re logs ps

all: up migrate

# --wait returns once the containers are running (and db is healthy), so the
# migration below never runs against a database that is still starting.
up:
	$(COMPOSE) up -d --build --wait

migrate:
	$(COMPOSE) exec api alembic upgrade head

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
