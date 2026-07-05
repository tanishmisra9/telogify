"""LangGraph ReAct agent wiring (Sonnet 5 + bound DB tools)."""

from langchain_core.messages import SystemMessage

from telogify.agent.prompts import SYSTEM_PROMPT
from telogify.agent.tools import build_tools
from telogify.config import settings


def build_agent(year: int, round: int, session_factory=None):
    """Construct the ReAct insight agent for one weekend. Fails loud without an API key."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The insight agent needs it; refusing to run "
            "rather than fabricate numbers."
        )

    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent

    model = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        max_tokens=4096,
    )
    tools = build_tools(year, round, session_factory=session_factory)
    # Cache the static prefix. Order in the request is tools -> system -> messages, so one
    # breakpoint on the system block caches tool schemas + system prompt together. Both are
    # identical across every ReAct step, guardrail retry, and round (retry feedback lands on the
    # user message, not here), so the cache reads hit on every call after the first.
    prompt = SystemMessage(
        content=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    )
    return create_react_agent(model, tools, prompt=prompt, checkpointer=MemorySaver())
