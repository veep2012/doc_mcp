"""Harness configuration and fixture validation."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from ..config.loader import ConfigError, load_config as load_site_config

_REQUIRED = (
    "HARNESS_BASELINE_WHEEL",
    "HARNESS_CURRENT_WHEEL",
    "HARNESS_FIXTURE_DIR",
    "HARNESS_ARTIFACT_DIR",
)
_SECRET_MARKERS = ("KEY", "PASSWORD", "TOKEN", "SECRET", "CREDENTIAL", "CERTIFICATE", "PRIVATE")


class HarnessError(RuntimeError):
    """Raised when a comparison cannot be started safely."""


@dataclass(frozen=True)
class HarnessConfig:
    baseline_wheel: Path
    current_wheel: Path
    fixture_dir: Path
    artifact_dir: Path
    container_bin: str
    image: str
    timeout_seconds: int
    allowlist: tuple[str, ...]
    verbose: bool = False


def _resolve(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def _validate_corpus(path: Path) -> list[dict]:
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"MCP request corpus is not valid JSON: {path}") from exc
    if (
        not isinstance(corpus, list)
        or not corpus
        or not all(isinstance(item, dict) for item in corpus)
    ):
        raise HarnessError("MCP request corpus must be a non-empty JSON array of request objects.")
    methods = {request.get("method") for request in corpus}
    if "initialize" not in methods:
        raise HarnessError("MCP request corpus must include an initialize request.")
    tools = [
        request.get("params", {}).get("name")
        for request in corpus
        if request.get("method") == "tools/call"
    ]
    if "get_version" not in tools or tools.count("search_docs") < 3:
        raise HarnessError(
            "MCP request corpus must include get_version and at least three search_docs requests."
        )
    if any(
        request.get("jsonrpc") != "2.0" or "id" not in request or not request.get("method")
        for request in corpus
    ):
        raise HarnessError("Each MCP request must contain jsonrpc='2.0', id, and method.")
    return corpus


def load_config(
    env_file: Path | str = ".env-harness", *, root: Path | None = None
) -> tuple[HarnessConfig, list[dict]]:
    """Load safe harness settings and return them with the immutable request corpus."""
    root = (root or Path.cwd()).resolve()
    env_path = _resolve(str(env_file), root)
    if not env_path.is_file():
        raise HarnessError(f"Harness configuration file not found: {env_path}")
    values = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
    forbidden = [key for key in values if any(marker in key.upper() for marker in _SECRET_MARKERS)]
    if forbidden:
        raise HarnessError(
            f".env-harness must not contain secret settings: {', '.join(sorted(forbidden))}"
        )
    missing = [key for key in _REQUIRED if not values.get(key)]
    if missing:
        raise HarnessError(f".env-harness is missing required settings: {', '.join(missing)}")

    baseline = _resolve(values["HARNESS_BASELINE_WHEEL"], root)
    current = _resolve(values["HARNESS_CURRENT_WHEEL"], root)
    for label, wheel in (("baseline", baseline), ("current", current)):
        if not wheel.is_file() or wheel.suffix != ".whl":
            raise HarnessError(f"{label.capitalize()} wheel must be an existing .whl file: {wheel}")
    fixture = _resolve(values["HARNESS_FIXTURE_DIR"], root)
    if not fixture.is_dir():
        raise HarnessError(f"Harness fixture directory does not exist: {fixture}")
    site_config = fixture / "config" / "sites.yaml"
    corpus = _validate_corpus(fixture / "mcp_requests.json")
    try:
        original_root, original_config = os.environ.get("DOC_MCP_HOME"), os.environ.get(
            "CONFIG_FILE"
        )
        os.environ["DOC_MCP_HOME"], os.environ["CONFIG_FILE"] = str(fixture), "config/sites.yaml"
        fixture_config = load_site_config()
    except ConfigError as exc:
        raise HarnessError(f"Harness fixture config is invalid: {site_config}: {exc}") from exc
    finally:
        if original_root is None:
            os.environ.pop("DOC_MCP_HOME", None)
        else:
            os.environ["DOC_MCP_HOME"] = original_root
        if original_config is None:
            os.environ.pop("CONFIG_FILE", None)
        else:
            os.environ["CONFIG_FILE"] = original_config
    missing_indexes = [
        site["index_file"]
        for site in fixture_config["sites"]
        if not Path(site["index_file"]).is_file()
    ]
    if missing_indexes:
        raise HarnessError(
            "Harness fixture is missing configured index files: " + ", ".join(missing_indexes)
        )

    runtime = os.environ.get("CONTAINER_BIN", values.get("CONTAINER_BIN", "podman"))
    if not shutil.which(runtime):
        raise HarnessError(
            f"Container runtime '{runtime}' is unavailable. Install Podman or Docker, or set CONTAINER_BIN=docker."
        )
    try:
        timeout = int(values.get("HARNESS_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise HarnessError("HARNESS_TIMEOUT_SECONDS must be a positive integer.") from exc
    if timeout <= 0:
        raise HarnessError("HARNESS_TIMEOUT_SECONDS must be a positive integer.")
    verbose_value = values.get("HARNESS_VERBOSE", "false").strip().lower()
    if verbose_value not in {"true", "false"}:
        raise HarnessError("HARNESS_VERBOSE must be true or false.")
    config = HarnessConfig(
        baseline_wheel=baseline,
        current_wheel=current,
        fixture_dir=fixture,
        artifact_dir=_resolve(values["HARNESS_ARTIFACT_DIR"], root),
        container_bin=runtime,
        image=values.get("HARNESS_IMAGE", "python:3.11-slim"),
        timeout_seconds=timeout,
        allowlist=tuple(
            filter(
                None,
                (
                    item.strip()
                    for item in values.get("HARNESS_ALLOWLIST", "serverInfo.version").split(",")
                ),
            )
        ),
        verbose=verbose_value == "true",
    )
    return config, corpus
