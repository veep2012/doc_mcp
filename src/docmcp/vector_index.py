"""
Local vector-index helpers and post-crawl vectorization support.
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import suppress
from functools import lru_cache
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - exercised via backend availability checks
    sqlite_vec = None

from .index_store import _get_ro_conn, _normalize_search_limit, count_pages, iter_page_documents

logger = logging.getLogger("docmcp.observability")

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
VECTOR_SIDECAR_SCHEMA_VERSION = 2


class VectorIndexError(RuntimeError):
    """Base class for vector-index lifecycle errors."""


class VectorBackendUnavailableError(VectorIndexError):
    """Raised when sqlite-vec is unavailable in the current runtime."""


class EmbeddingBackendUnavailableError(VectorBackendUnavailableError):
    """Raised when the FastEmbed runtime or model is unavailable."""


class VectorSourceError(VectorIndexError):
    """Raised when the keyword crawl index cannot be used as vector source data."""


class VectorSidecarStaleError(VectorIndexError):
    """Raised when vector metadata no longer matches the current crawl source."""


class VectorSidecarIncompatibleError(VectorIndexError):
    """Raised when vector metadata no longer matches the current query configuration."""


class VectorSidecarSchemaMismatchError(VectorSidecarIncompatibleError):
    """Raised when the sidecar header or metadata schema version is unsupported."""


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
    embedding_model: str
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


def _normalize_embedding_model(value: object) -> str:
    if value is None or value == "":
        return DEFAULT_EMBEDDING_MODEL
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    raise ValueError("embedding_model must be a non-empty string")


def _site_embedding_model(site: dict) -> str:
    vectorizer_cfg = site.get("vectorizer", {})
    return _normalize_embedding_model(vectorizer_cfg.get("embedding_model"))


def _normalize_index_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def _source_fingerprint_key(
    url: str, title: str, content_md: str, last_crawled: str | None
) -> bytes:
    return "\0".join((url, title, content_md, last_crawled or "")).encode("utf-8")


def _source_index_fingerprint(index_file: str) -> tuple[int, str | None, str] | None:
    conn = _get_ro_conn(index_file)
    if conn is None:
        return None

    digest = hashlib.sha256()
    page_count = 0
    source_max_last_crawled: str | None = None
    try:
        with conn as conn:
            rows = conn.execute(
                "SELECT url, title, content_md, last_crawled FROM pages ORDER BY url"
            )
            for url, title, content_md, last_crawled in rows:
                page_count += 1
                if last_crawled:
                    source_max_last_crawled = (
                        max(source_max_last_crawled, last_crawled)
                        if source_max_last_crawled
                        else last_crawled
                    )
                digest.update(
                    _source_fingerprint_key(url, title or "", content_md or "", last_crawled)
                )
                digest.update(b"\0")
    finally:
        conn.close()

    return page_count, source_max_last_crawled, digest.hexdigest()


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _age_seconds_from_timestamp(value: str | None) -> float | None:
    timestamp = _parse_utc_timestamp(value)
    if timestamp is None:
        return None
    now = datetime.now(timezone.utc)
    age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
    return max(age, 0.0)


def _emit_observation(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sidecar_schema_mismatch(site_name: str, detail: str) -> VectorSidecarSchemaMismatchError:
    return VectorSidecarSchemaMismatchError(
        f"Vector sidecar schema mismatch for '{site_name}': {detail}. "
        "Rebuild the sidecar with docmcp-vectorize to migrate it."
    )


def _read_vector_sidecar_meta(
    conn: sqlite3.Connection, site_name: str
) -> tuple[str | None, str, int, str | None, str | None]:
    header_version_row = conn.execute("PRAGMA user_version").fetchone()
    header_version = int(header_version_row[0] if header_version_row else 0)
    if header_version != VECTOR_SIDECAR_SCHEMA_VERSION:
        raise _sidecar_schema_mismatch(
            site_name,
            f"unsupported header version {header_version} (expected {VECTOR_SIDECAR_SCHEMA_VERSION})",
        )

    try:
        meta = conn.execute(
            """
            SELECT
                schema_version,
                source_index_file,
                embedding_model,
                embedding_dimensions,
                source_content_hash,
                source_max_last_crawled
            FROM vector_meta
            WHERE site_name = ?
            LIMIT 1
            """,
            (site_name,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        lowered = str(exc).lower()
        if "no such column" in lowered or "no such table" in lowered:
            raise _sidecar_schema_mismatch(
                site_name,
                "legacy metadata schema missing schema_version",
            ) from exc
        raise

    if meta is None:
        raise VectorSidecarIncompatibleError(
            f"Vector sidecar for '{site_name}' is missing metadata for that site. "
            "Rebuild the sidecar with docmcp-vectorize."
        )

    schema_version = int(meta[0] or 0)
    if schema_version != VECTOR_SIDECAR_SCHEMA_VERSION:
        raise _sidecar_schema_mismatch(
            site_name,
            f"metadata schema version {schema_version} (expected {VECTOR_SIDECAR_SCHEMA_VERSION})",
        )

    source_index_file = meta[1] if meta[1] else None
    embedding_model = meta[2] or DEFAULT_EMBEDDING_MODEL
    embedding_dimensions = int(meta[3] or 0)
    source_content_hash = meta[4] if meta[4] else None
    source_max_last_crawled = meta[5] if meta[5] else None
    return (
        source_index_file,
        embedding_model,
        embedding_dimensions,
        source_content_hash,
        source_max_last_crawled,
    )


@lru_cache(maxsize=None)
def _load_text_embedding_backend(model_name: str):
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover - exercised through runtime error paths
        raise EmbeddingBackendUnavailableError(
            "fastembed is not installed. Install with: pip install fastembed"
        ) from exc

    try:
        return TextEmbedding(model_name=model_name)
    except Exception as exc:  # pragma: no cover - exercised through runtime error paths
        raise EmbeddingBackendUnavailableError(
            f"FastEmbed model '{model_name}' could not be loaded: {exc}"
        ) from exc


def _coerce_embedding(embedding: object) -> list[float]:
    if hasattr(embedding, "tolist"):
        values = embedding.tolist()
    else:
        values = list(embedding)  # type: ignore[arg-type]
    return [float(value) for value in values]


def _embed_texts(texts: list[str], model_name: str) -> list[list[float]]:
    backend = _load_text_embedding_backend(model_name)
    embeddings = backend.embed(texts)
    return [_coerce_embedding(embedding) for embedding in embeddings]


@lru_cache(maxsize=None)
def _infer_embedding_dimensions(model_name: str, loader_token: object | None = None) -> int:
    return len(_embed_texts(["embedding probe"], model_name)[0])


def _connect_ro_vector_index(index_file: str) -> sqlite3.Connection | None:
    available, message = vector_backend_status()
    if not available:
        raise VectorBackendUnavailableError(message or "sqlite-vec is unavailable.")

    path = Path(index_file)
    if not path.exists():
        return None
    try:
        resolved_path = path.resolve(strict=True)
    except FileNotFoundError:
        return None

    conn = sqlite3.connect(f"{resolved_path.as_uri()}?mode=ro", uri=True)
    try:
        conn.enable_load_extension(True)
    except (AttributeError, sqlite3.NotSupportedError) as exc:
        conn.close()
        raise VectorBackendUnavailableError(
            "SQLite extension loading is not available in this Python runtime."
        ) from exc

    try:
        sqlite_vec.load(conn)
    finally:
        with suppress(sqlite3.Error):
            conn.enable_load_extension(False)
    return conn


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


def search_vector_chunks(site: dict, query: str, limit: int = 10) -> list[dict]:
    """Run a read-only nearest-neighbor search against a site's local vector sidecar."""
    limit = _normalize_search_limit(limit)
    if limit is None:
        return []

    conn = _connect_ro_vector_index(resolve_vector_index_file(site))
    if conn is None:
        return []

    try:
        (
            _source_index_file,
            embedding_model,
            embedding_dimensions,
            source_content_hash,
            source_max_last_crawled,
        ) = _read_vector_sidecar_meta(conn, site["name"])
        if not site.get("index_file"):
            raise VectorSidecarIncompatibleError(
                f"Vector sidecar for '{site['name']}' cannot be validated because the "
                "site configuration is missing index_file. Rebuild with docmcp-vectorize "
                "after fixing the site config."
            )

        current_fingerprint = _source_index_fingerprint(site["index_file"])
        if current_fingerprint is None:
            raise VectorSidecarIncompatibleError(
                f"Vector sidecar for '{site['name']}' cannot be validated because the "
                f"source index is missing or unreadable: {site['index_file']}. "
                "Rebuild the sidecar with docmcp-vectorize after restoring the crawl index."
            )

        _current_page_count, current_max_last_crawled, current_content_hash = current_fingerprint
        if (
            source_content_hash != current_content_hash
            or source_max_last_crawled != current_max_last_crawled
        ):
            raise VectorSidecarStaleError(
                f"Vector sidecar for '{site['name']}' is stale: "
                f"stored content hash={source_content_hash}, current content hash={current_content_hash}; "
                f"stored crawl timestamp={source_max_last_crawled}, current crawl timestamp={current_max_last_crawled}. "
                "Rebuild the sidecar with docmcp-vectorize."
            )

        configured_embedding_model = _site_embedding_model(site)
        if configured_embedding_model != embedding_model:
            raise VectorSidecarIncompatibleError(
                f"Vector sidecar embedding model mismatch for '{site['name']}': "
                f"sidecar={embedding_model}, configured={configured_embedding_model}. "
                "Rebuild the sidecar with docmcp-vectorize."
            )
        if embedding_dimensions <= 0:
            raise VectorSidecarIncompatibleError(
                f"Vector sidecar metadata for '{site['name']}' is missing embedding dimensions. "
                "Rebuild the sidecar with docmcp-vectorize."
            )

        query_embedding = _embed_text(query, embedding_model)
        if embedding_dimensions and len(query_embedding) != embedding_dimensions:
            raise VectorSidecarIncompatibleError(
                f"Vector sidecar embedding dimension mismatch for '{site['name']}': "
                f"expected {embedding_dimensions}, got {len(query_embedding)}. "
                "Rebuild the sidecar with docmcp-vectorize."
            )

        rows = conn.execute(
            """
            SELECT
                vc.chunk_id,
                vc.page_url,
                vc.title,
                vc.chunk_text,
                vc.chunk_index,
                ce.distance
            FROM chunk_embeddings AS ce
            JOIN vector_chunks AS vc
              ON vc.vec_rowid = ce.rowid
            WHERE vc.site_name = ?
              AND ce.embedding MATCH ?
              AND k = ?
            ORDER BY ce.distance, vc.page_url, vc.chunk_index, vc.chunk_id
            """,
            (
                site["name"],
                sqlite_vec.serialize_float32(query_embedding),
                limit,
            ),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "chunk_id": row[0],
            "page_url": row[1],
            "title": row[2],
            "text": row[3],
            "chunk_index": row[4],
            "distance": row[5],
        }
        for row in rows
    ]


def _normalize_chunk_settings(
    chunk_size: int | None,
    chunk_overlap: int | None,
    embedding_model: str | None,
) -> tuple[int, int, str]:
    chunk_size = chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    embedding_model = _normalize_embedding_model(embedding_model)

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    return chunk_size, chunk_overlap, embedding_model


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


def _embed_text(text: str, embedding_model: str) -> list[float]:
    """Generate a FastEmbed vector for a single text chunk."""
    return _embed_texts([text], embedding_model)[0]


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
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
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
            embedding_model=embedding_model,
        )
    ]


def _build_vector_records_for_page(
    site_name: str,
    page: dict,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
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
            embedding_model=embedding_model,
        )
    )


def _iter_vector_records_for_page(
    site_name: str,
    page: dict,
    source_text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
):
    chunks = chunk_markdown(source_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return

    embeddings = _embed_texts(chunks, embedding_model)
    for chunk_index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        yield VectorRecord(
            site_name=site_name,
            page_url=page["url"],
            title=page.get("title") or "",
            chunk_id=_chunk_id(site_name, page["url"], chunk_index, chunk_text),
            chunk_text=chunk_text,
            embedding=embedding,
            source_last_crawled=page.get("last_crawled"),
            chunk_index=chunk_index,
        )


def _emit_progress(message: str) -> None:
    print(f"[vectorize] {message}", flush=True)


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _init_vector_db(
    conn: sqlite3.Connection, *, embedding_model: str, embedding_dimensions: int
) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA cache_size=-2048")
    conn.execute("PRAGMA mmap_size=0")
    conn.execute(f"PRAGMA user_version = {VECTOR_SIDECAR_SCHEMA_VERSION}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_meta (
            site_name TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            source_index_file TEXT NOT NULL,
            built_at TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            embedding_dimensions INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            source_content_hash TEXT NOT NULL,
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


def rebuild_vector_index(site: dict, *, debug: bool = False) -> VectorBuildSummary:
    """Rebuild a site's local vector sidecar from the current crawl index."""
    vectorizer_cfg = site.get("vectorizer", {})
    chunk_size, chunk_overlap, embedding_model = _normalize_chunk_settings(
        vectorizer_cfg.get("chunk_size"),
        vectorizer_cfg.get("chunk_overlap"),
        _site_embedding_model(site),
    )

    source_index_path = Path(site["index_file"])
    if not source_index_path.exists():
        raise VectorSourceError(
            f"Keyword index not found: {site['index_file']}. Run docmcp-crawl before docmcp-vectorize."
        )

    try:
        total_pages = count_pages(site["index_file"])
    except sqlite3.Error as exc:
        raise VectorSourceError(
            f"Keyword index unreadable: {site['index_file']}. Run docmcp-crawl before docmcp-vectorize."
        ) from exc
    _emit_progress(f"Loaded {total_pages} pages from source index")

    embedding_dimensions = _infer_embedding_dimensions(
        embedding_model, _load_text_embedding_backend
    )

    vector_index_file = resolve_vector_index_file(site)
    target_path = Path(vector_index_file)
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    _emit_progress("Initializing vector index")
    started_at = time.perf_counter()
    conn = _connect_vector_index(str(temp_path))
    try:
        _init_vector_db(
            conn,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )
        chunk_count = 0
        page_count = 0
        source_content_digest = hashlib.sha256()
        source_max_last_crawled = None
        try:
            source_pages = iter_page_documents(site["index_file"])
            for page_index, page in enumerate(source_pages, start=1):
                page_started_at = time.perf_counter()
                page_count += 1
                page_title = page.get("title") or page["url"]
                source_content_digest.update(
                    _source_fingerprint_key(
                        page["url"],
                        page.get("title") or "",
                        page.get("content_md") or "",
                        page.get("last_crawled"),
                    )
                )
                source_content_digest.update(b"\0")
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
                        embedding_model=embedding_model,
                    ),
                    start=1,
                ):
                    vec_rowid = chunk_count + page_offset
                    embedding_rows.append(
                        (vec_rowid, sqlite_vec.serialize_float32(record.embedding))
                    )
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
                    if debug and (page_chunk_count == 1 or page_chunk_count % 10 == 0):
                        _emit_progress(
                            f"Page {page_index}/{total_pages} chunk {page_chunk_count} "
                            f"(global chunk {chunk_count + page_chunk_count}, {_format_duration(time.perf_counter() - started_at)} elapsed)"
                        )

                if debug:
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
                if debug:
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
                if debug:
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
        except sqlite3.Error as exc:
            raise VectorSourceError(
                f"Keyword index unreadable: {site['index_file']}. Run docmcp-crawl before docmcp-vectorize."
            ) from exc

        built_at = datetime.now(timezone.utc).isoformat()
        source_content_hash = source_content_digest.hexdigest()
        conn.execute(
            """
            INSERT INTO vector_meta(
                site_name,
                schema_version,
                source_index_file,
                built_at,
                embedding_model,
                page_count,
                chunk_count,
                embedding_dimensions,
                chunk_size,
                chunk_overlap,
                source_content_hash,
                source_max_last_crawled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site["name"],
                VECTOR_SIDECAR_SCHEMA_VERSION,
                site["index_file"],
                built_at,
                embedding_model,
                page_count,
                chunk_count,
                embedding_dimensions,
                chunk_size,
                chunk_overlap,
                source_content_hash,
                source_max_last_crawled,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _emit_progress(
        f"Wrote temporary index {temp_path} in {_format_duration(time.perf_counter() - started_at)}"
    )
    _fsync_file(temp_path)
    os.replace(temp_path, target_path)
    _fsync_directory(target_path.parent)
    vectorizer_duration = time.perf_counter() - started_at
    _emit_progress(
        f"Replaced vector index {target_path} in {_format_duration(vectorizer_duration)}"
    )
    _emit_observation(
        "vectorizer_completed",
        site_name=site["name"],
        source_index_file=site["index_file"],
        vector_index_file=str(target_path),
        vectorizer_duration=round(vectorizer_duration, 6),
        index_doc_count=page_count,
        page_count=page_count,
        chunk_count=chunk_count,
        source_max_last_crawled=source_max_last_crawled,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return VectorBuildSummary(
        site_name=site["name"],
        source_index_file=site["index_file"],
        vector_index_file=str(target_path),
        page_count=page_count,
        chunk_count=chunk_count,
        built_at=built_at,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
