"""Safe diagnostic artifact handling."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REDACT_QUOTED = re.compile(
    r"(?i)((?:api[_-]?key|password|token|secret|credential)\s*[=:]\s*)\"[^\"]*\"|"
    r"((?:api[_-]?key|password|token|secret|credential)\s*[=:]\s*)'[^']*'"
)
_REDACT_UNQUOTED = re.compile(
    r"(?i)((?:api[_-]?key|password|token|secret|credential)\s*[=:]\s*)[^,\s\"}']+"
)
_SECRET_KEY = re.compile(r"(?i)(?:api[_-]?key|password|token|secret|credential)")


def redact(value: str) -> str:
    """Remove likely credential values from captured diagnostics."""
    value = _REDACT_QUOTED.sub(
        lambda match: f'{match.group(1) or match.group(2)}"[REDACTED]"', value
    )
    return _REDACT_UNQUOTED.sub(r"\1[REDACTED]", value)


def _redact_value(value: Any) -> Any:
    """Recursively redact credential-like values before writing JSON artifacts."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            redacted[key] = "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return redact(value)
        if isinstance(decoded, (dict, list)):
            return json.dumps(_redact_value(decoded), ensure_ascii=False, indent=2)
        return redact(value)
    return value


def create_run_dir(root: Path) -> Path:
    path = root / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_redact_value(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(value), encoding="utf-8")
