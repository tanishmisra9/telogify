"""Anthropic LLM provider (prompt caching on the system block)."""

from langchain_core.messages import SystemMessage

from telogify.agent.llm.registry import LLMProvider, register
from telogify.config import Settings


@register("anthropic")
def create(settings: Settings) -> LLMProvider:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The insight agent needs it; refusing to run "
            "rather than fabricate numbers."
        )

    def build_model():
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            max_tokens=4096,
        )

    def build_system_message(prompt: str) -> SystemMessage:
        # Cache the static prefix. Order in the request is tools -> system -> messages, so one
        # breakpoint on the system block caches tool schemas + system prompt together.
        return SystemMessage(
            content=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
        )

    return LLMProvider(
        name="anthropic", build_model=build_model, build_system_message=build_system_message
    )
