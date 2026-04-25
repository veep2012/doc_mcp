"""
SQLite index store — stores crawled pages as Markdown with metadata.
Uses SQLite FTS5 for full-text keyword search.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _get_conn(index_file: str) -> sqlite3.Connection:
    path = Path(index_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def init_db(index_file: str) -> None:
    """Create tables and FTS index if they don't exist."""
    with _get_conn(index_file) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT UNIQUE NOT NULL,
                title       TEXT,
                content_md  TEXT,
                last_crawled TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
            USING fts5(
                title,
                content_md,
                content='pages',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
                INSERT INTO pages_fts(rowid, title, content_md)
                VALUES (new.id, new.title, new.content_md);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, title, content_md)
                VALUES ('delete', old.id, old.title, old.content_md);
                INSERT INTO pages_fts(rowid, title, content_md)
                VALUES (new.id, new.title, new.content_md);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, title, content_md)
                VALUES ('delete', old.id, old.title, old.content_md);
            END;
        """
        )


def upsert_page(index_file: str, url: str, title: str, content_md: str) -> None:
    """Insert or update a page in the index."""
    last_crawled = datetime.now(timezone.utc).isoformat()
    with _get_conn(index_file) as conn:
        conn.execute(
            """
            INSERT INTO pages (url, title, content_md, last_crawled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title        = excluded.title,
                content_md   = excluded.content_md,
                last_crawled = excluded.last_crawled
        """,
            (url, title, content_md, last_crawled),
        )


def search_pages(index_file: str, query: str, limit: int = 10) -> list[dict]:
    """Full-text search across title and content. Returns list of matching pages."""
    with _get_conn(index_file) as conn:
        rows = conn.execute(
            """
            SELECT p.url, p.title, p.last_crawled,
                   snippet(pages_fts, 1, '[', ']', '...', 20) AS excerpt
            FROM pages_fts
            JOIN pages p ON pages_fts.rowid = p.id
            WHERE pages_fts MATCH ?
            ORDER BY bm25(pages_fts)
            LIMIT ?
        """,
            (query, limit),
        ).fetchall()
    return [{"url": r[0], "title": r[1], "last_crawled": r[2], "excerpt": r[3]} for r in rows]


def get_page(index_file: str, url: str) -> dict | None:
    """Fetch a single page by URL."""
    with _get_conn(index_file) as conn:
        row = conn.execute(
            "SELECT url, title, content_md, last_crawled FROM pages WHERE url = ?", (url,)
        ).fetchone()
    if row:
        return {"url": row[0], "title": row[1], "content_md": row[2], "last_crawled": row[3]}
    return None


def list_pages(index_file: str) -> list[dict]:
    """List all indexed pages (url, title, last_crawled)."""
    with _get_conn(index_file) as conn:
        rows = conn.execute("SELECT url, title, last_crawled FROM pages ORDER BY title").fetchall()
    return [{"url": r[0], "title": r[1], "last_crawled": r[2]} for r in rows]


def count_pages(index_file: str) -> int:
    """Return total number of indexed pages."""
    with _get_conn(index_file) as conn:
        return conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
