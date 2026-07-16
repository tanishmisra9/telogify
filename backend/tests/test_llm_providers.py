import pytest
from langchain_core.messages import SystemMessage

from telogify.agent.llm import registered_names, resolve_provider
from telogify.agent.llm.registry import create_provider
from telogify.config import Settings


def test_registered_providers():
    assert registered_names() == ["anthropic", "openai"]


def test_resolve_provider_defaults_to_openai(monkeypatch):
    monkeypatch.setattr(
        "telogify.agent.llm.settings",
        Settings(llm_provider="openai", openai_api_key="sk-test"),
    )
    provider = resolve_provider()
    assert provider.name == "openai"


def test_resolve_provider_anthropic(monkeypatch):
    monkeypatch.setattr(
        "telogify.agent.llm.settings",
        Settings(llm_provider="anthropic", anthropic_api_key="sk-ant-test"),
    )
    provider = resolve_provider()
    assert provider.name == "anthropic"


def test_unknown_provider_fails_loud():
    with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
        create_provider("gemini", Settings())


def test_openai_provider_fails_loud_without_key():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        create_provider("openai", Settings(openai_api_key=""))


def test_anthropic_provider_fails_loud_without_key():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_provider("anthropic", Settings(anthropic_api_key=""))


def test_openai_system_message_is_plain_text():
    provider = create_provider("openai", Settings(openai_api_key="sk-test"))
    msg = provider.build_system_message("hello")
    assert isinstance(msg, SystemMessage)
    assert msg.content == "hello"


def test_anthropic_system_message_has_cache_control():
    provider = create_provider("anthropic", Settings(anthropic_api_key="sk-ant-test"))
    msg = provider.build_system_message("hello")
    assert isinstance(msg.content, list)
    assert msg.content[0]["cache_control"] == {"type": "ephemeral"}


def test_openai_build_model_passes_settings(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        __import__("sys").modules,
        "langchain_openai",
        type("m", (), {"ChatOpenAI": FakeChatOpenAI})(),
    )
    provider = create_provider(
        "openai",
        Settings(openai_api_key="sk-test", openai_model="gpt-4.1"),
    )
    provider.build_model()
    assert captured["model"] == "gpt-4.1"
    assert captured["api_key"] == "sk-test"
    # Reasoning models spend max_tokens on hidden reasoning before any text; 4096 produced
    # empty final messages on sprint weekends (see agent/llm/openai.py).
    assert captured["max_tokens"] == 16384
    assert "temperature" not in captured


def test_configured_llm_label_openai(monkeypatch):
    from telogify.config import Settings, configured_llm_label

    monkeypatch.setattr(
        "telogify.config.settings",
        Settings(llm_provider="openai", openai_model="gpt-5.2"),
    )
    assert configured_llm_label() == "openai / gpt-5.2"


def test_configured_llm_label_anthropic(monkeypatch):
    from telogify.config import Settings, configured_llm_label

    monkeypatch.setattr(
        "telogify.config.settings",
        Settings(llm_provider="anthropic", anthropic_model="claude-sonnet-5"),
    )
    assert configured_llm_label() == "anthropic / claude-sonnet-5"

    captured = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        __import__("sys").modules,
        "langchain_anthropic",
        type("m", (), {"ChatAnthropic": FakeChatAnthropic})(),
    )
    provider = create_provider(
        "anthropic",
        Settings(anthropic_api_key="sk-ant-test", anthropic_model="claude-sonnet-5"),
    )
    provider.build_model()
    assert captured["model"] == "claude-sonnet-5"
    assert captured["api_key"] == "sk-ant-test"
    assert captured["max_tokens"] == 4096
