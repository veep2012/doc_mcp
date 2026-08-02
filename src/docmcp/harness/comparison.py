"""Response normalization and structural comparison."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _remove_path(value: Any, path: str) -> None:
    current = value
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part)
    if isinstance(current, dict):
        current.pop(parts[-1], None)


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
