# SQLite Vector Queries

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-05-24
- Last Updated: 2026-05-24
- Version: v1.0

## Change Log
- 2026-05-24 | v1.0 | Added practical sqlite3 commands for inspecting the local vector index and running nearest-neighbor queries against `chunk_embeddings`.

## Purpose
Show how to inspect the local `sqlite-vec` sidecar with `sqlite3` and run a few useful SQL queries against the vector index.

## Scope
- In scope:
  - Opening the vector database in `sqlite3`.
  - Loading the `vec0` extension.
  - Inspecting the vector tables.
  - Running nearest-neighbor and closest-pair queries.
- Out of scope:
  - Building embeddings from raw text.
  - Changing the vectorizer implementation.
  - MCP search integration.

## Design / Behavior
### Open The Vector Database
Use a `sqlite3` build that supports extension loading, such as the Homebrew shell:

```bash
sqlite3 index/<site>.vec.db
```

Inside the shell, load the extension that defines `vec0`:

```sql
.load <path-to-sqlite_vec>/vec0.dylib
```

### Inspect The Tables
List the tables in the vector database:

```sql
.tables
```

Show the schema:

```sql
SELECT name, sql
FROM sqlite_master
WHERE type IN ('table', 'view')
ORDER BY name;
```

Show build metadata:

```sql
SELECT *
FROM vector_meta;
```

### Find The 2 Nearest Chunks To A Query Vector
`chunk_embeddings` stores the vectors and `vector_chunks` stores the readable metadata. Join them through `vec_rowid`:

```sql
SELECT
  vc.chunk_id,
  vc.page_url,
  vc.title,
  vc.chunk_text,
  ce.distance
FROM chunk_embeddings AS ce
JOIN vector_chunks AS vc
  ON vc.vec_rowid = ce.rowid
WHERE ce.embedding MATCH :query
  AND k = 2
ORDER BY ce.distance;
```

Notes:
- Bind `:query` to a real vector with the same dimension as the table.
- In this repository the default dimension is `32`, unless a site overrides `vectorizer.embedding_dimensions`.
- The `distance` column is smaller for closer matches.

### Test A Query With A Literal Vector
If you just want to verify the SQL, use a literal `vec_f32(...)` value with the right dimension:

```sql
SELECT
  vc.chunk_id,
  vc.page_url,
  vc.title,
  vc.chunk_text,
  ce.distance
FROM chunk_embeddings AS ce
JOIN vector_chunks AS vc
  ON vc.vec_rowid = ce.rowid
WHERE ce.embedding MATCH vec_f32('[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]')
  AND k = 2;
```

### Find The Closest Pair In The Whole Database
To discover the two chunks that are closest to each other, compare every embedding against every other embedding. This is brute force and can be expensive on large databases:

```sql
WITH pairs AS (
  SELECT
    a.rowid AS rowid_a,
    b.rowid AS rowid_b,
    vec_distance_L2(a.embedding, b.embedding) AS distance
  FROM chunk_embeddings AS a
  JOIN chunk_embeddings AS b
    ON a.rowid < b.rowid
)
SELECT
  vc1.chunk_id AS chunk_id_1,
  vc1.page_url AS page_url_1,
  vc1.title AS title_1,
  vc2.chunk_id AS chunk_id_2,
  vc2.page_url AS page_url_2,
  vc2.title AS title_2,
  pairs.distance
FROM pairs
JOIN vector_chunks AS vc1
  ON vc1.vec_rowid = pairs.rowid_a
JOIN vector_chunks AS vc2
  ON vc2.vec_rowid = pairs.rowid_b
ORDER BY pairs.distance
LIMIT 1;
```

### Useful Filters
Filter the metadata table by site:

```sql
SELECT *
FROM vector_meta
WHERE site_name = 'Example Docs';
```

Inspect all chunks for one page:

```sql
SELECT chunk_index, chunk_text
FROM vector_chunks
WHERE page_url = 'https://example.test/guide'
ORDER BY chunk_index;
```

## Edge Cases
- If `.load` fails, confirm you are using a `sqlite3` build that supports extension loading and the `vec0.dylib` path from the active Python environment.
- If `MATCH` reports a JSON parsing error, the query vector is not valid JSON or does not have the correct number of dimensions.
- If a `k` query returns no rows, confirm the vector table was built and the query vector dimension matches the table definition.
- The brute-force closest-pair query gets expensive as the vector index grows.

## References
- [documentation/configuration.md](./configuration.md)
- [src/docmcp/vector_index.py](../src/docmcp/vector_index.py)
- [sqlite-vec KNN queries](https://alexgarcia.xyz/sqlite-vec/features/knn.html)
