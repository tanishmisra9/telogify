import subprocess
import sys
from pathlib import Path

import pytest

from telogify.config import _ENV_FILE, Settings, require_production_send_urls, settings


def test_model_config_uses_the_absolute_env_file_not_a_cwd_relative_one():
    """Asserts the wiring, not just that the constant exists: a bare env_file=".env" is resolved
    against the process's working directory, so every setting silently falls back to its default
    whenever the process starts outside backend/."""
    configured = Settings.model_config["env_file"]
    assert Path(configured).is_absolute()
    assert Path(configured) == _ENV_FILE
    assert _ENV_FILE.parent == Path(__file__).resolve().parent.parent


def test_settings_load_the_same_from_an_unrelated_working_directory(tmp_path):
    """The real regression check: import settings in a subprocess started somewhere else
    entirely. Discriminates on resend_api_key because its default is the empty string -- a
    setting with a non-empty default (resend_from) is truthy either way and proves nothing.

    Why this matters beyond tidiness: an unloaded .env means an empty API key, which sends
    `Authorization: Bearer ` and makes Resend answer "API key is invalid" -- indistinguishable
    from a revoked key unless you already suspect the CWD.
    """
    if not _ENV_FILE.exists():
        return  # no local .env (CI/Railway supply real env vars); nothing to prove here
    code = "from telogify.config import settings; print(bool(settings.resend_api_key))"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "True", "settings did not load .env from an unrelated CWD"


def test_require_production_send_urls_is_a_noop_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "web_base_url", "http://localhost:5173")
    monkeypatch.setattr(settings, "api_base_url", "http://localhost:8000")
    require_production_send_urls()  # must not raise


def test_require_production_send_urls_raises_when_web_base_url_is_localhost(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "web_base_url", "http://localhost:5173")
    monkeypatch.setattr(settings, "api_base_url", "https://api.telogify.com")
    with pytest.raises(RuntimeError, match="WEB_BASE_URL"):
        require_production_send_urls()


def test_require_production_send_urls_raises_when_api_base_url_is_localhost(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "web_base_url", "https://www.telogify.com")
    monkeypatch.setattr(settings, "api_base_url", "http://127.0.0.1:8000")
    with pytest.raises(RuntimeError, match="API_BASE_URL"):
        require_production_send_urls()


def test_require_production_send_urls_passes_with_real_hostnames_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "web_base_url", "https://www.telogify.com")
    monkeypatch.setattr(settings, "api_base_url", "https://telogify-production.up.railway.app")
    require_production_send_urls()  # must not raise


def test_require_production_send_urls_raises_on_a_scheme_less_localhost_value(monkeypatch):
    # A bare "localhost:8000" (missing "http://") parses via plain urlparse() with hostname=None,
    # not "localhost" -- this pins that the guard still catches it.
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "web_base_url", "https://www.telogify.com")
    monkeypatch.setattr(settings, "api_base_url", "localhost:8000")
    with pytest.raises(RuntimeError, match="API_BASE_URL"):
        require_production_send_urls()
