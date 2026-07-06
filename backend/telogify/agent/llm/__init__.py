"""Drop-in LLM providers. Add a module under this package with @register(name) to extend."""

import importlib
import pkgutil

from telogify.agent.llm.registry import LLMProvider, create_provider, registered_names
from telogify.config import settings


def _discover_providers() -> None:
    """Import every module in this package so @register decorators run."""
    package = importlib.import_module(__name__)
    for _importer, name, _ispkg in pkgutil.iter_modules(package.__path__):
        if name.startswith("_") or name == "registry":
            continue
        importlib.import_module(f"{__name__}.{name}")


_discover_providers()


def resolve_provider(provider_name: str | None = None) -> LLMProvider:
    """Return the configured LLM provider from settings (LLM_PROVIDER in .env)."""
    name = (provider_name or settings.llm_provider).strip().lower()
    return create_provider(name, settings)


__all__ = ["LLMProvider", "registered_names", "resolve_provider"]
