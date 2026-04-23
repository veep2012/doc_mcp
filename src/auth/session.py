"""
Session manager — handles Playwright authentication and session persistence.

Supports one auth mode:
  - headful: visible browser, user interacts fully (types email, password, OTP)
"""
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext


async def _wait_for_user(prompt: str) -> str:
    """Async-friendly CLI prompt for user input."""
    print(f"\n{prompt}", flush=True)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input)


async def _save_session(context: BrowserContext, session_file: str) -> None:
    """Save browser cookies and storage state to disk."""
    path = Path(session_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(path))
    print(f"[auth] Session saved to {path}", flush=True)


def load_session(session_file: str) -> dict | None:
    """Load saved session state from disk. Returns None if file doesn't exist."""
    path = Path(session_file)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


async def is_session_valid(url: str, session_file: str) -> bool:
    """
    Check if the saved session is still valid.
    First does a fast cookie expiry check, then verifies by navigating to the site.
    """
    session = load_session(session_file)
    if not session:
        return False

    # Fast check: any expired cookies?
    now = time.time()
    for cookie in session.get("cookies", []):
        if cookie.get("expires", -1) > 0 and cookie["expires"] < now:
            print(f"[auth] Cookie expired: {cookie['name']} (expired {int(now - cookie['expires'])}s ago)")
            return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=session_file)
        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=30000)
            current_url = page.url
            # If redirected to a login page, session is invalid
            login_indicators = ["login", "signin", "sign-in", "auth", "sso"]
            is_valid = not any(indicator in current_url.lower() for indicator in login_indicators)
            return is_valid
        except Exception as e:
            print(f"[auth] Session check failed: {e}")
            return False
        finally:
            await browser.close()


async def authenticate_headful(site: dict) -> None:
    """
    Mode: headful — open visible browser, user does everything manually.
    Wait for user to confirm login is complete, then save session.
    """
    url = site["url"]
    session_file = site["session_file"]

    print(f"\n[auth] Opening browser for: {url}")
    print("[auth] Please log in manually in the browser window.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)

        await _wait_for_user("Press Enter here once you have fully logged in...")

        await _save_session(context, session_file)
        await browser.close()


async def authenticate(site: dict, force: bool = False) -> None:
    """
    Main entry point for authentication.
    Checks if an existing session is valid before re-authenticating.
    """
    session_file = site.get("session_file")

    if not site.get("auth_required", True):
        print(f"[auth] No auth required for: {site['name']}")
        return

    # Check if existing session is still valid — use start_url (protected page) if available
    if not force and session_file:
        check_url = site.get("crawl", {}).get("start_url", site["url"])
        print(f"[auth] Checking existing session for: {site['name']}...")
        valid = await is_session_valid(check_url, session_file)
        if valid:
            print(f"[auth] Session is valid, skipping re-authentication.")
            return
        print("[auth] Session expired or invalid, re-authenticating...")

    await authenticate_headful(site)
