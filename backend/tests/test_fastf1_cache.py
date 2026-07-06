import fastf1

from telogify.ingest import fastf1_cache


def test_enable_cache_uses_settings_path(monkeypatch, tmp_path):
    monkeypatch.setattr(fastf1_cache, "_cache_enabled", False)
    monkeypatch.setattr(
        fastf1_cache.settings, "fastf1_cache", str(tmp_path / "my-fastf1-cache")
    )
    seen = []
    monkeypatch.setattr(
        fastf1.Cache,
        "enable_cache",
        lambda path: seen.append(path),
    )

    fastf1_cache.enable_cache()
    fastf1_cache.enable_cache()  # idempotent

    assert seen == [str(tmp_path / "my-fastf1-cache")]
