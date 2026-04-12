"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings

_REQUIRED_VARS = ("devin_api_key", "devin_org_id", "github_token")


class Settings(BaseSettings):
    """Orchestrator configuration.

    All values are read from environment variables (or a .env file).
    """

    devin_api_key: str = ""
    devin_org_id: str = ""
    github_token: str = ""
    github_repo: str = "victorlga/superset"
    database_url: str = "sqlite+aiosqlite:///./data/orchestrator.db"
    devin_api_base: str = "https://api.devin.ai/v3"
    poll_interval_seconds: int = 30
    polling_enabled: bool = True
    max_rebuild_attempts: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _check_required_vars(self) -> Settings:
        missing = [name for name in _REQUIRED_VARS if not getattr(self, name)]
        if missing:
            env_names = ", ".join(name.upper() for name in missing)
            raise ValueError(
                f"Required environment variable(s) not set: {env_names}. "
                "Copy .env.example to .env and fill in your credentials "
                "(see README for details)."
            )
        return self


settings = Settings()
