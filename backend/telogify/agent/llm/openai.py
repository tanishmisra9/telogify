"""OpenAI LLM provider (default)."""

from langchain_core.messages import SystemMessage

from telogify.agent.llm.registry import LLMProvider, register
from telogify.config import Settings


@register("openai")
def create(settings: Settings) -> LLMProvider:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The insight agent needs it; refusing to run "
            "rather than fabricate numbers."
        )

    def build_model():
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            # Reasoning models spend this budget on hidden reasoning tokens BEFORE any text:
            # 4096 produced fully-empty final messages on long sprint-weekend transcripts
            # (2026 R2, three parse failures in a row). 16384 leaves reasoning headroom while
            # still capping a runaway response; the JSON answer itself is only ~600 tokens.
            max_tokens=16384,
        )

    def build_system_message(prompt: str) -> SystemMessage:
        return SystemMessage(content=prompt)

    return LLMProvider(name="openai", build_model=build_model, build_system_message=build_system_message)
