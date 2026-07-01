from __future__ import annotations

import json
from typing import Any


class ContextPacker:
    def __init__(self, max_chars: int = 24_000) -> None:
        self.max_chars = max_chars

    def pack(self, payload: dict[str, Any]) -> str:
        text = json.dumps(payload, default=str, separators=(",", ":"))
        if len(text) <= self.max_chars:
            return text
        head = text[: self.max_chars - 160]
        return head + ',"_truncated":"context exceeded configured budget"}'
