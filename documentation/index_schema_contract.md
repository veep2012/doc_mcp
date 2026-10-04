# Index Schema Contract

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-10-04
- Last Updated: 2026-10-04
- Version: v1.0
- Related Tickets: veep2012/doc_mcp#83

## Change Log
- 2026-10-04 | v1.0 | Published the machine-readable keyword and vector index contract and maintenance process.

## Purpose
Explain how external tools can inspect indexes produced by `doc_mcp` without starting the MCP server or copying its schema definitions.

## Scope
- In scope: The canonical [JSON contract](../schemas/index_schema_contract.json), its version, index structures, and compatibility checks.
- Out of scope: A benchmark validator, schema migrations, or changes to search behavior.

## Design / Behavior
### Format and versioning
`schemas/index_schema_contract.json` is the canonical, UTF-8 JSON description of the indexes created by `init_db` and `rebuild_vector_index`. `contract_version` uses semantic versioning: increment the major version for breaking contract-format or index-format changes, the minor version for backward-compatible additions, and the patch version for clarifications that do not change validation. `doc_mcp_releases.compatible` identifies the release whose generated indexes are verified against this file (currently `1.1.3`). Other releases are not implicitly covered; add an explicitly verified release/range when supporting them.

The **keyword** format is unversioned: `keyword_index.schema_version` is `null`; the generated SQLite `user_version` is zero by default, not an embedded keyword schema version. The **vector** sidecar requires both SQLite `PRAGMA user_version = 2` and `vector_meta.schema_version = 2`. Older or incompatible sidecars must be rebuilt, not migrated by this contract.

### Data model
- `pages`: `id` is an autoincrement integer primary key; `url` is unique and non-null. `title`, `content_md`, and `last_crawled` are nullable text.
- `pages_fts`: an external-content FTS5 table indexing `title` and `content_md` from `pages`, using `id` as the content rowid. `pages_ai`, `pages_au`, and `pages_ad` synchronize inserts, updates, and deletes. The contract carries their SQL definitions.
- `vector_meta`: a primary-keyed row per `site_name`, containing the schema version, source path, build time, embedding model and dimensions, chunk settings and counts, and source fingerprint.
- `vector_chunks`: keyed by `chunk_id`; `vec_rowid` is unique and joins to `chunk_embeddings.rowid`. `idx_vector_chunks_page` indexes `(page_url, chunk_index)` in that order.
- `chunk_embeddings`: a sqlite-vec `vec0` virtual table with a `float` embedding column. Substitute the positive value of `vector_meta.embedding_dimensions` into its `sql_template`; **do not** assume a fixed dimension for all models. SQLite FTS5/sqlite-vec shadow tables are internal and are not listed in the contract.

### Compatibility checks
The JSON `cross_index_compatibility.checks` array lists identifiers, operands, and comparison operators (`equal`, `positive`, `all_equal`, and `same_set`). A consumer must select the configured keyword file and site, then compare the sidecar metadata to the source fingerprint, site identity and configured model, page count, positive chunk count, chunk and embedding counts, and joined rowids. `source_index_file` records the configured path at build time; match it to the selected `site.index_file` when validating a capture. These are **external validation rules**, not a claim that every rule is enforced at MCP query time.

For `source_fingerprint.sha256`, visit `pages` ordered by `url` ascending. For each page concatenate UTF-8 `url`, `title`, `content_md`, `last_crawled` separated by NUL bytes, treating nullable values as empty strings, and append another NUL byte. Hash the concatenated bytes with SHA-256 (lowercase hex). The companion timestamp is the maximum non-empty `last_crawled` string or NULL. `source_fingerprint.page_count` is the number of pages. On an empty index the hash is SHA-256 of empty bytes and the timestamp is NULL, but the harness requires non-empty fixtures for vector validation.

### Updating the contract
When index creation, fingerprinting, or compatibility rules change, update the implementation, this JSON, its release compatibility and contract version, the [scenario catalog](test_scenarios/index_schema_contract.md), and `tests/test_index_schema_contract.py` together. Generate test databases using `init_db` and `rebuild_vector_index`, run the contract tests and the repository quality gate, and verify that a deliberate mismatch still fails. Update this page and linked SQLite/MCP references when the supported format changes. Do not declare support for a release without testing the databases it produces.

## Edge Cases
- A keyword index's zero header value is not a promise of future keyword schema versioning.
- The vec0 extension must be available to query embedding rows; ordinary SQLite metadata queries alone do not validate the vectors.
- A sidecar built for a different source, site, model, or embedding dimension is incompatible even if its tables exist.

## References
- [Machine-readable index schema contract](../schemas/index_schema_contract.json)
- [SQLite vector queries](sqlite_vector_queries.md)
- [MCP server](mcp-server.md)
- [Scenario catalog](test_scenarios/index_schema_contract.md)
- [Keyword schema source](../src/docmcp/index_store.py)
- [Vector schema source](../src/docmcp/vector_index.py)
