"""
Application settings loaded from the environment / .env file.

All settings are typed via pydantic-settings.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object — one instance shared application-wide."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    # ── Application ──────────────────────────
    APP_ENV: str
    APP_NAME: str = "ERP System"
    APP_VERSION: str
    APP_DEBUG: bool

    @property
    def DEBUG(self) -> bool:
        return self.APP_DEBUG

    # ── Database ─────────────────────────────
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # ── Security / JWT ────────────────────────
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────
    ALLOWED_ORIGINS: List[str]


    # ── Helpers ───────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


settings = Settings()
