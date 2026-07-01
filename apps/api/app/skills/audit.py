from __future__ import annotations

import hashlib
import json
from typing import Any


def audit_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
