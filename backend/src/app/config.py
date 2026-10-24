from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default (D19): a process that does not say where it runs refuses to
    # start, so a forgotten APP_ENV cannot leave a deployment in development
    # mode with the fake identity provider letting anyone in.
    app_env: Environment

    # Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str

    database_url: str
    frontend_origin: str = "http://localhost:5173"

    # 42 OAuth — unset until Phase 4.
    fortytwo_client_id: str = ""
    fortytwo_client_secret: str = ""
    fortytwo_redirect_uri: str = ""

    # Dev-only fake identity provider, so local work and CI never call 42.
    auth_fake_provider_enabled: bool = False

    access_token_minutes: int = 15
    refresh_token_days: int = 7

    login_attempts_per_minute: int = 5

    # Today and the days after it that always have their puzzles (DECISIONS.md Q11).
    puzzle_days_ahead: int = 7

    # When a game left from an earlier day closes (GAME_RULES.md §3, Q1).
    game_inactivity_minutes: int = 15
    game_rollover_grace_minutes: int = 120
    # A gap between two contacts longer than this is idleness, not play (API.md).
    game_active_gap_seconds: int = 90
    # Cell inputs per game session: a burst of this many, then one a second (D22).
    game_input_burst: int = 10
    # Per game session too (D5).
    game_heartbeats_per_minute: int = 2
    game_completions_per_minute: int = 5

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        if not self.is_production:
            return self
        if self.auth_fake_provider_enabled:
            raise ValueError("AUTH_FAKE_PROVIDER_ENABLED must be false when APP_ENV is production")
        if self.secret_key in {"", "change-me", "dev-only-not-a-real-secret"}:
            raise ValueError("SECRET_KEY must be set to a real value in production")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
