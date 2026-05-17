"""
Local vector index lifecycle helpers.

The MCP runtime stays read-only. This module defines the repo-owned local vector
index contract plus the explicit post-crawl vectorizer that writes it.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .index_store import read_pages

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - exercised with monkeypatch in tests
    sqlite_vec = None

VECTOR_SCHEMA_VERSION = 1
DEFAULT_VECTOR_CHUNK_SIZE = 200
DEFAULT_VECTOR_CHUNK_OVERLAP = 40
DEFAULT_VECTOR_EMBEDDING_DIMENSIONS = 32


class VectorIndexError(RuntimeError):
    """Raised when the local vector index cannot be read or written."""


@dataclass(frozen=True)
class VectorRecord:
    site_key: str
    page_url: str
    title: str
    chunk_id: str
    chunk_index: int
    chunk_text: str
    embedding: list[float]
    last_crawled: str | None


@dataclass(frozen=True)
class VectorBuildSummary:
    site_name: str
    site_key: str
    source_index_file: str
    vector_index_file: str
    page_count: int
    chunk_count: int
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int


def site_vector_index_file(site: dict) -> str:
    """Return the configured or derived local vector index path for a site."""
    configured = site.get("vector_index_file")
    if configured:
        return str(configured)

    index_path = Path(site["index_file"])
    return str(index_path.with_name(f"{index_path.stem}.vec{index_path.suffix}"))


def vectorizer_settings(site: dict) -> dict[str, int]:
    """Return vectorizer settings with defaults applied."""
    configured = site.get("vectorizer") or {}
    chunk_size = int(configured.get("chunk_size", DEFAULT_VECTOR_CHUNK_SIZE))
    chunk_overlap = int(configured.get("chunk_overlap", DEFAULT_VECTOR_CHUNK_OVERLAP))
    embedding_dimensions = int(
        configured.get("embedding_dimensions", DEFAULT_VECTOR_EMBEDDING_DIMENSIONS)
    )

    if chunk_size <= 0:
        raise VectorIndexError("vectorizer.chunk_size must be greater than zero.")
    if chunk_overlap < 0:
        raise VectorIndexError("vectorizer.chunk_overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise VectorIndexError("vectorizer.chunk_overlap must be smaller than chunk_size.")
    if embedding_dimensions <= 0:
        raise VectorIndexError("vectorizer.embedding_dimensions must be greater than zero.")

    return {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embedding_dimensions": embedding_dimensions,
    }


def site_partition_key(site_name: str) -> str:
    """Return the stable site partition key stored with vector records."""
    return re.sub(r"\s+", " ", site_name.strip()).lower()


def _normalize_chunk_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _chunk_words(words: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    if not words:
        return []

    step = max(1, chunk_size - chunk_overlap)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            continue
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


def chunk_markdown(content_md: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split page Markdown into deterministic overlapping text chunks."""
    normalized = _normalize_chunk_text(content_md)
    if not normalized:
        return []
    return _chunk_words(normalized.split(" "), chunk_size, chunk_overlap)


def embed_text(text: str, dimensions: int) -> list[float]:
    """Build a deterministic local embedding for chunk storage and refresh tests."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return [0.0] * dimensions

    values = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] % 2 else 1.0
        values[bucket] += sign * (1.0 + (digest[5] / 255.0))

    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return values
    return [round(value / magnitude, 6) for value in values]


def shape_vector_records(site: dict, pages: list[dict]) -> list[VectorRecord]:
    """Convert indexed pages into deterministic vector records."""
    settings = vectorizer_settings(site)
    site_key = site_partition_key(site["name"])
    records: list[VectorRecord] = []

    for page in sorted(pages, key=lambda item: item["url"]):
        title = page.get("title") or page["url"]
        for chunk_index, chunk_text in enumerate(
            chunk_markdown(
                page.get("content_md") or "",
                settings["chunk_size"],
                settings["chunk_overlap"],
            )
        ):
            chunk_hash = hashlib.sha256(
                f"{site_key}\n{page['url']}\n{chunk_index}".encode("utf-8")
            ).hexdigest()[:16]
            records.append(
                VectorRecord(
                    site_key=site_key,
                    page_url=page["url"],
                    title=title,
                    chunk_id=f"{site_key}:{chunk_hash}:{chunk_index}",
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    embedding=embed_text(chunk_text, settings["embedding_dimensions"]),
                    last_crawled=page.get("last_crawled"),
                )
            )

    return records


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    if sqlite_vec is None:
        raise VectorIndexError(
            "sqlite-vec is not installed. Install it with: pip install sqlite-vec"
        )

    try:
        conn.enable_load_extension(True)
    except (AttributeError, sqlite3.Error) as exc:
        raise VectorIndexError(f"SQLite extension loading is unavailable: {exc}") from exc
    try:
        sqlite_vec.load(conn)
    except sqlite3.Error as exc:
        raise VectorIndexError(f"Unable to load sqlite-vec into SQLite: {exc}") from exc


def _vector_rw_conn(vector_index_file: str) -> sqlite3.Connection:
    path = Path(vector_index_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _load_sqlite_vec(conn)
    return conn


def _vector_ro_conn(vector_index_file: str) -> sqlite3.Connection | None:
    path = Path(vector_index_file)
    if not path.exists():
        return None
    # Use non-strict resolution so readonly URI opening still works for callers
    # that hand us normalized sidecar paths during transitions around rebuilds.
    conn = sqlite3.connect(f"{path.resolve(strict=False).as_uri()}?mode=ro", uri=True)
    _load_sqlite_vec(conn)
    return conn


def _read_global_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM vector_index_settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _init_vector_schema(conn: sqlite3.Connection, embedding_dimensions: int) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_index_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_builds (
            site_key TEXT PRIMARY KEY,
            site_name TEXT NOT NULL,
            source_index_file TEXT NOT NULL,
            vector_index_file TEXT NOT NULL,
            built_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            embedding_dimensions INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            page_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL
        )
        """
    )

    current_dimensions = _read_global_setting(conn, "embedding_dimensions")
    if current_dimensions is not None and int(current_dimensions) != embedding_dimensions:
        raise VectorIndexError(
            "The existing vector index uses embedding_dimensions="
            f"{current_dimensions}, but this run requested {embedding_dimensions}. "
            "Delete the vector index file or align the site configuration."
        )

    conn.execute(
        """
        INSERT INTO vector_index_settings(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(VECTOR_SCHEMA_VERSION),),
    )
    conn.execute(
        """
        INSERT INTO vector_index_settings(key, value)
        VALUES ('embedding_dimensions', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(embedding_dimensions),),
    )

    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
        USING vec0(
            site_key TEXT partition key,
            page_url TEXT,
            title TEXT,
            chunk_id TEXT,
            chunk_index INTEGER,
            last_crawled TEXT,
            chunk_embedding FLOAT[{embedding_dimensions}],
            +chunk_text TEXT
        )
        """
    )


def rebuild_vector_index(site: dict) -> VectorBuildSummary:
    """Rebuild a site's local vector index sidecar from the keyword index."""
    settings = vectorizer_settings(site)
    source_index_file = str(site["index_file"])
    vector_index_file = site_vector_index_file(site)
    if not Path(source_index_file).exists():
        raise VectorIndexError(
            f"Keyword index not found at {source_index_file}. Run docmcp-crawl first."
        )
    pages = read_pages(source_index_file)
    records = shape_vector_records(site, pages)
    site_key = site_partition_key(site["name"])

    try:
        with _vector_rw_conn(vector_index_file) as conn:
            _init_vector_schema(conn, settings["embedding_dimensions"])
            conn.execute("DELETE FROM vec_chunks WHERE site_key = ?", (site_key,))
            for record in records:
                conn.execute(
                    """
                    INSERT INTO vec_chunks(
                        site_key,
                        page_url,
                        title,
                        chunk_id,
                        chunk_index,
                        last_crawled,
                        chunk_embedding,
                        chunk_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.site_key,
                        record.page_url,
                        record.title,
                        record.chunk_id,
                        record.chunk_index,
                        record.last_crawled,
                        str(record.embedding),
                        record.chunk_text,
                    ),
                )

            conn.execute(
                """
                INSERT INTO vector_builds(
                    site_key,
                    site_name,
                    source_index_file,
                    vector_index_file,
                    built_at,
                    schema_version,
                    embedding_dimensions,
                    chunk_size,
                    chunk_overlap,
                    page_count,
                    chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_key) DO UPDATE SET
                    site_name = excluded.site_name,
                    source_index_file = excluded.source_index_file,
                    vector_index_file = excluded.vector_index_file,
                    built_at = excluded.built_at,
                    schema_version = excluded.schema_version,
                    embedding_dimensions = excluded.embedding_dimensions,
                    chunk_size = excluded.chunk_size,
                    chunk_overlap = excluded.chunk_overlap,
                    page_count = excluded.page_count,
                    chunk_count = excluded.chunk_count
                """,
                (
                    site_key,
                    site["name"],
                    source_index_file,
                    vector_index_file,
                    datetime.now(timezone.utc).isoformat(),
                    VECTOR_SCHEMA_VERSION,
                    settings["embedding_dimensions"],
                    settings["chunk_size"],
                    settings["chunk_overlap"],
                    len(pages),
                    len(records),
                ),
            )
    except sqlite3.Error as exc:
        raise VectorIndexError(f"Unable to rebuild vector index: {exc}") from exc

    return VectorBuildSummary(
        site_name=site["name"],
        site_key=site_key,
        source_index_file=source_index_file,
        vector_index_file=vector_index_file,
        page_count=len(pages),
        chunk_count=len(records),
        embedding_dimensions=settings["embedding_dimensions"],
        chunk_size=settings["chunk_size"],
        chunk_overlap=settings["chunk_overlap"],
    )


def inspect_vector_index(site: dict) -> dict:
    """Read a site's vector index status without writing to it."""
    vector_index_file = site_vector_index_file(site)
    try:
        conn = _vector_ro_conn(vector_index_file)
    except VectorIndexError as exc:
        return {"available": False, "reason": str(exc), "vector_index_file": vector_index_file}

    if conn is None:
        return {"available": False, "reason": "missing", "vector_index_file": vector_index_file}

    site_key = site_partition_key(site["name"])
    try:
        with conn as conn:
            build_row = conn.execute(
                """
                SELECT built_at, embedding_dimensions, chunk_size, chunk_overlap, page_count, chunk_count
                FROM vector_builds
                WHERE site_key = ?
                """,
                (site_key,),
            ).fetchone()
    except sqlite3.Error as exc:
        return {"available": False, "reason": f"unreadable: {exc}", "vector_index_file": vector_index_file}

    if build_row is None:
        return {"available": False, "reason": "site_missing", "vector_index_file": vector_index_file}

    return {
        "available": True,
        "vector_index_file": vector_index_file,
        "site_key": site_key,
        "built_at": build_row[0],
        "embedding_dimensions": build_row[1],
        "chunk_size": build_row[2],
        "chunk_overlap": build_row[3],
        "page_count": build_row[4],
        "chunk_count": build_row[5],
    }


def read_vector_records(vector_index_file: str, site_key: str) -> list[dict]:
    """Return stored vector rows for a site partition."""
    conn = _vector_ro_conn(vector_index_file)
    if conn is None:
        return []

    with conn as conn:
        rows = conn.execute(
            """
            SELECT
                site_key,
                page_url,
                title,
                chunk_id,
                chunk_index,
                chunk_text,
                vec_to_json(chunk_embedding),
                last_crawled
            FROM vec_chunks
            WHERE site_key = ?
            ORDER BY page_url, chunk_index
            """,
            (site_key,),
        ).fetchall()

    return [
        {
            "site_key": row[0],
            "page_url": row[1],
            "title": row[2],
            "chunk_id": row[3],
            "chunk_index": row[4],
            "chunk_text": row[5],
            "embedding": row[6],
            "last_crawled": row[7],
        }
        for row in rows
    ]
