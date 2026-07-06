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
            max_tokens=4096,
        )

    def build_system_message(prompt: str) -> SystemMessage:
        return SystemMessage(content=prompt)

    return LLMProvider(name="openai", build_model=build_model, build_system_message=build_system_message)
