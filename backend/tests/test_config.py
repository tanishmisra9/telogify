import subprocess
import sys
from pathlib import Path

from telogify.config import _ENV_FILE, Settings


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
