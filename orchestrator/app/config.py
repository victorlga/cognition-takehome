"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
