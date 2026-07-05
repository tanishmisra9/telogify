"""Env-driven settings. Loaded once as `settings`."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://localhost:5432/telogify_dev"

    @field_validator("database_url")
    @classmethod
    def _normalize_scheme(cls, v: str) -> str:
        # Railway/Heroku hand out postgres://; SQLAlchemy + psycopg2 needs postgresql://.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    resend_api_key: str = ""
    resend_from: str = "Telogify <onboarding@resend.dev>"

    fastf1_cache: str = ".fastf1_cache"

    web_base_url: str = "http://localhost:5173"

    # Fuel-load correction: seconds per lap shed as fuel burns off.
    # Industry heuristic used by most public F1 pace analyses (~0.065 s/lap for a
    # typical 70-kg load over 60 laps). Multiply by (total_laps - lap_number) to
    # estimate the extra time carried at that lap vs an empty tank.
    fuel_effect_s_per_lap: float = 0.065


settings = Settings()
