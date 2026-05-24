"""
Post-crawl vectorizer CLI for the local sqlite-vec sidecar.
"""

import argparse
import sys

from dotenv import load_dotenv

from . import __version__
from .config.loader import ConfigError, get_sites
from .vector_index import (
    VectorBackendUnavailableError,
    VectorIndexError,
    rebuild_vector_index,
    resolve_vector_index_file,
)

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="docmcp-vectorize",
        description=(
            "Build or refresh the local sqlite-vec sidecar from the crawled SQLite index.\n"
            f"Version: {__version__}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--site", type=str, help="Name of the site to vectorize (as in sites.yaml)")
    parser.add_argument(
        "--debug", action="store_true", help="Print detailed vectorizer diagnostics"
    )
    parser.add_argument("--list", action="store_true", help="List configured vectorizer targets")
    parser.add_argument("--version", action="store_true", help="Show the current version and exit")
    args = parser.parse_args()

    if args.version:
        if args.site or args.list:
            parser.error("--version cannot be combined with other arguments")
        print(f"{parser.prog} {__version__}")
        sys.exit(0)

    if not args.list and not args.site:
        parser.print_help()
        return

    try:
        sites = get_sites()
    except ConfigError as exc:
        print(f"[docmcp-vectorize] Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("\nConfigured vectorizer targets:")
        for site in sites:
            print(f"  - {site['name']} -> {resolve_vector_index_file(site)}")
        return

    site = next(
        (candidate for candidate in sites if candidate["name"].lower() == args.site.lower()), None
    )
    if not site:
        print(
            f"[vectorize] Site '{args.site}' not found. Use --list to see available sites.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[vectorize] Site         : {site['name']}")
    print(f"[vectorize] Crawl index  : {site['index_file']}")
    print(f"[vectorize] Vector index : {resolve_vector_index_file(site)}")

    try:
        summary = rebuild_vector_index(site, debug=args.debug)
    except VectorBackendUnavailableError as exc:
        print(f"[vectorize] sqlite-vec backend unavailable:\n{exc}", file=sys.stderr)
        sys.exit(1)
    except VectorIndexError as exc:
        print(f"[vectorize] Vectorization failed:\n{exc}", file=sys.stderr)
        sys.exit(1)

    print(
        "[vectorize] Done. "
        f"{summary.page_count} pages -> {summary.chunk_count} chunks -> {summary.vector_index_file}"
    )


if __name__ == "__main__":
    main()
