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

    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    resend_api_key: str = ""
    resend_from: str = "Telogify <onboarding@resend.dev>"

    fastf1_cache: str = ".fastf1_cache"

    web_base_url: str = "http://localhost:5173"

    # The deployed API's own public URL (Railway) -- distinct from web_base_url (the frontend,
    # Vercel). Real email sends need this because the dynamic chip images (chipgen.py: driver
    # name, event name, team-colored labels) are served BY this backend at /chip/text.png, and
    # Gmail has to fetch that URL from the public internet, not localhost.
    api_base_url: str = "http://localhost:8000"

    # HMAC key for unsubscribe tokens and IP hashing (subscriptions.py). Rotating it invalidates
    # every outstanding unsubscribe link, which is the intended emergency lever.
    subscriber_token_secret: str = ""

    # reCAPTCHA v3. Empty secret skips verification, which is only tolerable locally; see
    # require_signup_secrets() below.
    recaptcha_secret: str = ""

    # Set ENVIRONMENT=production on Railway. This started out derived from web_base_url, to save
    # a setting, which was wrong: web_base_url is https://www.telogify.com even in local dev,
    # because Gmail has to fetch the digest's hosted images from the public internet during a
    # real test send. Nothing else here distinguishes local from deployed, so it has to be said.
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        """The frontend origin, plus the Vite dev server so local work keeps functioning."""
        return list(dict.fromkeys([self.web_base_url.rstrip("/"), "http://localhost:5173"]))

    # Fuel-load correction: corrected = raw - fuel_time_cost_s_per_kg * burn_rate_kg_per_lap *
    # (total_laps - lap_number), computed per race in ingest/stints.py since burn rate depends on
    # that circuit's lap count. fuel_kg_per_race is the 2026 FIA race fuel allowance (down from
    # 110kg pre-2026, https://www.formula1.com/en/latest/article/more-efficient-less-fuel-and-carbon-net-zero-7-things-you-need-to-know-about.ZhtzvU3cPCv8QO7jtFxQR).
    # fuel_time_cost_s_per_kg is Mirco Bartolozzi's (fdataanalysis) stated per-kg cost, replacing
    # the earlier flat 0.065 s/lap heuristic (which implied ~0.056 s/kg, over double this value).
    fuel_kg_per_race: float = 70.0
    fuel_time_cost_s_per_kg: float = 0.025


settings = Settings()


def require_signup_secrets() -> None:
    """Fail loudly in production rather than serve a signup form with no bot defense.

    Called from the API's startup, not at import, so the CLI and tests (which never expose the
    form) are unaffected. A silently unprotected signup endpoint is worse than a failed boot.
    """
    if not settings.is_production:
        return
    missing = [
        name
        for name, value in (
            ("SUBSCRIBER_TOKEN_SECRET", settings.subscriber_token_secret),
            ("RECAPTCHA_SECRET", settings.recaptcha_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} must be set when ENVIRONMENT=production. "
            "Refusing to start with an unprotected signup endpoint."
        )


def configured_llm_label() -> str:
    """Provider and model from settings (LLM_PROVIDER + matching *_MODEL)."""
    provider = settings.llm_provider.strip().lower()
    model_by_provider = {
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
    }
    model = model_by_provider.get(provider, "?")
    return f"{provider} / {model}"
