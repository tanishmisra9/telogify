"""Env-driven settings. Loaded once as `settings`."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The deployed frontend's own origins. Always allowed, so the live site cannot be cut off by a
#: missing or mistyped WEB_BASE_URL. Public hostnames, deliberately not configuration.
PRODUCTION_ORIGINS = ("https://www.telogify.com", "https://telogify.com")


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

    #: Extra browser origins allowed to call the API, comma separated. Only needed for an origin
    #: that is neither WEB_BASE_URL nor its apex/www sibling (a preview deployment, say).
    extra_cors_origins: str = ""

    #: Regex for origins allowed in addition to the list above, for hosts whose name is not
    #: fixed. Vercel mints a new URL per deployment, so a preview cannot be enumerated ahead of
    #: time; only the per-branch alias is stable. Set this to something scoped to the project,
    #: e.g. `https://telogify-[a-z0-9-]+\.vercel\.app`, never a bare `.*\.vercel\.app`, which
    #: would let any site hosted on Vercel call this API.
    #: Empty by default: previews are opt-in, and production should not be matching wildcards.
    cors_origin_regex: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """The frontend origin, its apex/www sibling, the Vite dev server, and any extras.

        The sibling matters: this replaced allow_origins=["*"], so an origin that is merely
        *nearly* right is now a hard failure for every request the site makes, not just signup.
        A reader landing on the apex when WEB_BASE_URL names www (or the reverse) would have seen
        the whole site fail to load. Cheap to accept both; expensive to get wrong.

        The production origins are listed unconditionally rather than derived, because deriving
        them from WEB_BASE_URL alone took the live site down: Railway had no WEB_BASE_URL set (it
        never needed one, since digests are sent from a developer machine whose .env does have
        it), so the allowlist collapsed to localhost and the deployed frontend was refused by
        every request it made. These are public hostnames, not configuration, and the site should
        not depend on an env var nobody knew was load-bearing.
        """
        primary = self.web_base_url.rstrip("/")
        origins = [primary, *PRODUCTION_ORIGINS, "http://localhost:5173"]
        if "://www." in primary:
            origins.append(primary.replace("://www.", "://", 1))
        elif "://" in primary:
            scheme, _, host = primary.partition("://")
            if host and not host.startswith("localhost"):
                origins.append(f"{scheme}://www.{host}")
        origins.extend(o.strip() for o in self.extra_cors_origins.split(",") if o.strip())
        return list(dict.fromkeys(origins))

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
