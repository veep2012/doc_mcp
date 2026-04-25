"""
Config loader — reads config/sites.yaml and resolves ${ENV_VAR} references from .env
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when runtime configuration is missing or invalid."""


def _runtime_root() -> Path:
    """Return the workspace/runtime root used for relative config and data paths."""
    configured_root = os.environ.get("DOC_MCP_HOME")
    if configured_root:
        return Path(configured_root).expanduser()
    return Path.cwd()


# Only rewrite file-backed runtime outputs here. Nested crawl fields are URLs,
# glob patterns, or scalar options in the current schema, not local paths.
_RUNTIME_PATH_KEYS = frozenset({"session_file", "index_file"})


def _resolve_runtime_path(value: Any, root: Path) -> Any:
    """Resolve a configured file path from the runtime root when it is relative."""
    if not isinstance(value, str) or not value:
        return value

    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(root / path)


def _resolve_runtime_paths(config: Any, root: Path) -> Any:
    """Resolve known runtime file paths inside the loaded site configuration."""
    if not isinstance(config, dict):
        return config

    sites = config.get("sites")
    if not isinstance(sites, list):
        return config

    for site in sites:
        if not isinstance(site, dict):
            continue
        for key in _RUNTIME_PATH_KEYS:
            if key in site:
                site[key] = _resolve_runtime_path(site[key], root)

    return config


def _format_config_path_hint(path: Path, root: Path) -> str:
    return (
        "Configuration file not found.\n"
        f"  Expected: {path}\n"
        f"  Runtime root: {root}\n\n"
        "Create the runtime workspace files, or point the process at them:\n"
        "  mkdir -p config storage index\n"
        "  cp /path/to/sites.yaml config/sites.yaml\n"
        "  export DOC_MCP_HOME=/path/to/workspace\n"
        "  export CONFIG_FILE=config/sites.yaml\n\n"
        "For VS Code MCP, set DOC_MCP_HOME and CONFIG_FILE in .vscode/mcp.json."
    )


def _validate_sites(config: Any) -> list[dict]:
    if not isinstance(config, dict):
        raise ConfigError(
            "Configuration file must contain a YAML mapping with a non-empty 'sites' list."
        )

    sites = config.get("sites")
    if not isinstance(sites, list) or not sites:
        raise ConfigError(
            "Configuration has no sites.\n"
            "Add at least one site entry under 'sites:' in config/sites.yaml."
        )

    return sites


def _validate_runtime_directories(sites: list[dict]) -> None:
    missing_dirs: set[Path] = set()
    for site in sites:
        if not isinstance(site, dict):
            continue
        for key in _RUNTIME_PATH_KEYS:
            value = site.get(key)
            if not isinstance(value, str) or not value:
                continue
            parent = Path(value).parent
            if not parent.exists():
                missing_dirs.add(parent)

    if missing_dirs:
        formatted = "\n".join(f"  - {path}" for path in sorted(missing_dirs))
        raise ConfigError(
            "Runtime directories are missing.\n"
            f"{formatted}\n\n"
            "Create them before starting the installed MCP server, for example:\n"
            "  mkdir -p config storage index"
        )


# Load .env from the runtime workspace, not from the installed package directory.
load_dotenv(_runtime_root() / ".env")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR_NAME} placeholders from environment variables."""
    if isinstance(value, str):

        def replacer(match):
            var_name = match.group(1)
            resolved = os.environ.get(var_name)
            if resolved is None:
                # Return empty string for unset optional vars instead of crashing
                return ""
            return resolved

        return re.sub(r"\$\{([^}]+)\}", replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(i) for i in value]
    return value


def load_config(config_path: str | None = None) -> dict:
    """Load and return the sites configuration with env vars resolved."""
    root = _runtime_root()
    if config_path is None:
        config_path = os.environ.get("CONFIG_FILE", "config/sites.yaml")

    path = Path(config_path)
    if not path.is_absolute():
        path = root / path

    if not path.exists():
        raise ConfigError(_format_config_path_hint(path, root))

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return _resolve_runtime_paths(_resolve_env_vars(raw), root)


def validate_config(require_runtime_dirs: bool = False) -> dict:
    """Load config and raise a friendly error for common startup problems."""
    config = load_config()
    sites = _validate_sites(config)
    if require_runtime_dirs:
        _validate_runtime_directories(sites)
    return config


def get_sites(config_path: str | None = None) -> list[dict]:
    """Return the list of site configurations."""
    config = load_config(config_path)
    return _validate_sites(config)


def get_site_by_name(name: str, config_path: str | None = None) -> dict | None:
    """Find a site config by its name."""
    for site in get_sites(config_path):
        if site.get("name") == name:
            return site
    return None
