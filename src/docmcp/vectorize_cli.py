"""
Post-crawl vectorizer CLI.

Usage:
    docmcp-vectorize --site "Example Docs"
    docmcp-vectorize --list
"""

import argparse
import sys

from dotenv import load_dotenv

from .config.loader import ConfigError, get_sites
from .vector_index import VectorIndexError, rebuild_vector_index, site_vector_index_file

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or refresh the local vector index from the crawled SQLite pages."
    )
    parser.add_argument("--site", type=str, help="Name of the site to vectorize (as in sites.yaml)")
    parser.add_argument("--list", action="store_true", help="List all configured sites")
    args = parser.parse_args()

    if not args.list and not args.site:
        parser.print_help()
        return

    try:
        sites = get_sites()
    except ConfigError as exc:
        print(f"[docmcp-vectorize] Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("\nConfigured sites:")
        for site in sites:
            print(
                "  - "
                f"{site['name']} — keyword index: {site['index_file']} — "
                f"vector index: {site_vector_index_file(site)}"
            )
        return

    site = next((candidate for candidate in sites if candidate["name"].lower() == args.site.lower()), None)
    if not site:
        print(f"[vectorize] Site '{args.site}' not found. Use --list to see available sites.")
        sys.exit(1)

    try:
        summary = rebuild_vector_index(site)
    except VectorIndexError as exc:
        print(f"[vectorize] Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        "[vectorize] Done. "
        f"{summary.page_count} pages -> {summary.chunk_count} chunks -> {summary.vector_index_file}"
    )


if __name__ == "__main__":
    main()
