"""LangGraph ReAct agent wiring (configurable LLM provider + bound DB tools)."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from telogify.agent.llm import resolve_provider
from telogify.agent.prompts import SYSTEM_PROMPT
from telogify.agent.tools import build_tools


def build_agent(year: int, round: int, session_factory=None):
    """Construct the ReAct insight agent for one weekend. Fails loud without an API key."""
    provider = resolve_provider()
    tools = build_tools(year, round, session_factory=session_factory)
    return create_react_agent(
        provider.build_model(),
        tools,
        prompt=provider.build_system_message(SYSTEM_PROMPT),
        checkpointer=MemorySaver(),
    )
