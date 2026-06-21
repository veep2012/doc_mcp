"""
Config loader — reads config/sites.yaml and resolves ${ENV_VAR} references from .env
"""

import os
import re
import math
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from ..vector_index import _normalize_chunk_settings


class ConfigError(RuntimeError):
    """Raised when runtime configuration is missing or invalid."""


_ALLOWED_SEARCH_ENGINES = frozenset({"hybrid", "keyword", "vector"})


def _runtime_root() -> Path:
    """Return the workspace/runtime root used for relative config and data paths."""
    configured_root = os.environ.get("DOC_MCP_HOME")
    if configured_root:
        return Path(configured_root).expanduser()
    return Path.cwd()


# Only rewrite file-backed runtime outputs here. Nested crawl fields are URLs,
# glob patterns, or scalar options in the current schema, not local paths.
_RUNTIME_PATH_KEYS = frozenset({"session_file", "index_file", "vector_index_file"})
_REDIRECT_POLICIES = frozenset({"final", "requested", "skip"})


def _resolve_runtime_path(value: Any, root: Path) -> Any:
    """Resolve a configured file path from the runtime root when it is relative."""
    if not isinstance(value, str) or not value:
        return value

    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(root / path)


def _normalize_search_engine(value: Any, site_name: str | None = None) -> str:
    """Return the canonical site search engine or raise a configuration error."""
    if value is None or value == "":
        return "hybrid"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _ALLOWED_SEARCH_ENGINES:
            return normalized
    allowed = ", ".join(sorted(_ALLOWED_SEARCH_ENGINES))
    site_label = f" for site '{site_name}'" if site_name else ""
    raise ConfigError(
        f"Invalid search_engine{site_label}: {value!r}. " f"Expected one of: {allowed}."
    )


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
        site["search_engine"] = _normalize_search_engine(
            site.get("search_engine"), site.get("name")
        )
        for key in _RUNTIME_PATH_KEYS:
            if key in site:
                site[key] = _resolve_runtime_path(site[key], root)

    return config


def _invalid_redirect_policy_message(received_value: object, site_name: str | None = None) -> str:
    allowed_values = ", ".join(sorted(_REDIRECT_POLICIES))
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    return (
        f"Invalid crawl.redirect_policy{site_context}: received "
        f"{received_value!r}; expected one of {allowed_values}"
    )


def _validate_bool(value: object, field_name: str, site_name: str | None = None) -> bool:
    if isinstance(value, bool):
        return value
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    raise ConfigError(
        f"Invalid {field_name}{site_context}: received {value!r}; expected a boolean value."
    )


def _validate_list_of_strings(
    value: object, field_name: str, site_name: str | None = None
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        site_context = f" for site {site_name!r}" if site_name is not None else ""
        raise ConfigError(
            f"Invalid {field_name}{site_context}: received {value!r}; expected a list of strings."
        )
    return value


def _validate_non_empty_string(value: object, field_name: str, site_name: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    raise ConfigError(
        f"Invalid {field_name}{site_context}: received {value!r}; expected a non-empty string."
    )


def _validate_non_negative_int(value: object, field_name: str, site_name: str | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        site_context = f" for site {site_name!r}" if site_name is not None else ""
        raise ConfigError(
            f"Invalid {field_name}{site_context}: received {value!r}; expected an integer >= 0."
        )
    if value < 0:
        site_context = f" for site {site_name!r}" if site_name is not None else ""
        raise ConfigError(
            f"Invalid {field_name}{site_context}: received {value!r}; expected an integer >= 0."
        )
    return value


def _validate_site_config(site: dict) -> dict:
    site_name = site.get("name")
    _validate_non_empty_string(site_name, "site.name")
    _validate_non_empty_string(site.get("url"), "site.url", site_name)
    _validate_bool(site.get("auth_required"), "site.auth_required", site_name)
    if "session_file" in site and site["session_file"] is not None:
        _validate_non_empty_string(site["session_file"], "session_file", site_name)
    _normalize_search_engine(site.get("search_engine"), site_name)

    crawl_cfg = site.get("crawl", {})
    if not isinstance(crawl_cfg, dict):
        raise ConfigError(f"Invalid crawl block for site {site_name!r}: expected a mapping.")
    if "start_url" in crawl_cfg:
        _validate_non_empty_string(crawl_cfg.get("start_url"), "crawl.start_url", site_name)
    if "max_depth" in crawl_cfg:
        _validate_non_negative_int(crawl_cfg.get("max_depth"), "crawl.max_depth", site_name)
    if "block_images" in crawl_cfg:
        _validate_bool(crawl_cfg.get("block_images"), "crawl.block_images", site_name)
    if "ignore_query_links" in crawl_cfg:
        _validate_bool(crawl_cfg.get("ignore_query_links"), "crawl.ignore_query_links", site_name)
    if "ignore_anchor_links" in crawl_cfg:
        _validate_bool(crawl_cfg.get("ignore_anchor_links"), "crawl.ignore_anchor_links", site_name)
    if "ignore_https_errors" in crawl_cfg:
        _validate_bool(crawl_cfg.get("ignore_https_errors"), "crawl.ignore_https_errors", site_name)
    if "delay_seconds" in crawl_cfg:
        delay_seconds = crawl_cfg.get("delay_seconds")
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)):
            raise ConfigError(
                f"Invalid crawl.delay_seconds for site {site_name!r}: received {delay_seconds!r}; "
                "expected a finite number >= 0."
            )
        if not math.isfinite(float(delay_seconds)) or float(delay_seconds) < 0:
            raise ConfigError(
                f"Invalid crawl.delay_seconds for site {site_name!r}: received {delay_seconds!r}; "
                "expected a finite number >= 0."
            )
    if "start_delay_seconds" in crawl_cfg:
        start_delay_seconds = crawl_cfg.get("start_delay_seconds")
        if isinstance(start_delay_seconds, bool) or not isinstance(
            start_delay_seconds, (int, float)
        ):
            raise ConfigError(
                f"Invalid crawl.start_delay_seconds for site {site_name!r}: received {start_delay_seconds!r}; "
                "expected a finite number >= 0."
            )
        if not math.isfinite(float(start_delay_seconds)) or float(start_delay_seconds) < 0:
            raise ConfigError(
                f"Invalid crawl.start_delay_seconds for site {site_name!r}: received {start_delay_seconds!r}; "
                "expected a finite number >= 0."
            )
    if "redirect_policy" in crawl_cfg:
        policy = crawl_cfg.get("redirect_policy")
        if not isinstance(policy, str) or policy.strip().lower() not in _REDIRECT_POLICIES:
            raise ConfigError(_invalid_redirect_policy_message(policy, site_name))
    if "allow_patterns" in crawl_cfg:
        _validate_list_of_strings(
            crawl_cfg.get("allow_patterns"), "crawl.allow_patterns", site_name
        )
    if "deny_patterns" in crawl_cfg:
        _validate_list_of_strings(crawl_cfg.get("deny_patterns"), "crawl.deny_patterns", site_name)

    vectorizer_cfg = site.get("vectorizer", {})
    if not isinstance(vectorizer_cfg, dict):
        raise ConfigError(f"Invalid vectorizer block for site {site_name!r}: expected a mapping.")
    if "chunk_size" in vectorizer_cfg:
        _validate_non_negative_int(
            vectorizer_cfg.get("chunk_size"), "vectorizer.chunk_size", site_name
        )
    if "chunk_overlap" in vectorizer_cfg:
        _validate_non_negative_int(
            vectorizer_cfg.get("chunk_overlap"), "vectorizer.chunk_overlap", site_name
        )
    if "embedding_model" in vectorizer_cfg and vectorizer_cfg.get("embedding_model") is not None:
        _validate_non_empty_string(
            vectorizer_cfg.get("embedding_model"), "vectorizer.embedding_model", site_name
        )
    if (
        "chunk_size" in vectorizer_cfg
        or "chunk_overlap" in vectorizer_cfg
        or "embedding_model" in vectorizer_cfg
    ):
        chunk_size = vectorizer_cfg.get("chunk_size")
        chunk_overlap = vectorizer_cfg.get("chunk_overlap")
        embedding_model = vectorizer_cfg.get("embedding_model")
        try:
            _normalize_chunk_settings(chunk_size, chunk_overlap, embedding_model)
        except ValueError as exc:
            raise ConfigError(f"Invalid vectorizer settings for site {site_name!r}: {exc}") from exc

    return site


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

    validated_sites: list[dict] = []
    for site in sites:
        if not isinstance(site, dict):
            raise ConfigError(f"Invalid site entry: expected a mapping, received {site!r}.")
        validated_sites.append(_validate_site_config(site))

    config["sites"] = validated_sites
    return validated_sites


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

    config = _resolve_runtime_paths(_resolve_env_vars(raw, runtime_env), root)
    _validate_sites(config)
    return config


def validate_config() -> dict:
    """Load config and raise a friendly error for common startup problems."""
    return load_config()


def get_sites(config_path: str | None = None) -> list[dict]:
    """Return the list of site configurations."""
    config = load_config(config_path)
    return config["sites"]


def get_site_by_name(name: str, config_path: str | None = None) -> dict | None:
    """Find a site config by its name."""
    for site in get_sites(config_path):
        if site.get("name") == name:
            return site
    return None
