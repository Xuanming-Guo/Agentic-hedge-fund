from __future__ import annotations

import json
import time
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.agents.providers import LLMResult
from app.agents.structured_output import normalize_payload, repair_prompt, validation_summary
from app.core.config import Settings
from app.core.exceptions import LLMProviderError

T = TypeVar("T", bound=BaseModel)


class QwenCloudProvider:
    provider_name = "qwen"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.dashscope_api_key:
            raise LLMProviderError("DASHSCOPE_API_KEY is required when Qwen is selected.")
        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key, base_url=settings.qwen_base_url
        )

    async def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float,
        max_tokens: int | None,
        metadata: dict,
    ) -> LLMResult:
        started = time.perf_counter()
        model = metadata.get("model") or self.settings.qwen_model_reasoning
        response_format = {"type": "json_object"} if self.settings.qwen_json_mode else None
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        completion = await self.client.chat.completions.create(**kwargs)
        raw = completion.choices[0].message.content or "{}"
        repair_status: str | None = None
        validation_note: str | None = None
        try:
            parsed = json.loads(raw)
            parsed, normalized, validation_note = normalize_payload(
                parsed,
                response_schema,
                agent_name=agent_name,
                metadata=metadata,
            )
            if normalized:
                repair_status = "normalized"
            validated = response_schema.model_validate(parsed)
        except (json.JSONDecodeError, PydanticValidationError) as exc:
            validation_note = validation_summary(exc)
            prompt = repair_prompt(
                response_schema=response_schema,
                validation_error=exc,
                raw_text=raw,
                user_prompt=user_prompt,
            )
            repair = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format=response_format,
            )
            raw = repair.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            parsed, normalized, normalize_note = normalize_payload(
                parsed,
                response_schema,
                agent_name=agent_name,
                metadata=metadata,
            )
            validated = response_schema.model_validate(parsed)
            completion = repair
            repair_status = "repaired"
            if normalized and normalize_note:
                validation_note = f"{validation_note}; {normalize_note}"
        usage = completion.usage
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResult(
            content_json=validated.model_dump(),
            raw_text=raw,
            provider=self.provider_name,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
            latency_ms=latency_ms,
            repair_status=repair_status,
            validation_summary=validation_note,
        )
