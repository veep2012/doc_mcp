"""
Config loader — reads config/sites.yaml and resolves ${ENV_VAR} references from .env
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parents[2] / ".env")


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
    if config_path is None:
        config_path = os.environ.get("CONFIG_FILE", "config/sites.yaml")

    path = Path(config_path)
    if not path.is_absolute():
        path = Path(__file__).parents[2] / path

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return _resolve_env_vars(raw)


def get_sites(config_path: str | None = None) -> list[dict]:
    """Return the list of site configurations."""
    config = load_config(config_path)
    return config.get("sites", [])


def get_site_by_name(name: str, config_path: str | None = None) -> dict | None:
    """Find a site config by its name."""
    for site in get_sites(config_path):
        if site.get("name") == name:
            return site
    return None
