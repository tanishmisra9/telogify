"""Env-driven settings. Loaded once as `settings`."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://localhost:5432/telogify_dev"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-7"

    resend_api_key: str = ""
    resend_from: str = "Telogify <onboarding@resend.dev>"

    fastf1_cache: str = ".fastf1_cache"

    web_base_url: str = "http://localhost:5173"


settings = Settings()
