"""
Authentication CLI — run this script to authenticate to a documentation site
and save the session before starting the MCP server.

Usage:
    python auth_cli.py --site "Example Docs"
    python auth_cli.py --site "Example Docs" --force
    python auth_cli.py --list
"""
import argparse
import asyncio

from dotenv import load_dotenv

load_dotenv()

from src.config.loader import get_sites
from src.auth.session import authenticate


def main():
    parser = argparse.ArgumentParser(description="Authenticate to a documentation site.")
    parser.add_argument("--site", type=str, help="Name of the site to authenticate (as in sites.yaml)")
    parser.add_argument("--force", action="store_true", help="Force re-authentication even if session is valid")
    parser.add_argument("--list", action="store_true", help="List all configured sites")
    args = parser.parse_args()

    if args.list:
        sites = get_sites()
        print("\nConfigured sites:")
        for site in sites:
            auth = "auth required" if site.get("auth_required") else "public"
            print(f"  - {site['name']} ({auth}) [{site.get('auth_mode', 'n/a')}] — {site['url']}")
        return

    if not args.site:
        parser.print_help()
        return

    sites = get_sites()
    site = next((s for s in sites if s["name"].lower() == args.site.lower()), None)

    if not site:
        print(f"Site '{args.site}' not found in config. Use --list to see available sites.")
        return

    asyncio.run(authenticate(site, force=args.force))
    print(f"\n[auth] Done. You can now start the MCP server.")


if __name__ == "__main__":
    main()
