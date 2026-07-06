"""Provider registry: drop-in LLM backends register via @register(name)."""

from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from telogify.config import Settings

ProviderFactory = Callable[[Settings], "LLMProvider"]

_REGISTRY: dict[str, ProviderFactory] = {}


@dataclass(frozen=True)
class LLMProvider:
    """One LLM backend: model construction + system-message formatting."""

    name: str
    build_model: Callable[[], BaseChatModel]
    build_system_message: Callable[[str], SystemMessage]


def register(name: str) -> Callable[[ProviderFactory], ProviderFactory]:
    """Decorator to register a provider factory under `name`."""

    def decorator(factory: ProviderFactory) -> ProviderFactory:
        _REGISTRY[name] = factory
        return factory

    return decorator


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def create_provider(name: str, settings: Settings) -> LLMProvider:
    factory = _REGISTRY.get(name)
    if factory is None:
        available = ", ".join(registered_names()) or "(none)"
        raise RuntimeError(
            f"Unknown LLM_PROVIDER {name!r}. Registered providers: {available}. "
            "Set LLM_PROVIDER in backend/.env."
        )
    return factory(settings)
