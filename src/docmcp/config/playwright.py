"""Validated per-site Playwright settings shared by browser runtime flows."""

from dataclasses import dataclass
from typing import Any


_BROWSERS = frozenset({"chromium", "firefox", "webkit"})
_LAUNCH_OPTIONS = frozenset(
    {"channel", "executable_path", "proxy", "timeout", "slow_mo", "args"}
)
_CONTEXT_OPTIONS = frozenset(
    {
        "viewport",
        "user_agent",
        "locale",
        "timezone_id",
        "color_scheme",
        "device_scale_factor",
        "is_mobile",
        "has_touch",
        "java_script_enabled",
        "accept_downloads",
        "extra_http_headers",
        "geolocation",
        "permissions",
    }
)


@dataclass(frozen=True)
class PlaywrightSettings:
    browser: str
    launch_options: dict[str, Any]
    context_options: dict[str, Any]


def resolve_playwright_settings(site: dict[str, Any]) -> PlaywrightSettings:
    """Return a site's validated Playwright settings with Chromium defaults."""
    config = site.get("playwright") or {}
    return PlaywrightSettings(
        browser=config.get("browser", "chromium"),
        launch_options=dict(config.get("launch", {})),
        context_options=dict(config.get("context", {})),
    )


def _invalid(field: str, site_name: object, detail: str) -> ValueError:
    return ValueError(f"Invalid playwright.{field} for site {site_name!r}: {detail}")


def _require_string(value: object, field: str, site_name: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(field, site_name, "expected a non-empty string.")


def _require_bool(value: object, field: str, site_name: object) -> None:
    if not isinstance(value, bool):
        raise _invalid(field, site_name, "expected a boolean value.")


def _require_number(value: object, field: str, site_name: object, minimum: float = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise _invalid(field, site_name, f"expected a number >= {minimum}.")


def validate_playwright_config(value: object, site_name: object) -> None:
    """Validate the safe, documented Playwright configuration allowlist."""
    if value is None:
        return
    if not isinstance(value, dict):
        raise _invalid("block", site_name, "expected a mapping.")
    unknown = set(value) - {"browser", "launch", "context"}
    if unknown:
        raise _invalid("block", site_name, f"unsupported keys: {', '.join(sorted(unknown))}.")
    browser = value.get("browser", "chromium")
    if not isinstance(browser, str) or browser not in _BROWSERS:
        raise _invalid("browser", site_name, f"expected one of: {', '.join(sorted(_BROWSERS))}.")

    launch = value.get("launch", {})
    if not isinstance(launch, dict):
        raise _invalid("launch", site_name, "expected a mapping.")
    unknown = set(launch) - _LAUNCH_OPTIONS
    if unknown:
        raise _invalid("launch", site_name, f"unsupported keys: {', '.join(sorted(unknown))}.")
    for key in {"channel", "executable_path"} & set(launch):
        _require_string(launch[key], f"launch.{key}", site_name)
    for key in {"timeout", "slow_mo"} & set(launch):
        _require_number(launch[key], f"launch.{key}", site_name)
    if "args" in launch:
        if not isinstance(launch["args"], list) or not all(isinstance(arg, str) for arg in launch["args"]):
            raise _invalid("launch.args", site_name, "expected a list of strings.")
    if "proxy" in launch:
        proxy = launch["proxy"]
        if not isinstance(proxy, dict) or set(proxy) - {"server", "bypass", "username", "password"}:
            raise _invalid("launch.proxy", site_name, "expected server, bypass, username, and password fields only.")
        _require_string(proxy.get("server"), "launch.proxy.server", site_name)
        for key in {"bypass", "username", "password"} & set(proxy):
            _require_string(proxy[key], f"launch.proxy.{key}", site_name)

    context = value.get("context", {})
    if not isinstance(context, dict):
        raise _invalid("context", site_name, "expected a mapping.")
    unknown = set(context) - _CONTEXT_OPTIONS
    if unknown:
        raise _invalid("context", site_name, f"unsupported keys: {', '.join(sorted(unknown))}.")
    for key in {"user_agent", "locale", "timezone_id"} & set(context):
        _require_string(context[key], f"context.{key}", site_name)
    for key in {"is_mobile", "has_touch", "java_script_enabled", "accept_downloads"} & set(context):
        _require_bool(context[key], f"context.{key}", site_name)
    if "color_scheme" in context and context["color_scheme"] not in {"light", "dark", "no-preference"}:
        raise _invalid("context.color_scheme", site_name, "expected light, dark, or no-preference.")
    if "device_scale_factor" in context:
        _require_number(context["device_scale_factor"], "context.device_scale_factor", site_name, 0.000001)
    if "viewport" in context:
        viewport = context["viewport"]
        if not isinstance(viewport, dict) or set(viewport) != {"width", "height"}:
            raise _invalid("context.viewport", site_name, "expected width and height fields.")
        for key in viewport:
            if type(viewport[key]) is not int or viewport[key] <= 0:
                raise _invalid(f"context.viewport.{key}", site_name, "expected an integer > 0.")
    if "extra_http_headers" in context:
        headers = context["extra_http_headers"]
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise _invalid("context.extra_http_headers", site_name, "expected a mapping of strings.")
    if "permissions" in context and (
        not isinstance(context["permissions"], list)
        or not all(isinstance(permission, str) for permission in context["permissions"])
    ):
        raise _invalid("context.permissions", site_name, "expected a list of strings.")
    if "geolocation" in context:
        geolocation = context["geolocation"]
        if not isinstance(geolocation, dict):
            raise _invalid("context.geolocation", site_name, "expected latitude, longitude, and optional accuracy fields.")
        geolocation_keys = set(geolocation)
        unsupported_keys = geolocation_keys - {"latitude", "longitude", "accuracy"}
        missing_required_keys = {"latitude", "longitude"} - geolocation_keys
        if unsupported_keys or missing_required_keys:
            raise _invalid(
                "context.geolocation",
                site_name,
                "expected latitude, longitude, and optional accuracy fields.",
            )
        _require_number(geolocation["latitude"], "context.geolocation.latitude", site_name, -90)
        if geolocation["latitude"] > 90:
            raise _invalid("context.geolocation.latitude", site_name, "expected a number between -90 and 90.")
        _require_number(geolocation["longitude"], "context.geolocation.longitude", site_name, -180)
        if geolocation["longitude"] > 180:
            raise _invalid("context.geolocation.longitude", site_name, "expected a number between -180 and 180.")
        if "accuracy" in geolocation:
            _require_number(geolocation["accuracy"], "context.geolocation.accuracy", site_name)
