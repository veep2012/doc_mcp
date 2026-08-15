"""Response normalization and structural comparison."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def _remove_path(value: Any, path: str) -> None:
    """Remove a dot-separated path, including keys in JSON-encoded response text."""

    def remove(current: Any, parts: list[str]) -> tuple[Any, bool]:
        if not parts:
            return current, False
        if isinstance(current, dict):
            part = parts[0]
            if len(parts) == 1:
                if part not in current:
                    return current, False
                current.pop(part)
                return current, True
            if part not in current:
                return current, False
            child, removed = remove(current[part], parts[1:])
            if removed:
                current[part] = child
            return current, removed
        if isinstance(current, list):
            try:
                index = int(parts[0])
            except ValueError:
                return current, False
            if index < 0 or index >= len(current):
                return current, False
            child, removed = remove(current[index], parts[1:])
            if removed:
                current[index] = child
            return current, removed
        if isinstance(current, str):
            try:
                decoded = json.loads(current)
            except json.JSONDecodeError:
                return current, False
            decoded, removed = remove(decoded, parts)
            if not removed:
                return current, False
            return (
                json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                True,
            )
        return current, False

    remove(value, path.split("."))


def normalize_response(response: dict[str, Any], allowlist: tuple[str, ...]) -> dict[str, Any]:
    """Return a response with only explicitly documented non-semantic fields removed."""
    normalized = deepcopy(response)
    for path in allowlist:
        _remove_path(normalized, path)
    return normalized


def compare_responses(
    baseline: list[dict[str, Any]], current: list[dict[str, Any]], allowlist: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Return all normalized request-response differences."""
    differences = []
    for index in range(max(len(baseline), len(current))):
        left = normalize_response(baseline[index], allowlist) if index < len(baseline) else None
        right = normalize_response(current[index], allowlist) if index < len(current) else None
        if left != right:
            differences.append({"request_index": index, "baseline": left, "current": right})
    return differences
