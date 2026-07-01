from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.qwen_client import QwenCloudProvider
from app.core.config import Settings
from app.schemas.agent_outputs import SignalReport


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        raw = self.responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=raw))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        )


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


@pytest.mark.asyncio
async def test_qwen_provider_repair_prompt_includes_schema_and_json_mode() -> None:
    completions = _FakeCompletions(
        [
            "not-json",
            json.dumps(
                {
                    "agent_id": "MacroAnalystAgent",
                    "symbol": "ALPH",
                    "direction": "neutral",
                    "confidence": 0.51,
                    "evidence_ids": [],
                    "rationale": "No released catalyst.",
                    "uncertainty": "Waiting for evidence.",
                }
            ),
        ]
    )
    provider = QwenCloudProvider(Settings(dashscope_api_key="qwen-test-key"))
    provider.client = _FakeClient(completions)

    result = await provider.complete_json(
        agent_name="MacroAnalystAgent",
        system_prompt="Return strict JSON.",
        user_prompt="Use only visible context.",
        response_schema=SignalReport,
        temperature=0.2,
        max_tokens=900,
        metadata={},
    )

    assert result.content_json["direction"] == "neutral"
    assert result.repair_status == "repaired"
    assert "JSON schema" in completions.calls[1]["messages"][1]["content"]
    assert "direction" in completions.calls[1]["messages"][1]["content"]
    assert completions.calls[1]["response_format"] == {"type": "json_object"}
