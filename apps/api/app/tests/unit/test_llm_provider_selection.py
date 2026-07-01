from __future__ import annotations

from app.agents.providers import MockLLMProvider
from app.agents.qwen_client import QwenCloudProvider
from app.core.config import Settings, resolve_llm_provider
from app.services import simulation_engine


def _settings(*, qwen_key: str = "") -> Settings:
    return Settings(
        dashscope_api_key=qwen_key,
        database_url="sqlite:///:memory:",
    )


def test_resolve_llm_provider_uses_mock_without_keys() -> None:
    assert resolve_llm_provider(_settings()) == "mock"


def test_resolve_llm_provider_uses_qwen_when_only_qwen_key_exists() -> None:
    assert resolve_llm_provider(_settings(qwen_key="qwen-test-key")) == "qwen"


def test_simulation_engine_builds_mock_without_keys(monkeypatch) -> None:
    monkeypatch.setattr(simulation_engine, "get_settings", lambda: _settings())
    engine = simulation_engine.SimulationEngine()

    assert engine.active_llm_provider == "mock"
    assert isinstance(engine.llm_provider, MockLLMProvider)


def test_simulation_engine_builds_qwen_when_dashscope_key_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        simulation_engine,
        "get_settings",
        lambda: _settings(qwen_key="qwen-test-key"),
    )
    engine = simulation_engine.SimulationEngine()

    assert engine.active_llm_provider == "qwen"
    assert isinstance(engine.llm_provider, QwenCloudProvider)
    assert engine.model_router.reasoning_model == "qwen3.7-plus"
