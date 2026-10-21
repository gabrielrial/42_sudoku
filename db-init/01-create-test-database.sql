-- Run by the postgres image the first time it starts on an empty volume
-- (docker-entrypoint-initdb.d), as POSTGRES_USER, who therefore owns it.
--
-- The database tests need a database of their own, and refuse any whose name
-- does not end in "_test": they drop and recreate its schema on every run
-- (backend/tests/conftest.py). Created here, it comes back on its own after
-- `make re` or `docker compose down -v` wipe the volume.
CREATE DATABASE sudoku_test;
