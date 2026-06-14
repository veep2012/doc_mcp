import sqlite3

import pytest

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - exercised only when the backend is unavailable
    sqlite_vec = None

import docmcp.vector_index as vector_index
from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingBackendUnavailableError,
    VectorIndexError,
    VectorSourceError,
    build_vector_records,
    chunk_markdown,
    rebuild_vector_index,
    resolve_vector_index_file,
    search_vector_chunks,
    _normalize_chunk_settings,
    vector_backend_status,
)


def _require_vector_backend():
    available, message = vector_backend_status()
    if not available:
        pytest.skip(message or "sqlite-vec backend unavailable")


def _read_vector_db(index_file):
    _require_vector_backend()
    conn = sqlite3.connect(str(index_file))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def test_build_vector_records_shapes_stable_chunk_records():
    records = build_vector_records(
        "Example Docs",
        [
            {
                "url": "https://example.test/guide",
                "title": "Guide",
                "content_md": "Alpha beta gamma delta epsilon zeta eta theta",
                "last_crawled": "2026-05-23T00:00:00+00:00",
            }
        ],
        chunk_size=20,
        chunk_overlap=5,
        embedding_model="fake-fastembed-model",
    )

    assert len(records) >= 2
    assert records[0].site_name == "Example Docs"
    assert records[0].page_url == "https://example.test/guide"
    assert records[0].title == "Guide"
    assert records[0].chunk_index == 0
    assert len(records[0].embedding) == 8
    assert records[0].chunk_id
    assert records[0].chunk_text
    assert (
        build_vector_records(
            "Example Docs",
            [
                {
                    "url": "https://example.test/guide",
                    "title": "Guide",
                    "content_md": "Alpha beta gamma delta epsilon zeta eta theta",
                    "last_crawled": "2026-05-23T00:00:00+00:00",
                }
            ],
            chunk_size=20,
            chunk_overlap=5,
            embedding_model="fake-fastembed-model",
        )
        == records
    )


def test_chunk_markdown_handles_oversized_tokens():
    text = "alpha " + ("x" * 1200) + " beta gamma"

    chunks = chunk_markdown(text, chunk_size=800, chunk_overlap=120)

    assert chunks
    assert chunks[0].startswith("alpha")
    assert any("x" * 1200 in chunk for chunk in chunks)
    assert chunks[-1].endswith("gamma")


def test_vector_backend_status_reports_missing_dependency(monkeypatch):
    monkeypatch.setattr("docmcp.vector_index.sqlite_vec", None)

    available, message = vector_backend_status()

    assert not available
    assert "pip install sqlite-vec" in message


def test_fastembed_supports_documented_embedding_models():
    try:
        from fastembed import TextEmbedding
    except ModuleNotFoundError:
        pytest.skip("fastembed is not installed in the test environment")

    supported_models = {model["model"] for model in TextEmbedding.list_supported_models()}

    assert DEFAULT_EMBEDDING_MODEL in supported_models
    assert "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in supported_models


def test_infer_embedding_dimensions_is_cached_by_loader_token(monkeypatch):
    calls: list[str] = []

    def fake_embed_texts(texts, model_name: str):
        calls.append(model_name)
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(vector_index, "_embed_texts", fake_embed_texts)
    vector_index._infer_embedding_dimensions.cache_clear()

    loader_token = object()
    assert vector_index._infer_embedding_dimensions("fake-fastembed-model", loader_token) == 3
    assert vector_index._infer_embedding_dimensions("fake-fastembed-model", loader_token) == 3
    assert calls == ["fake-fastembed-model"]

    assert vector_index._infer_embedding_dimensions("fake-fastembed-model", object()) == 3
    assert calls == ["fake-fastembed-model", "fake-fastembed-model"]


def test_resolve_vector_index_file_defaults_to_sidecar_name(tmp_path):
    site = {"index_file": str(tmp_path / "index" / "docs.db")}

    assert resolve_vector_index_file(site) == str(tmp_path / "index" / "docs.vec.db")


@pytest.mark.parametrize(
    "chunk_size, chunk_overlap, expected",
    [
        (0, 5, "chunk_size must be positive"),
        (18, -1, "chunk_overlap must be non-negative"),
        (18, 18, "chunk_overlap must be smaller than chunk_size"),
        (18, 19, "chunk_overlap must be smaller than chunk_size"),
    ],
)
def test_normalize_chunk_settings_rejects_invalid_values(chunk_size, chunk_overlap, expected):
    with pytest.raises(ValueError, match=expected):
        _normalize_chunk_settings(chunk_size, chunk_overlap, None)


def test_rebuild_vector_index_creates_and_refreshes_sidecar(tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))
    upsert_page(
        str(source_index),
        "https://example.test/guide",
        "Guide",
        "Alpha beta gamma delta epsilon",
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index),
        "vectorizer": {
            "chunk_size": 18,
            "chunk_overlap": 5,
            "embedding_model": "fake-fastembed-model",
        },
    }

    summary = rebuild_vector_index(site)

    assert summary.page_count == 1
    assert summary.chunk_count >= 2
    assert summary.embedding_model == "fake-fastembed-model"
    assert summary.embedding_dimensions == 8
    assert vector_index.exists()

    with _read_vector_db(vector_index) as conn:
        first_rows = conn.execute(
            "SELECT chunk_id, page_url, title, chunk_text FROM vector_chunks ORDER BY chunk_index"
        ).fetchall()
        meta = conn.execute(
            "SELECT site_name, page_count, chunk_count, embedding_model, embedding_dimensions FROM vector_meta"
        ).fetchone()

    assert meta == ("Example Docs", 1, len(first_rows), "fake-fastembed-model", 8)
    assert all(row[1] == "https://example.test/guide" for row in first_rows)

    upsert_page(
        str(source_index),
        "https://example.test/guide",
        "Guide Updated",
        "Alpha beta gamma delta epsilon zeta eta theta iota",
    )

    rebuild_vector_index(site)

    with _read_vector_db(vector_index) as conn:
        second_rows = conn.execute(
            "SELECT chunk_id, title, chunk_text FROM vector_chunks ORDER BY chunk_index"
        ).fetchall()

    assert second_rows != first_rows
    assert all(row[1] == "Guide Updated" for row in second_rows)
    assert len({row[0] for row in second_rows}) == len(second_rows)
    assert len(second_rows) >= len(first_rows)
    assert any("theta" in row[2] for row in second_rows)


def test_rebuild_vector_index_requires_existing_keyword_index(tmp_path):
    site = {
        "name": "Example Docs",
        "index_file": str(tmp_path / "missing" / "docs.db"),
        "vector_index_file": str(tmp_path / "index" / "docs.vec.db"),
    }

    with pytest.raises(VectorSourceError, match="Run docmcp-crawl before docmcp-vectorize"):
        rebuild_vector_index(site)


def test_rebuild_vector_index_reports_missing_source_before_embedding_backend(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        vector_index,
        "_load_text_embedding_backend",
        lambda model_name: (_ for _ in ()).throw(
            EmbeddingBackendUnavailableError("fastembed is not installed")
        ),
    )

    site = {
        "name": "Example Docs",
        "index_file": str(tmp_path / "missing" / "docs.db"),
        "vector_index_file": str(tmp_path / "index" / "docs.vec.db"),
        "vectorizer": {"embedding_model": "fake-fastembed-model"},
    }

    with pytest.raises(VectorSourceError, match="Keyword index not found"):
        rebuild_vector_index(site)


def test_rebuild_vector_index_rejects_corrupt_source_index(tmp_path):
    source_index = tmp_path / "index" / "docs.db"
    source_index.parent.mkdir(parents=True, exist_ok=True)
    source_index.write_bytes(b"not a sqlite database")

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(tmp_path / "index" / "docs.vec.db"),
    }

    with pytest.raises(VectorSourceError, match="Keyword index unreadable"):
        rebuild_vector_index(site)


def test_rebuild_vector_index_handles_empty_source_index(tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index),
    }

    summary = rebuild_vector_index(site)

    assert summary.page_count == 0
    assert summary.chunk_count == 0
    assert vector_index.exists()

    with _read_vector_db(vector_index) as conn:
        meta = conn.execute("SELECT site_name, page_count, chunk_count FROM vector_meta").fetchone()
        chunk_rows = conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]

    assert meta == ("Example Docs", 0, 0)
    assert chunk_rows == 0


def test_search_vector_chunks_reads_ranked_matches_from_sidecar(tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))
    upsert_page(
        str(source_index),
        "https://example.test/vector-best",
        "Vector Best",
        "Alpha alpha alpha beta",
    )
    upsert_page(
        str(source_index),
        "https://example.test/vector-next",
        "Vector Next",
        "Gamma delta epsilon zeta",
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index),
        "vectorizer": {
            "chunk_size": 100,
            "chunk_overlap": 20,
            "embedding_model": "fake-fastembed-model",
        },
    }
    rebuild_vector_index(site)

    results = search_vector_chunks(site, "Alpha", limit=2)

    assert [result["page_url"] for result in results] == [
        "https://example.test/vector-best",
        "https://example.test/vector-next",
    ]
    assert results[0]["distance"] <= results[1]["distance"]
    assert all(result["chunk_id"] for result in results)
    assert all(isinstance(result["text"], str) and result["text"] for result in results)


def test_search_vector_chunks_rejects_stale_embedding_dimensions(monkeypatch, tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index_file = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))
    upsert_page(
        str(source_index),
        "https://example.test/vector-best",
        "Vector Best",
        "Alpha alpha alpha beta",
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index_file),
        "vectorizer": {
            "chunk_size": 100,
            "chunk_overlap": 20,
            "embedding_model": "fake-fastembed-model",
        },
    }
    rebuild_vector_index(site)

    class _ShortEmbeddingBackend:
        def embed(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        vector_index,
        "_load_text_embedding_backend",
        lambda model_name: _ShortEmbeddingBackend(),
    )

    with pytest.raises(VectorIndexError, match="embedding dimension mismatch"):
        search_vector_chunks(site, "Alpha", limit=2)


def test_rebuild_vector_index_reports_embedding_backend_failure(monkeypatch, tmp_path):
    source_index = tmp_path / "index" / "docs.db"
    init_db(str(source_index))

    monkeypatch.setattr(
        vector_index,
        "_load_text_embedding_backend",
        lambda model_name: (_ for _ in ()).throw(
            EmbeddingBackendUnavailableError("fastembed is not installed")
        ),
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(tmp_path / "index" / "docs.vec.db"),
        "vectorizer": {"embedding_model": "fake-fastembed-model"},
    }

    with pytest.raises(EmbeddingBackendUnavailableError, match="fastembed is not installed"):
        rebuild_vector_index(site)
