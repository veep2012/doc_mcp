"""
Local vector-index helpers and post-crawl vectorization support.
"""

import hashlib
import math
import os
import re
import sqlite3
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - exercised via backend availability checks
    sqlite_vec = None

from .index_store import count_pages, iter_page_documents, list_page_documents

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
    chunk_size = chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    embedding_dimensions = (
        embedding_dimensions
        if embedding_dimensions is not None
        else DEFAULT_EMBEDDING_DIMENSIONS
    )

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


def chunk_markdown(
    text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> list[str]:
    """Split Markdown text into deterministic overlapping chunks."""
    normalized = _normalize_text(text)
    if not normalized:
        return []

    words = normalized.split(" ")
    if len(words) == 1:
        return [normalized]

    chunks: list[str] = []
    start = 0
    end = 0
    window_len = 0
    while start < len(words):
        while end < len(words):
            word_len = len(words[end])
            add_len = word_len if end == start else word_len + 1
            if window_len + add_len > chunk_size:
                break
            window_len += add_len
            end += 1

        if end == start:
            chunks.append(words[start])
            start += 1
            end = start
            window_len = 0
            continue

        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break

        shrink_start = start
        shrink_len = window_len
        while shrink_start < end - 1 and shrink_len > chunk_overlap:
            shrink_len -= len(words[shrink_start]) + 1
            shrink_start += 1

        if shrink_start == start:
            if end == start + 1:
                start = end
                window_len = 0
            else:
                window_len -= len(words[start]) + 1
                start += 1
        else:
            start = shrink_start
            window_len = shrink_len

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
    return [
        record
        for page in pages
        for record in _build_vector_records_for_page(
            site_name,
            page,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding_dimensions=embedding_dimensions,
        )
    ]


def _build_vector_records_for_page(
    site_name: str,
    page: dict,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_dimensions: int,
) -> list[VectorRecord]:
    source_text = _normalize_text(page.get("content_md") or "") or _normalize_text(
        page.get("title") or ""
    )
    if not source_text:
        return []

    return list(
        _iter_vector_records_for_page(
            site_name,
            page,
            source_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding_dimensions=embedding_dimensions,
        )
    )


def _iter_vector_records_for_page(
    site_name: str,
    page: dict,
    source_text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_dimensions: int,
):
    for chunk_index, chunk_text in enumerate(
        chunk_markdown(source_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    ):
        yield VectorRecord(
            site_name=site_name,
            page_url=page["url"],
            title=page.get("title") or "",
            chunk_id=_chunk_id(site_name, page["url"], chunk_index, chunk_text),
            chunk_text=chunk_text,
            embedding=_embed_text(chunk_text, embedding_dimensions),
            source_last_crawled=page.get("last_crawled"),
            chunk_index=chunk_index,
        )


def _emit_progress(message: str) -> None:
    print(f"[vectorize] {message}", flush=True)


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _init_vector_db(conn: sqlite3.Connection, *, embedding_dimensions: int) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA cache_size=-2048")
    conn.execute("PRAGMA mmap_size=0")
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

    source_index_path = Path(site["index_file"])
    if not source_index_path.exists():
        raise VectorSourceError(
            f"Keyword index not found: {site['index_file']}. Run docmcp-crawl before docmcp-vectorize."
        )

    total_pages = count_pages(site["index_file"])
    _emit_progress(f"Loaded {total_pages} pages from source index")

    vector_index_file = resolve_vector_index_file(site)
    target_path = Path(vector_index_file)
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    _emit_progress("Initializing vector index")
    conn = _connect_vector_index(str(temp_path))
    try:
        _init_vector_db(conn, embedding_dimensions=embedding_dimensions)
        chunk_count = 0
        page_count = 0
        source_max_last_crawled = None
        started_at = time.perf_counter()
        for page_index, page in enumerate(iter_page_documents(site["index_file"]), start=1):
            page_started_at = time.perf_counter()
            page_count += 1
            page_title = page.get("title") or page["url"]
            if page.get("last_crawled"):
                source_max_last_crawled = (
                    max(source_max_last_crawled, page["last_crawled"])
                    if source_max_last_crawled
                    else page["last_crawled"]
                )
            _emit_progress(f"Page {page_index}/{total_pages} start: {page_title}")

            page_chunk_count = 0
            embedding_rows: list[tuple[int, bytes]] = []
            chunk_rows: list[tuple[str, str, str, str, int, str, str | None, int]] = []
            for page_offset, record in enumerate(
                _iter_vector_records_for_page(
                    site["name"],
                    page,
                    page.get("content_md") or page.get("title") or "",
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    embedding_dimensions=embedding_dimensions,
                ),
                start=1,
            ):
                vec_rowid = chunk_count + page_offset
                embedding_rows.append((vec_rowid, sqlite_vec.serialize_float32(record.embedding)))
                chunk_rows.append(
                    (
                        record.chunk_id,
                        record.site_name,
                        record.page_url,
                        record.title,
                        record.chunk_index,
                        record.chunk_text,
                        record.source_last_crawled,
                        vec_rowid,
                    )
                )

                page_chunk_count += 1
                if page_chunk_count == 1 or page_chunk_count % 10 == 0:
                    _emit_progress(
                        f"Page {page_index}/{total_pages} chunk {page_chunk_count} "
                        f"(global chunk {chunk_count + page_chunk_count}, {_format_duration(time.perf_counter() - started_at)} elapsed)"
                    )

            _emit_progress(
                f"Page {page_index}/{total_pages} chunking complete: {page_chunk_count} chunks "
                f"({_format_duration(time.perf_counter() - page_started_at)} elapsed)"
            )
            conn.executemany(
                """
                INSERT INTO chunk_embeddings(rowid, embedding)
                VALUES (?, ?)
                """,
                embedding_rows,
            )
            _emit_progress(
                f"Page {page_index}/{total_pages} embeddings written: {page_chunk_count} rows "
                f"({_format_duration(time.perf_counter() - page_started_at)} elapsed)"
            )
            conn.executemany(
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
                chunk_rows,
            )
            _emit_progress(
                f"Page {page_index}/{total_pages} metadata written: {page_chunk_count} rows "
                f"({_format_duration(time.perf_counter() - page_started_at)} elapsed)"
            )
            chunk_count += page_chunk_count

            _emit_progress(
                f"Page {page_index}/{total_pages} done: {page_chunk_count} chunks in "
                f"{_format_duration(time.perf_counter() - page_started_at)} "
                f"({chunk_count} total, {_format_duration(time.perf_counter() - started_at)} elapsed)"
            )
            conn.commit()

        built_at = datetime.now(timezone.utc).isoformat()
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
                page_count,
                chunk_count,
                embedding_dimensions,
                chunk_size,
                chunk_overlap,
                source_max_last_crawled,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _emit_progress(
        f"Wrote temporary index {temp_path} in {_format_duration(time.perf_counter() - started_at)}"
    )
    os.replace(temp_path, target_path)
    _emit_progress(
        f"Replaced vector index {target_path} in {_format_duration(time.perf_counter() - started_at)}"
    )
    return VectorBuildSummary(
        site_name=site["name"],
        source_index_file=site["index_file"],
        vector_index_file=str(target_path),
        page_count=page_count,
        chunk_count=chunk_count,
        built_at=built_at,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
