# Index Schema Contract Test Scenarios

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-10-04
- Last Updated: 2026-10-04
- Version: v1.0
- Related Tickets: veep2012/doc_mcp#83

## Change Log
- 2026-10-04 | v1.0 | Defined generated-index contract verification and mismatch regression scenarios; clarified that implicit vec0 rowid metadata is excluded from declared-column comparison.

## Purpose
Define the verification required to keep the published index schema contract aligned with generated SQLite files.

## Scope
- In scope: JSON identity, keyword and vector schema, cross-index compatibility, and mismatch detection.
- Out of scope: Implementing a benchmark index validator or changing either database format.

## Design / Behavior
### TS-ISC-001: Contract identity
- Preconditions: `schemas/index_schema_contract.json` exists.
- Action: Parse the JSON.
- Expected result: It identifies its contract version and compatible `doc_mcp` release, and explicitly marks the keyword format as unversioned.

### TS-ISC-002: Keyword index
- Preconditions: A temporary keyword index is created with `init_db`.
- Action: Inspect SQLite table and column metadata, FTS5 configuration, indexes, and trigger definitions.
- Expected result: The generated `pages` table, `pages_fts`, uniqueness and synchronization triggers agree with the contract; the keyword header version is zero.
- Cleanup: Remove the temporary index.

### TS-ISC-003: Vector sidecar
- Preconditions: A populated keyword index and a sidecar built using `rebuild_vector_index` with the fake test embedding backend.
- Action: Inspect header and metadata versions, tables and columns, index, vec0 definition, and the dimensions from metadata.
- Expected result: Both schema versions, required columns, index order, and vec0 embedding dimension agree with the contract; dimension is derived from `vector_meta.embedding_dimensions` rather than a fixed model constant.
- Cleanup: Remove the temporary indexes.

### TS-ISC-004: Cross-index compatibility
- Preconditions: The same populated index and sidecar.
- Action: Evaluate the contract's source fingerprint, site identity, model, page count, and vector record consistency rules against generated files with an explicit model, an omitted model, and a model padded with whitespace.
- Expected result: Each rule resolves to actual fixture values and passes, including a positive chunk and embedding count. The model check uses the declared default for an omitted value and trims configured whitespace.
- Cleanup: Remove the temporary indexes.

### TS-ISC-005: Contract drift detection
- Preconditions: A generated keyword index and a parsed copy of the contract.
- Action: Deliberately change one declared column type in the copy and run the same schema comparison.
- Expected result: Verification fails rather than silently accepting the changed contract.
- Cleanup: Remove the temporary index.

### Automated Test Mapping
| Scenario | Automated verification |
| --- | --- |
| TS-ISC-001 | `tests/test_index_schema_contract.py::test_contract_identity` |
| TS-ISC-002 | `tests/test_index_schema_contract.py::test_keyword_schema_matches_contract` |
| TS-ISC-003 | `tests/test_index_schema_contract.py::test_vector_schema_matches_contract` |
| TS-ISC-004 | `tests/test_index_schema_contract.py::test_cross_index_checks_match_contract` |
| TS-ISC-005 | `tests/test_index_schema_contract.py::test_contract_drift_is_detected` |

## Edge Cases
- The fake embedding backend uses a test-specific dimension; verifiers must not assume a production model's dimension.
- `PRAGMA table_info(chunk_embeddings)` may expose sqlite-vec's implicit `rowid`; compare declared embedding columns separately while still requiring the rowid used by `vector_chunks.vec_rowid`.
- SQLite and sqlite-vec create internal shadow tables; compare only declared public objects.

## References
- [Index schema contract](../index_schema_contract.md)
- [Keyword implementation](../../src/docmcp/index_store.py)
- [Vector implementation](../../src/docmcp/vector_index.py)
