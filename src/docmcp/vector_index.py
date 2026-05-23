"""
Local vector-index helpers and post-crawl vectorization support.
"""

import hashlib
import math
import os
import re
import sqlite3
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - exercised via backend availability checks
    sqlite_vec = None

from .index_store import list_page_documents

DEFAULT_EMBEDDING_DIMENSIONS = 32
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class VectorIndexError(RuntimeError):
    """Base class for vector-index lifecycle errors."""


class VectorBackendUnavailableError(VectorIndexError):
    """Raised when sqlite-vec is unavailable in the current runtime."""


class VectorSourceError(VectorIndexError):
    """Raised when the keyword crawl index cannot be used as vector source data."""


@dataclass(frozen=True)
class VectorRecord:
    site_name: str
    page_url: str
    title: str
    chunk_id: str
    chunk_text: str
    embedding: list[float]
    source_last_crawled: str | None
    chunk_index: int

    def as_row(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VectorBuildSummary:
    site_name: str
    source_index_file: str
    vector_index_file: str
    page_count: int
    chunk_count: int
    built_at: str
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int


def resolve_vector_index_file(site: dict) -> str:
    """Return the configured vector sidecar path for a site."""
    configured = site.get("vector_index_file")
    if configured:
        return str(configured)
    index_path = Path(site["index_file"])
    return str(index_path.with_name(f"{index_path.stem}.vec.db"))


def vector_backend_status() -> tuple[bool, str | None]:
    """Return whether sqlite-vec can be loaded in this Python runtime."""
    if sqlite_vec is None:
        return False, "sqlite-vec is not installed. Install with: pip install sqlite-vec"
    try:
        conn = sqlite3.connect(":memory:")
    except sqlite3.Error as exc:
        return False, f"SQLite is unavailable: {exc}"
    try:
        try:
            conn.enable_load_extension(True)
        except (AttributeError, sqlite3.NotSupportedError):
            return False, "SQLite extension loading is not available in this Python runtime."
        sqlite_vec.load(conn)
    except sqlite3.Error as exc:
        return False, f"sqlite-vec could not be loaded: {exc}"
    finally:
        with suppress(sqlite3.Error):
            conn.enable_load_extension(False)
        conn.close()
    return True, None


def _connect_vector_index(index_file: str) -> sqlite3.Connection:
    available, message = vector_backend_status()
    if not available:
        raise VectorBackendUnavailableError(message or "sqlite-vec is unavailable.")

    path = Path(index_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _normalize_chunk_settings(
    chunk_size: int | None,
    chunk_overlap: int | None,
    embedding_dimensions: int | None,
) -> tuple[int, int, int]:
    chunk_size = chunk_size or DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    embedding_dimensions = embedding_dimensions or DEFAULT_EMBEDDING_DIMENSIONS

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    if embedding_dimensions <= 0:
        raise ValueError("embedding_dimensions must be positive")

    return chunk_size, chunk_overlap, embedding_dimensions


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def chunk_markdown(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split Markdown text into deterministic overlapping chunks."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    words = normalized.split(" ")
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        current_words: list[str] = []
        current_length = 0
        while end < len(words):
            word = words[end]
            next_length = current_length + len(word) + (1 if current_words else 0)
            if current_words and next_length > chunk_size:
                break
            current_words.append(word)
            current_length = next_length
            end += 1

        if not current_words:
            current_words.append(words[end])
            end += 1

        chunks.append(" ".join(current_words))
        if end >= len(words):
            break

        overlap_chars = 0
        overlap_start = end
        while overlap_start > start:
            overlap_start -= 1
            overlap_chars += len(words[overlap_start]) + (0 if overlap_start == end - 1 else 1)
            if overlap_chars >= chunk_overlap:
                break
        start = overlap_start if overlap_start < end else end

    return chunks


def _embed_text(text: str, dimensions: int) -> list[float]:
    """Create a deterministic local embedding vector for a text chunk."""
    vector = [0.0] * dimensions
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        vector[0] = 1.0
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        primary = int.from_bytes(digest[:4], "little") % dimensions
        secondary = int.from_bytes(digest[4:8], "little") % dimensions
        sign = -1.0 if digest[8] & 1 else 1.0
        weight = 1.0 + (digest[9] / 255.0)
        vector[primary] += sign * weight
        vector[secondary] += (weight / 2.0) * (-sign)

    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        vector[0] = 1.0
        norm = 1.0
    return [component / norm for component in vector]


def _chunk_id(site_name: str, page_url: str, chunk_index: int, chunk_text: str) -> str:
    digest = hashlib.sha256(
        f"{site_name}\n{page_url}\n{chunk_index}\n{chunk_text}".encode("utf-8")
    ).hexdigest()
    return digest


def build_vector_records(
    site_name: str,
    pages: list[dict],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> list[VectorRecord]:
    """Convert crawled page documents into vector records."""
    records: list[VectorRecord] = []
    for page in pages:
        source_text = _normalize_text(page.get("content_md") or "") or _normalize_text(
            page.get("title") or ""
        )
        if not source_text:
            continue

        for chunk_index, chunk_text in enumerate(
            chunk_markdown(source_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        ):
            records.append(
                VectorRecord(
                    site_name=site_name,
                    page_url=page["url"],
                    title=page.get("title") or "",
                    chunk_id=_chunk_id(site_name, page["url"], chunk_index, chunk_text),
                    chunk_text=chunk_text,
                    embedding=_embed_text(chunk_text, embedding_dimensions),
                    source_last_crawled=page.get("last_crawled"),
                    chunk_index=chunk_index,
                )
            )
    return records


def _init_vector_db(conn: sqlite3.Connection, *, embedding_dimensions: int) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_meta (
            site_name TEXT PRIMARY KEY,
            source_index_file TEXT NOT NULL,
            built_at TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            embedding_dimensions INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            source_max_last_crawled TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_chunks (
            chunk_id TEXT PRIMARY KEY,
            site_name TEXT NOT NULL,
            page_url TEXT NOT NULL,
            title TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_last_crawled TEXT,
            vec_rowid INTEGER NOT NULL UNIQUE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_chunks_page ON vector_chunks(page_url, chunk_index)"
    )
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(embedding float[{embedding_dimensions}])"
    )
    conn.commit()


def _source_pages(index_file: str) -> list[dict]:
    path = Path(index_file)
    if not path.exists():
        raise VectorSourceError(
            f"Keyword index not found: {index_file}. Run docmcp-crawl before docmcp-vectorize."
        )
    try:
        return list_page_documents(index_file)
    except sqlite3.Error as exc:
        raise VectorSourceError(f"Keyword index is unreadable: {index_file}\n{exc}") from exc


def rebuild_vector_index(site: dict) -> VectorBuildSummary:
    """Rebuild a site's local vector sidecar from the current crawl index."""
    vectorizer_cfg = site.get("vectorizer", {})
    chunk_size, chunk_overlap, embedding_dimensions = _normalize_chunk_settings(
        vectorizer_cfg.get("chunk_size"),
        vectorizer_cfg.get("chunk_overlap"),
        vectorizer_cfg.get("embedding_dimensions"),
    )

    pages = _source_pages(site["index_file"])
    records = build_vector_records(
        site["name"],
        pages,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_dimensions=embedding_dimensions,
    )

    vector_index_file = resolve_vector_index_file(site)
    target_path = Path(vector_index_file)
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    conn = _connect_vector_index(str(temp_path))
    try:
        _init_vector_db(conn, embedding_dimensions=embedding_dimensions)
        for record in records:
            cursor = conn.execute(
                "INSERT INTO chunk_embeddings(embedding) VALUES (?)",
                (sqlite_vec.serialize_float32(record.embedding),),
            )
            conn.execute(
                """
                INSERT INTO vector_chunks(
                    chunk_id,
                    site_name,
                    page_url,
                    title,
                    chunk_index,
                    chunk_text,
                    source_last_crawled,
                    vec_rowid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.chunk_id,
                    record.site_name,
                    record.page_url,
                    record.title,
                    record.chunk_index,
                    record.chunk_text,
                    record.source_last_crawled,
                    cursor.lastrowid,
                ),
            )

        built_at = datetime.now(timezone.utc).isoformat()
        source_max_last_crawled = max(
            (page.get("last_crawled") for page in pages if page.get("last_crawled")),
            default=None,
        )
        conn.execute(
            """
            INSERT INTO vector_meta(
                site_name,
                source_index_file,
                built_at,
                page_count,
                chunk_count,
                embedding_dimensions,
                chunk_size,
                chunk_overlap,
                source_max_last_crawled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site["name"],
                site["index_file"],
                built_at,
                len(pages),
                len(records),
                embedding_dimensions,
                chunk_size,
                chunk_overlap,
                source_max_last_crawled,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    os.replace(temp_path, target_path)
    return VectorBuildSummary(
        site_name=site["name"],
        source_index_file=site["index_file"],
        vector_index_file=str(target_path),
        page_count=len(pages),
        chunk_count=len(records),
        built_at=built_at,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

