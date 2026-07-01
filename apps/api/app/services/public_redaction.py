from __future__ import annotations

import re
from typing import Any

from app.schemas.market import AgentActivityDetail, SimulationSnapshot
from app.schemas.recording import RecordingManifest, SimulationRecordingFrame

_PROVIDER_TEXT_PATTERNS = [
    re.compile(r"deterministic/mock", re.IGNORECASE),
    re.compile(r"\bqwen(?:-[\w.]+)?\b", re.IGNORECASE),
    re.compile(r"\bmock\b", re.IGNORECASE),
]

_TOP_LEVEL_SNAPSHOT_KEYS = {
    "active_provider",
    "configured_provider",
    "last_llm_provider",
    "last_completed_provider",
    "last_fallback_provider",
    "last_llm_model",
}

_REDACTED_DETAIL_KEYS = {
    "provider",
    "model",
    "primary_provider",
    "fallback_provider",
    "configured_provider",
    "effective_provider",
    "requested_provider",
    "active_provider",
    "last_llm_provider",
    "last_completed_provider",
    "last_fallback_provider",
    "last_llm_model",
    "provider_precedence",
    "active_provider_file",
    "qwen_provider_file",
    "model_reasoning",
    "model_fast",
    "model_coder",
}


def redact_provider_text(value: str) -> str:
    redacted = value
    for pattern in _PROVIDER_TEXT_PATTERNS:
        redacted = pattern.sub("AI runtime", redacted)
    return redacted


def _redact_recursive(value: Any, *, remove_keys: bool = True) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if remove_keys and key in _REDACTED_DETAIL_KEYS:
                continue
            cleaned[key] = _redact_recursive(item, remove_keys=remove_keys)
        return cleaned
    if isinstance(value, list):
        return [_redact_recursive(item, remove_keys=remove_keys) for item in value]
    if isinstance(value, str):
        return redact_provider_text(value)
    return value


def _redact_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = _redact_recursive(payload, remove_keys=False)
    if not isinstance(cleaned, dict):
        return payload

    for key in _TOP_LEVEL_SNAPSHOT_KEYS:
        cleaned.pop(key, None)

    for key in ("last_llm_error", "last_fallback_reason"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = redact_provider_text(cleaned[key])

    for agent in cleaned.get("agent_states", []) or []:
        if isinstance(agent, dict):
            agent["model"] = "AI runtime"
            if isinstance(agent.get("last_action"), str):
                agent["last_action"] = redact_provider_text(agent["last_action"])

    for item in cleaned.get("agent_activity_feed", []) or []:
        if not isinstance(item, dict):
            continue
        item.pop("provider", None)
        item.pop("model", None)
        for text_key in ("title", "message", "validation_summary"):
            if isinstance(item.get(text_key), str):
                item[text_key] = redact_provider_text(item[text_key])

    return cleaned


def redact_snapshot_dict(snapshot: SimulationSnapshot | dict[str, Any]) -> dict[str, Any]:
    payload = (
        snapshot.model_dump(mode="json")
        if isinstance(snapshot, SimulationSnapshot)
        else dict(snapshot)
    )
    return _redact_snapshot_payload(payload)


def redact_snapshot_model(snapshot: SimulationSnapshot) -> SimulationSnapshot:
    redacted = redact_snapshot_dict(snapshot)
    # Keep internal schema validity for recordings/restores while public serializers
    # omit the provider/model keys from JSON.
    redacted.update(
        {
            "active_provider": None,
            "configured_provider": None,
            "last_llm_provider": None,
            "last_completed_provider": None,
            "last_fallback_provider": None,
            "last_llm_model": None,
        }
    )
    for item in redacted.get("agent_activity_feed", []) or []:
        if isinstance(item, dict):
            item["provider"] = None
            item["model"] = None
    return SimulationSnapshot.model_validate(redacted)


def redact_activity_detail_dict(detail: AgentActivityDetail | dict[str, Any]) -> dict[str, Any]:
    payload = (
        detail.model_dump(mode="json")
        if isinstance(detail, AgentActivityDetail)
        else dict(detail)
    )
    cleaned = _redact_recursive(payload, remove_keys=True)
    return cleaned if isinstance(cleaned, dict) else payload


def redact_activity_detail_model(detail: AgentActivityDetail) -> AgentActivityDetail:
    return AgentActivityDetail.model_validate(redact_activity_detail_dict(detail))


def redact_manifest_dict(manifest: RecordingManifest | dict[str, Any]) -> dict[str, Any]:
    payload = (
        manifest.model_dump(mode="json")
        if isinstance(manifest, RecordingManifest)
        else dict(manifest)
    )
    payload.pop("provider", None)
    payload.pop("model_summary", None)
    if isinstance(payload.get("summary"), str):
        payload["summary"] = redact_provider_text(payload["summary"])
    return payload


def redact_frame_dict(frame: SimulationRecordingFrame | dict[str, Any]) -> dict[str, Any]:
    payload = (
        frame.model_dump(mode="json")
        if isinstance(frame, SimulationRecordingFrame)
        else dict(frame)
    )
    if "snapshot" in payload:
        payload["snapshot"] = redact_snapshot_dict(payload["snapshot"])
    return payload


def redact_recording_file_dict(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    if "manifest" in cleaned:
        cleaned["manifest"] = redact_manifest_dict(cleaned["manifest"])
    cleaned["frames"] = [redact_frame_dict(frame) for frame in cleaned.get("frames", [])]
    cleaned["activity_details"] = {
        key: redact_activity_detail_dict(value)
        for key, value in cleaned.get("activity_details", {}).items()
    }
    cleaned["skill_call_details"] = _redact_recursive(
        cleaned.get("skill_call_details", {}),
        remove_keys=True,
    )
    return cleaned
