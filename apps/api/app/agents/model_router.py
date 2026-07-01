from __future__ import annotations

from app.core.config import Settings


class LLMModelRouter:
    def __init__(self, settings: Settings, provider_name: str) -> None:
        self.settings = settings
        self.provider_name = provider_name

    @property
    def reasoning_model(self) -> str:
        if self.provider_name == "mock":
            return "mock-deterministic"
        return self.settings.qwen_model_reasoning

    @property
    def fast_model(self) -> str:
        if self.provider_name == "mock":
            return "mock-deterministic"
        return self.settings.qwen_model_fast

    @property
    def coder_model(self) -> str:
        if self.provider_name == "mock":
            return "mock-deterministic"
        return self.settings.qwen_model_coder

    def route(self, agent_name: str) -> tuple[str, float]:
        if agent_name in {"CoordinatorAgent", "DemoNarratorAgent"}:
            return self.fast_model, self.settings.qwen_temperature_execution
        if agent_name in {"ExecutionTraderAgent"}:
            return self.fast_model, self.settings.qwen_temperature_execution
        if "Bull" in agent_name or "Bear" in agent_name:
            return self.reasoning_model, self.settings.qwen_temperature_debate
        if "Risk" in agent_name or "Compliance" in agent_name:
            return self.reasoning_model, self.settings.qwen_temperature_execution
        return self.reasoning_model, self.settings.qwen_temperature_analyst


class QwenModelRouter(LLMModelRouter):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, "qwen")
