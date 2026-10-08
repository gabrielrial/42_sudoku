"""``app/config.py``: the settings refuse to start in an unsafe state.

Every test builds its own ``Settings`` with ``_env_file=None`` and explicit
values, so neither a local ``.env`` nor the container's environment (where
docker-compose sets ``AUTH_FAKE_PROVIDER_ENABLED=true``) changes the outcome.
"""

import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings

GOOD_KEY = secrets.token_hex(32)  # 64 hex characters = 32 random bytes


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "development",
        "secret_key": GOOD_KEY,
        "database_url": "postgresql+psycopg://user:pass@localhost:5432/whatever",
        "auth_fake_provider_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# --- every environment -------------------------------------------------------


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, database_url="postgresql+psycopg://u:p@localhost/x")


def test_development_accepts_a_short_key() -> None:
    assert _settings(app_env="development", secret_key="short").secret_key == "short"


# --- production ----------------------------------------------------------------


def test_production_accepts_a_long_random_key() -> None:
    assert _settings(app_env="production").secret_key == GOOD_KEY


@pytest.mark.parametrize("placeholder", ["", "change-me", "dev-only-not-a-real-secret"])
def test_production_refuses_a_placeholder_key(placeholder: str) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be set"):
        _settings(app_env="production", secret_key=placeholder)


def test_production_refuses_a_short_key() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _settings(app_env="production", secret_key="x" * 31)


def test_production_accepts_exactly_the_minimum_length() -> None:
    assert len(_settings(app_env="production", secret_key="x" * 32).secret_key) == 32


def test_production_refuses_the_fake_identity_provider() -> None:
    with pytest.raises(ValidationError, match="AUTH_FAKE_PROVIDER_ENABLED"):
        _settings(app_env="production", auth_fake_provider_enabled=True)
