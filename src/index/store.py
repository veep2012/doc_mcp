"""SQLite-backed page index store with FTS5 search support."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _db_path(db_path: str | Path) -> Path:
    return Path(db_path)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _require_existing_db(db_path: str | Path) -> Path:
    path = _db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Index file not found: {path}")
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prepare_match_query(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " ".join('"{}"'.format(token.replace('"', '""')) for token in tokens)


def init_db(db_path: str | Path) -> None:
    """Create the page table and FTS index if they do not already exist."""
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content_md TEXT NOT NULL,
                last_crawled TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
            USING fts5(
                url UNINDEXED,
                title,
                content_md
            );
            """
        )


def upsert_page(db_path: str | Path, url: str, title: str, content_md: str) -> None:
    """Insert or update a crawled page."""
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pages (url, title, content_md, last_crawled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                content_md = excluded.content_md,
                last_crawled = excluded.last_crawled
            """,
            (url, title, content_md, _now_iso()),
        )
        conn.execute("DELETE FROM pages_fts WHERE url = ?", (url,))
        conn.execute(
            "INSERT INTO pages_fts (url, title, content_md) VALUES (?, ?, ?)",
            (url, title, content_md),
        )


def count_pages(db_path: str | Path) -> int:
    """Return the number of indexed pages."""
    _require_existing_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
    return int(row["count"])


def list_pages(db_path: str | Path) -> list[dict]:
    """List all indexed pages ordered by title."""
    _require_existing_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT url, title, last_crawled FROM pages ORDER BY title COLLATE NOCASE, url"
        ).fetchall()
    return [dict(row) for row in rows]


def get_page(db_path: str | Path, url: str) -> dict | None:
    """Fetch a single indexed page by URL."""
    _require_existing_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT url, title, content_md, last_crawled FROM pages WHERE url = ?",
            (url,),
        ).fetchone()
    return dict(row) if row else None


def search_pages(db_path: str | Path, query: str, limit: int = 10) -> list[dict]:
    """Search the indexed pages with SQLite FTS5."""
    _require_existing_db(db_path)
    match_query = _prepare_match_query(query)
    if not match_query:
        return []

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                url,
                title,
                snippet(pages_fts, 2, '[', ']', ' … ', 12) AS excerpt
            FROM pages_fts
            WHERE pages_fts MATCH ?
            ORDER BY bm25(pages_fts)
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
    return [dict(row) for row in rows]
