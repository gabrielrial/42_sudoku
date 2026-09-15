"""Application configuration.

Every value comes from the environment. Nothing is hard-coded, and there are no
defaults for anything secret.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Environment = "development"
    secret_key: str

    database_url: str
    frontend_origin: str = "http://localhost:5173"

    # 42 OAuth — unset until Phase 4.
    fortytwo_client_id: str = ""
    fortytwo_client_secret: str = ""
    fortytwo_redirect_uri: str = ""

    # Dev-only fake identity provider, so local work and CI never call 42.
    auth_fake_provider_enabled: bool = False

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
