"""LangGraph ReAct agent wiring (Opus 4.7 + bound DB tools)."""

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
    return create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=MemorySaver())
