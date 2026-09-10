import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-only-not-a-real-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://sudoku:sudoku@localhost:5432/sudoku_test"
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
