"""Create the local packaged-harness SQLite fixture index."""

from __future__ import annotations

import argparse
from pathlib import Path

from docmcp.index_store import init_db, upsert_page

_PAGE_COUNT = 103


def build_fixture_index(fixture_dir: Path) -> Path:
    """Recreate the deterministic harness source index with enough pages to paginate."""
    index_dir = fixture_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "example.db"
    sidecar_file = index_dir / "example.vec.db"
    index_file.unlink(missing_ok=True)
    sidecar_file.unlink(missing_ok=True)

    init_db(str(index_file))
    upsert_page(
        str(index_file),
        "https://example.test/alpha",
        "Alpha",
        "Alpha documentation content.",
    )
    upsert_page(
        str(index_file),
        "https://example.test/beta",
        "Beta",
        "Beta documentation content.",
    )
    for number in range(1, _PAGE_COUNT - 1):
        upsert_page(
            str(index_file),
            f"https://example.test/generated-{number:03d}",
            f"Generated Page {number:03d}",
            f"Generated harness documentation page {number:03d}.",
        )
    return index_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/fixtures/harness"),
        help="Harness fixture root (default: tests/fixtures/harness)",
    )
    args = parser.parse_args()
    index_file = build_fixture_index(args.fixture_dir)
    print(f"Created {_PAGE_COUNT} indexed pages in {index_file}")


if __name__ == "__main__":
    main()
