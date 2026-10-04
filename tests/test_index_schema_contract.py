"""TS-ISC-001..005: documentation/test_scenarios/index_schema_contract.md."""

import copy
import hashlib
import json
import re
import sqlite3
import tomllib
from pathlib import Path

import pytest

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import (
    DEFAULT_EMBEDDING_MODEL,
    _normalize_embedding_model,
    rebuild_vector_index,
    vector_backend_status,
)

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "schemas/index_schema_contract.json"
SCENARIOS = (
    Path(__file__).resolve().parents[1] / "documentation/test_scenarios/index_schema_contract.md"
)


@pytest.fixture
def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def keyword_index(tmp_path):
    path = tmp_path / "docs.db"
    init_db(str(path))
    return path


@pytest.fixture(params=["explicit", "omitted", "padded"])
def generated_indexes(keyword_index, tmp_path, request):
    available, reason = vector_backend_status()
    if not available or sqlite_vec is None:
        pytest.skip(reason)
    upsert_page(str(keyword_index), "https://example.test/guide", "Guide", "Alpha beta gamma")
    vectorizer = {"chunk_size": 18, "chunk_overlap": 5}
    if request.param != "omitted":
        vectorizer["embedding_model"] = (
            " fake-fastembed-model " if request.param == "padded" else "fake-fastembed-model"
        )
    site = {
        "name": "Example Docs",
        "index_file": str(keyword_index),
        "vector_index_file": str(tmp_path / "docs.vec.db"),
        "vectorizer": vectorizer,
    }
    rebuild_vector_index(site)
    return keyword_index, Path(site["vector_index_file"]), site


def _declared_sql_objects(conn, object_type):
    return {
        name: _normalized_sql(sql)
        for name, sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = ? AND sql IS NOT NULL",
            (object_type,),
        )
    }


def _declared_columns(conn, table):
    return {
        name: {
            "name": name,
            "type": (kind or "").upper(),
            "not_null": bool(not_null),
            "primary_key": primary_key,
        }
        for _, name, kind, not_null, _, primary_key in conn.execute(f"PRAGMA table_info({table})")
        if name != "rowid"
    }


def _declared_column_names(conn, table):
    return {name for _, name, *_ in conn.execute(f"PRAGMA table_info({table})") if name != "rowid"}


def _verify_public_tables(conn, expected_names):
    actual_names = {
        name
        for _, name, table_type, *_ in conn.execute("PRAGMA table_list")
        if table_type != "shadow" and not name.startswith("sqlite_")
    }
    assert actual_names == set(expected_names)


def _verify_indexes(conn, indexes):
    actual_indexes = dict(
        conn.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
        )
    )
    for name, definition in indexes.items():
        assert actual_indexes.get(name) == definition["table"]
        index_list = conn.execute(f"PRAGMA index_list({definition['table']})")
        index_info = next(
            (row for row in index_list if row[1] == name),
            None,
        )
        assert index_info is not None
        assert bool(index_info[2]) == definition["unique"]
        actual_columns = [row[2] for row in conn.execute(f"PRAGMA index_info({name})")]
        assert actual_columns == definition["columns"]


def _verify_table_definitions(conn, tables):
    actual_sql = _declared_sql_objects(conn, "table")
    for name, definition in tables.items():
        assert name in actual_sql
        actual_columns = _declared_columns(conn, name)
        expected_columns = {
            column["name"]: {**column, "type": column["type"].upper()}
            for column in definition["columns"]
        }
        assert actual_columns == expected_columns
        unique_indexes = {
            tuple(row[2] for row in conn.execute(f"PRAGMA index_info({index_name})"))
            for _, index_name, is_unique, *_ in conn.execute(f"PRAGMA index_list({name})")
            if is_unique
        }
        assert unique_indexes == {tuple(columns) for columns in definition.get("unique", [])}
        if "autoincrement" in definition:
            ddl = actual_sql[name]
            assert re.search(
                rf"\b{definition['autoincrement']}\s+INTEGER PRIMARY KEY AUTOINCREMENT\b",
                ddl,
                re.IGNORECASE,
            )


def _verify_tables(conn, tables):
    _verify_table_definitions(conn, tables)


def _normalized_sql(value):
    return " ".join(
        re.sub(
            r"\s*([()])\s*",
            r"\1",
            re.sub(r"\bIF NOT EXISTS\s+", "", value, flags=re.IGNORECASE),
        ).split()
    ).lower()


def _verify_sql_objects(conn, object_type, definitions):
    actual = _declared_sql_objects(conn, object_type)
    for name, definition in definitions.items():
        assert actual.get(name) == _normalized_sql(definition["sql"]), name


def _verify_trigger_objects(conn, triggers):
    actual_sql = _declared_sql_objects(conn, "trigger")
    actual_targets = dict(
        conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type = 'trigger'")
    )
    expected_targets = {
        name: definition["event"].rsplit(" ON ", 1)[1] for name, definition in triggers.items()
    }
    assert set(actual_sql) == set(triggers)
    assert actual_targets == expected_targets
    _verify_sql_objects(conn, "trigger", triggers)


def test_contract_identity(contract):
    """TS-ISC-001: contract identity and bidirectional scenario mapping."""
    assert contract["contract_name"] == "doc_mcp_index_schema"
    assert re.fullmatch(r"\d+\.\d+\.\d+", contract["contract_version"])
    package = tomllib.loads(
        (CONTRACT_PATH.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    schema_source = contract["schema_source"]
    assert schema_source["artifact_type"] == "SQLite keyword index and vector sidecar"
    assert schema_source["producer"] == "doc_mcp"
    assert schema_source["producer_version_field"] == "doc_mcp_releases.compatible"
    producer_version_section, producer_version_key = schema_source["producer_version_field"].split(
        ".", 1
    )
    assert contract[producer_version_section][producer_version_key] == package["project"]["version"]
    assert contract["keyword_index"]["schema_version"] is None
    scenario_text = SCENARIOS.read_text(encoding="utf-8")
    for number, entrypoint in enumerate(
        (
            "test_contract_identity",
            "test_keyword_schema_matches_contract",
            "test_vector_schema_matches_contract",
            "test_cross_index_checks_match_contract",
            "test_contract_drift_is_detected",
        ),
        1,
    ):
        assert f"TS-ISC-{number:03d}" in scenario_text
        assert f"tests/test_index_schema_contract.py::{entrypoint}" in scenario_text


def test_keyword_schema_matches_contract(contract, keyword_index):
    """TS-ISC-002: compare keyword schema with an init_db fixture."""
    spec = contract["keyword_index"]
    with sqlite3.connect(keyword_index) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == spec["sqlite_user_version"]
        _verify_tables(conn, spec["tables"])
        _verify_public_tables(conn, set(spec["tables"]) | set(spec["virtual_tables"]))
        for definition in spec["virtual_tables"].values():
            expected = (
                f"CREATE VIRTUAL TABLE pages_fts USING {definition['module']}"
                f"({', '.join(definition['columns'])}, "
                f"content='{definition['options']['content']}', "
                f"content_rowid='{definition['options']['content_rowid']}')"
            )
            assert _normalized_sql(definition["sql"]) == _normalized_sql(expected)
        _verify_sql_objects(conn, "table", spec["virtual_tables"])
        _verify_trigger_objects(conn, spec["triggers"])

        conn.execute(
            "INSERT INTO pages(url, title, content_md) VALUES (?, ?, ?)",
            ("https://example.test/fts", "Trigger test", "insertneedle originalword"),
        )
        page_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        assert conn.execute(
            "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'insertneedle'"
        ).fetchone() == (page_id,)
        conn.execute(
            "UPDATE pages SET title = ?, content_md = ? WHERE id = ?",
            ("Updated trigger test", "replacementneedle", page_id),
        )
        assert (
            conn.execute(
                "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'insertneedle'"
            ).fetchone()
            is None
        )
        assert conn.execute(
            "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'replacementneedle'"
        ).fetchone() == (page_id,)
        conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        assert (
            conn.execute(
                "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'replacementneedle'"
            ).fetchone()
            is None
        )


def test_vector_schema_matches_contract(contract, generated_indexes):
    """TS-ISC-003: compare sidecar schema and dynamic dimension with a rebuild fixture."""
    _, vector_path, site = generated_indexes
    spec = contract["vector_sidecar"]
    with sqlite3.connect(vector_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == spec["sqlite_user_version"]
        _verify_tables(conn, spec["tables"])
        meta = conn.execute(
            "SELECT schema_version, embedding_dimensions FROM vector_meta WHERE site_name = ?",
            (site["name"],),
        ).fetchone()
        assert meta[0] == spec["metadata_schema_version"]
        assert spec["metadata_version_field"] == "vector_meta.schema_version"
        _verify_indexes(conn, spec["indexes"])
        vec = spec["virtual_tables"]["chunk_embeddings"]
        assert _declared_column_names(conn, "chunk_embeddings") == set(vec["columns"])
        assert vec["dimensions_from"] == "vector_meta.embedding_dimensions"
        assert meta[1] > 0
        expected = vec["sql_template"].format(embedding_dimensions=meta[1])
        assert _normalized_sql(expected) == _normalized_sql(
            f"CREATE VIRTUAL TABLE chunk_embeddings USING {vec['module']}"
            f"({vec['columns'][0]} {vec['embedding_type']}[{meta[1]}])"
        )
        _verify_sql_objects(conn, "table", {"chunk_embeddings": {"sql": expected}})


def _source_fingerprint(conn):
    digest = hashlib.sha256()
    rows = conn.execute(
        "SELECT url, title, content_md, last_crawled FROM pages ORDER BY url"
    ).fetchall()
    for url, title, content, crawled in rows:
        digest.update("\0".join((url, title or "", content or "", crawled or "")).encode("utf-8"))
        digest.update(b"\0")
    return {
        "page_count": len(rows),
        "source_max_last_crawled": max((r[3] for r in rows if r[3]), default=None),
        "sha256": digest.hexdigest(),
    }


def test_cross_index_checks_match_contract(contract, generated_indexes):
    """TS-ISC-004: evaluate every declared compatibility rule against both indexes."""
    keyword_path, vector_path, site = generated_indexes
    compatibility = contract["cross_index_compatibility"]
    model_rule = compatibility["effective_embedding_model"]
    assert model_rule["source"] == "site.vectorizer.embedding_model"
    assert model_rule["default"] == DEFAULT_EMBEDDING_MODEL
    assert model_rule["use_default_when"] == ["missing", "null", "empty_string"]
    assert model_rule["trim_whitespace"] is True
    assert model_rule["normalization_steps"] == [
        {
            "step": 1,
            "condition": "input_is_missing_null_or_empty_string",
            "action": "return_default",
        },
        {
            "step": 2,
            "condition": "input_is_string",
            "action": "trim_leading_and_trailing_whitespace",
        },
        {
            "step": 3,
            "condition": "trimmed_string_is_non_empty",
            "action": "return_trimmed_string",
        },
        {
            "step": 4,
            "condition": "no_prior_step_returned",
            "action": "reject",
        },
    ]
    assert model_rule["reject_when"] == ["non_string", "whitespace_only"]

    def resolve_model_from_contract(value, *, missing=False):
        if missing or value is None or value == "":
            return model_rule["default"]
        if not isinstance(value, str):
            raise ValueError("embedding model must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("embedding model must not be whitespace-only")
        return normalized

    contract_cases = [
        ("omitted", None, True),
        ("null", None, False),
        ("empty", "", False),
        ("padded", " fake-fastembed-model ", False),
    ]
    for label, value, missing in contract_cases:
        expected = resolve_model_from_contract(value, missing=missing)
        actual_input = None if missing else value
        assert expected == _normalize_embedding_model(actual_input), label
    with pytest.raises(ValueError):
        resolve_model_from_contract("   ")
    with pytest.raises(ValueError):
        _normalize_embedding_model("   ")
    with pytest.raises(ValueError):
        resolve_model_from_contract(123)
    with pytest.raises(ValueError):
        _normalize_embedding_model(123)

    configured_model = site["vectorizer"].get("embedding_model")
    effective_model = (
        model_rule["default"]
        if configured_model is None or configured_model == ""
        else configured_model.strip()
    )
    fingerprint_spec = compatibility["source_fingerprint"]
    assert fingerprint_spec == {
        "pages_order": "url ASC",
        "fields": ["url", "title", "content_md", "last_crawled"],
        "null_handling": "Treat NULL title, content_md, and last_crawled as empty strings",
        "encoding": "UTF-8",
        "field_separator": "U+0000",
        "record_terminator": "U+0000",
        "hash": "SHA-256 lowercase hex",
        "source_max_last_crawled": "Maximum non-empty last_crawled value, or NULL",
    }
    with sqlite3.connect(keyword_path) as keyword, sqlite3.connect(vector_path) as vector:
        vector.enable_load_extension(True)
        sqlite_vec.load(vector)
        vector.enable_load_extension(False)
        vector.row_factory = sqlite3.Row
        meta = dict(
            vector.execute(
                "SELECT * FROM vector_meta WHERE site_name = ?", (site["name"],)
            ).fetchone()
        )
        values = {
            "vector_meta": meta,
            "source_fingerprint": _source_fingerprint(keyword),
            "site": {
                "index_file": site["index_file"],
                "name": site["name"],
                "effective_embedding_model": effective_model,
            },
            "vector_chunks": {
                "count": vector.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0],
                "site_name": [
                    row[0] for row in vector.execute("SELECT site_name FROM vector_chunks")
                ],
                "vec_rowid": {
                    row[0] for row in vector.execute("SELECT vec_rowid FROM vector_chunks")
                },
            },
            "chunk_embeddings": {
                "count": vector.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0],
                "rowid": {row[0] for row in vector.execute("SELECT rowid FROM chunk_embeddings")},
            },
        }

        def resolve(path):
            value = values
            for key in path.split("."):
                value = value[key]
            return value

        checks = compatibility["checks"]
        assert len(checks) == 12
        assert len({rule["id"] for rule in checks}) == len(checks)
        for rule in checks:
            left = resolve(rule["left"])
            if rule["operator"] in ("equal", "same_set"):
                assert left == resolve(rule["right"]), rule["id"]
            elif rule["operator"] == "positive":
                assert left > 0, rule["id"]
            elif rule["operator"] == "all_equal":
                assert left and all(item == resolve(rule["right"]) for item in left), rule["id"]
            else:
                pytest.fail(f"Unknown compatibility operation: {rule['operator']}")


def test_contract_drift_is_detected(contract, keyword_index):
    """TS-ISC-005: a deliberate contract mutation fails the shared comparison."""
    changed = copy.deepcopy(contract["keyword_index"]["tables"])
    changed["pages"]["columns"][1]["type"] = "INTEGER"
    with sqlite3.connect(keyword_index) as conn, pytest.raises(AssertionError):
        _verify_tables(conn, changed)
