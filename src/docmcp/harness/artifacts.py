"""Safe diagnostic artifact handling."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REDACT = re.compile(r"(?i)((?:api[_-]?key|password|token|secret|credential)\s*[=:]\s*)[^,\s\"']+")


def redact(value: str) -> str:
    """Remove likely credential values from captured diagnostics."""
    return _REDACT.sub(r"\1[REDACTED]", value)


def create_run_dir(root: Path) -> Path:
    path = root / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(value), encoding="utf-8")
