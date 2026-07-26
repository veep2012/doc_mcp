import asyncio

import pytest

from docmcp.config.playwright import (
    BrowserUnavailableError,
    launch_browser,
    resolve_playwright_settings,
)


class _Page:
    url = "https://example.test/docs"

    async def goto(self, *args, **kwargs):
        return None


class _Context:
    async def new_page(self):
        return _Page()

    async def storage_state(self, **kwargs):
        return None


class _Browser:
    def __init__(self, calls):
        self.calls = calls

    async def new_context(self, **kwargs):
        self.calls["context"] = kwargs
        return _Context()

    async def close(self):
        return None


class _Engine:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    async def launch(self, **kwargs):
        self.calls["engine"] = self.name
        self.calls["launch"] = kwargs
        return _Browser(self.calls)


class _Playwright:
    def __init__(self, calls):
        self.chromium = _Engine("chromium", calls)
        self.firefox = _Engine("firefox", calls)
        self.webkit = _Engine("webkit", calls)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def test_authentication_and_session_validation_use_site_playwright_settings(monkeypatch):
    pytest.importorskip(
        "playwright.async_api",
        reason=(
            "Playwright is required for authentication settings tests. "
            "Install it with: python -m pip install playwright"
        ),
    )
    import docmcp.auth.session as session
    calls = {}
    site = {
        "name": "Docs",
        "url": "https://example.test/docs",
        "session_file": "session.json",
        "playwright": {
            "browser": "firefox",
            "launch": {"slow_mo": 10},
            "context": {"locale": "fr-FR", "viewport": {"width": 800, "height": 600}},
        },
    }
    monkeypatch.setattr(session, "async_playwright", lambda: _Playwright(calls))
    monkeypatch.setattr(session, "_wait_for_user", lambda prompt: asyncio.sleep(0))
    monkeypatch.setattr(session, "_save_session", lambda context, path: asyncio.sleep(0))

    asyncio.run(session.authenticate_headful(site))

    assert calls == {
        "engine": "firefox",
        "launch": {"headless": False, "slow_mo": 10},
        "context": {
            "locale": "fr-FR",
            "viewport": {"width": 800, "height": 600},
            "ignore_https_errors": False,
        },
    }

    calls.clear()
    monkeypatch.setattr(session, "load_session", lambda path: {"cookies": []})
    assert asyncio.run(session.is_session_valid(site["url"], "session.json", site=site)) is True
    assert calls["engine"] == "firefox"
    assert calls["launch"] == {"headless": True, "slow_mo": 10}
    assert calls["context"]["storage_state"] == "session.json"
    assert calls["context"]["ignore_https_errors"] is False


def test_launch_browser_reports_missing_browser_installation():
    class MissingEngine:
        async def launch(self, **kwargs):
            raise RuntimeError("Executable doesn't exist at /missing/browser")

    class Playwright:
        firefox = MissingEngine()

    settings = resolve_playwright_settings({"playwright": {"browser": "firefox"}})

    try:
        asyncio.run(launch_browser(Playwright(), settings, headless=False))
    except BrowserUnavailableError as exc:
        assert str(exc) == (
            "Playwright browser 'firefox' is not installed.\n"
            "Install it with:\n"
            "  python -m playwright install firefox"
        )
    else:
        raise AssertionError("Expected BrowserUnavailableError")
