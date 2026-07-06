"""Single FastF1 disk cache location (FASTF1_CACHE in .env). Call before any FastF1 API use."""

import os

import fastf1

from telogify.config import settings

_cache_enabled = False


def enable_cache() -> None:
    """Point FastF1 at settings.fastf1_cache so schedule fetches and ingest share one directory."""
    global _cache_enabled
    if not _cache_enabled:
        os.makedirs(settings.fastf1_cache, exist_ok=True)
        fastf1.Cache.enable_cache(settings.fastf1_cache)
        _cache_enabled = True
