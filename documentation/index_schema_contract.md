# Index Schema Contract

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-10-04
- Last Updated: 2026-10-04
- Version: v1.4
- Related Tickets: veep2012/doc_mcp#83

## Change Log
- 2026-10-04 | v1.4 | Corrected the compatible `doc_mcp` release to 1.1.4, incremented the contract patch version, documented ordered embedding-model normalization and provenance, separated consumer requirements from repository verification, and added a validation checklist.

## Purpose
Explain how external tools can inspect indexes produced by `doc_mcp` without starting the MCP server or copying its schema definitions.

## Scope
- In scope: The canonical [JSON contract](../schemas/index_schema_contract.json), its version, index structures, and compatibility checks.
- Out of scope: A benchmark validator, schema migrations, or changes to search behavior.

## Design / Behavior
### Consumer contract
The JSON contract is the normative source for external consumers. The rules in this section explain guarantees consumers can rely on. Repository implementation details and test procedures below provide conformance evidence; they do not add requirements beyond the JSON contract.

#### Format and versioning
`schemas/index_schema_contract.json` is the canonical, UTF-8 JSON description of the indexes created by `init_db` and `rebuild_vector_index`. `contract_version` versions the contract itself; it follows semantic versioning, where a major version denotes breaking contract-format or index-format changes, a minor version denotes backward-compatible additions, and a patch version denotes clarifications that do not change validation. The current contract version is `1.0.4`. The top-level `schema_source` identifies the described artifact and producer, and `producer_version_field` points to the package version field. `doc_mcp_releases.compatible` identifies the `doc_mcp` release whose generated indexes this contract covers; that release is currently `1.1.4`.

The **keyword** format is unversioned: `keyword_index.schema_version` is `null`; the generated SQLite `user_version` is zero by default, not an embedded keyword schema version. The **vector** sidecar requires both SQLite `PRAGMA user_version = 2` and `vector_meta.schema_version = 2`. Older or incompatible sidecars must be rebuilt, not migrated by this contract.

#### Consumer checklist
Apply these checks in order before accepting an index:

1. **Contract applicability:** Read `contract_name`, `contract_version`, and `schema_source.producer`. Resolve `schema_source.producer_version_field` (`doc_mcp_releases.compatible`) to identify the producer release covered; `contract_version` versions the contract, not the package.
2. **Keyword index:** Compare `PRAGMA user_version` with `keyword_index.sqlite_user_version`. Treat `keyword_index.schema_version: null` as explicitly unversioned. Then validate declared tables, `keyword_index.virtual_tables`, and `keyword_index.triggers` against the JSON.
3. **Vector sidecar:** Compare its `PRAGMA user_version` with `vector_sidecar.sqlite_user_version`. Select the `vector_meta` row for `site.name`; resolve `vector_sidecar.metadata_version_field` (`vector_meta.schema_version`) and compare it with `vector_sidecar.metadata_schema_version`. Verify `vector_meta.site_name` matches `site.name`, require positive `vector_meta.embedding_dimensions`, and use that value for `vector_sidecar.virtual_tables.chunk_embeddings.sql_template`.
4. **Cross-index compatibility:** Evaluate every rule in `cross_index_compatibility.checks` for the selected keyword index and site, including the source fingerprint and effective embedding model.

#### Data model
- `pages`: `id` is an autoincrement integer primary key; `url` is unique and non-null. `title`, `content_md`, and `last_crawled` are nullable text.
- `pages_fts`: an external-content FTS5 table indexing `title` and `content_md` from `pages`, using `id` as the content rowid. `pages_ai`, `pages_au`, and `pages_ad` synchronize inserts, updates, and deletes. The contract carries their SQL definitions.
- `vector_meta`: a primary-keyed row per `site_name`, containing the schema version, source path, build time, embedding model and dimensions, chunk settings and counts, and source fingerprint.
- `vector_chunks`: keyed by `chunk_id`; `vec_rowid` is unique and joins to `chunk_embeddings.rowid`. `idx_vector_chunks_page` indexes `(page_url, chunk_index)` in that order.
- `chunk_embeddings`: a sqlite-vec `vec0` virtual table with a `float` embedding column. Substitute the positive value of `vector_meta.embedding_dimensions` into its `sql_template`; **do not** assume a fixed dimension for all models. SQLite FTS5/sqlite-vec shadow tables are internal and are not listed in the contract.

#### Compatibility checks
The JSON `cross_index_compatibility.checks` array lists identifiers, operands, and comparison operators (`equal`, `positive`, `all_equal`, and `same_set`). A consumer must select the configured keyword file and site, then compare the sidecar metadata to the source fingerprint, site identity and effective model, page count, positive chunk count, chunk and embedding counts, and joined rowids. `effective_embedding_model.normalization_steps` is normative and must be applied in ascending `step` order. Missing, null, or exactly empty input returns the default immediately. Other strings are trimmed; a non-empty trimmed value is returned. If no step returns a value, the input is rejected. Thus whitespace-only strings and non-string values are invalid and must not resolve to the default. `source_index_file` records the configured path at build time; match it to the selected `site.index_file` when validating a capture. These are **external validation rules**, not a claim that every rule is enforced at MCP query time.

The `source_fingerprint.sha256` rule visits `pages` ordered by `url` ascending. For each page, concatenate UTF-8 `url`, `title`, `content_md`, and `last_crawled` separated by NUL bytes, treating nullable values as empty strings, then append another NUL byte. Hash the concatenated bytes with SHA-256 (lowercase hex). The companion timestamp is the maximum non-empty `last_crawled` string or NULL. `source_fingerprint.page_count` is the number of pages. An empty index has the SHA-256 of empty bytes and a NULL timestamp; consumers should apply the compatibility rules to the data they validate.

### Repository verification and maintenance
This section describes this repository's current validation workflow. It may change as implementation or test tooling changes; external consumers should follow the JSON contract and do not need to reproduce these repository checks.

#### Updating the contract
When index creation, fingerprinting, or compatibility rules change, update the implementation, this JSON, its release compatibility and contract version, the [scenario catalog](test_scenarios/index_schema_contract.md), and `tests/test_index_schema_contract.py` together. Apply semantic-versioning rules to `contract_version`; declare compatibility for another release only after testing the indexes it produces. Generate test databases using `init_db` and `rebuild_vector_index`, run the contract tests and the repository quality gate, and verify that a deliberate mismatch still fails. Update this page and linked SQLite/MCP references when the supported format changes.

## Edge Cases
- A keyword index's zero header value is not a promise of future keyword schema versioning.
- The vec0 extension must be available to query embedding rows; ordinary SQLite metadata queries alone do not validate the vectors.
- A sidecar built for a different source, site, model, or embedding dimension is incompatible even if its tables exist.

## References
- [Machine-readable index schema contract](../schemas/index_schema_contract.json)
- [SQLite vector queries](sqlite_vector_queries.md)
- [MCP server](mcp-server.md)
- Repository verification: [scenario catalog](test_scenarios/index_schema_contract.md), [keyword schema source](../src/docmcp/index_store.py), and [vector schema source](../src/docmcp/vector_index.py)
