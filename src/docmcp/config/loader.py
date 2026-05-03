"""
Config loader — reads config/sites.yaml and resolves ${ENV_VAR} references from .env
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values


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


def _runtime_env(root: Path) -> dict[str, str]:
    """Return a private env mapping for the active runtime workspace."""
    merged_env = dict(os.environ)
    env_path = root / ".env"
    if env_path.exists():
        # Workspace .env values should take precedence for config resolution, but
        # they stay local to this mapping instead of mutating process state.
        for key, value in dotenv_values(env_path).items():
            if key and value is not None:
                merged_env[key] = value
    return merged_env


def _resolve_env_vars(value: Any, env: dict[str, str]) -> Any:
    """Recursively resolve ${VAR_NAME} placeholders from a provided env mapping."""
    if isinstance(value, str):

        def replacer(match):
            var_name = match.group(1)
            resolved = env.get(var_name)
            if resolved is None:
                # Return empty string for unset optional vars instead of crashing
                return ""
            return resolved

        return re.sub(r"\$\{([^}]+)\}", replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v, env) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(i, env) for i in value]
    return value


def load_config(config_path: str | None = None) -> dict:
    """Load and return the sites configuration with env vars resolved."""
    root = _runtime_root()
    runtime_env = _runtime_env(root)
    if config_path is None:
        config_path = os.environ.get("CONFIG_FILE", "config/sites.yaml")

    path = Path(config_path)
    if not path.is_absolute():
        path = root / path

    if not path.exists():
        raise ConfigError(_format_config_path_hint(path, root))

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration file is not valid YAML: {path}\n{exc}") from exc

    return _resolve_runtime_paths(_resolve_env_vars(raw, runtime_env), root)


def validate_config() -> dict:
    """Load config and raise a friendly error for common startup problems."""
    config = load_config()
    _validate_sites(config)
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
