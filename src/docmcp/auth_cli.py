"""
Authentication CLI — run this script to authenticate to a documentation site
and save the session before starting the MCP server.

Usage:
    docmcp-auth --site "Example Docs"
    docmcp-auth --site "Example Docs" --force
    docmcp-auth --list
"""

import argparse
import asyncio
import sys

from dotenv import load_dotenv

from .auth.session import authenticate
from .config.loader import ConfigError, get_sites

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Authenticate to a documentation site.")
    parser.add_argument(
        "--site", type=str, help="Name of the site to authenticate (as in sites.yaml)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-authentication even if session is valid"
    )
    parser.add_argument("--list", action="store_true", help="List all configured sites")
    args = parser.parse_args()

    if not args.list and not args.site:
        parser.print_help()
        return

    try:
        sites = get_sites()
    except ConfigError as exc:
        print(f"[docmcp-auth] Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("\nConfigured sites:")
        for site in sites:
            auth = "auth required" if site.get("auth_required") else "public"
            print(f"  - {site['name']} ({auth}) [{site.get('auth_mode', 'n/a')}] — {site['url']}")
        return

    site = next((s for s in sites if s["name"].lower() == args.site.lower()), None)

    if not site:
        print(f"Site '{args.site}' not found in config. Use --list to see available sites.")
        return

    asyncio.run(authenticate(site, force=args.force))
    print("\n[auth] Done. You can now start the MCP server.")


if __name__ == "__main__":
    main()
