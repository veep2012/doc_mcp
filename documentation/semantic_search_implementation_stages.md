# Semantic Search Implementation Stages

## Document Control
- Status: Draft
- Owner: Repository maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-25
- Last Updated: 2026-04-25
- Version: v0.2
- Related Tickets: https://github.com/veep2012/doc_mcp/issues/1

## Change Log
- 2026-04-25 | v0.2 | Added the staged semantic, keyword, and hybrid search plan and updated implementation references for package entry points.

## Purpose
Split the semantic search epic into implementation stages that can be delivered and validated independently while keeping the MCP server read-only and stateless.

## Scope
- In scope:
  - Staged implementation plan for best-effort search, semantic search, hybrid search, mode transparency, and graceful degradation.
  - Acceptance criteria for each implementation stage.
  - Boundaries between MCP retrieval behavior and external indexing behavior.
- Out of scope:
  - Building the external chunking, embedding, or indexing pipeline.
  - Selecting a final production vector database provider.
  - Replacing the current SQLite crawler and keyword index.

## Audience
- Repository maintainers
- Backend implementers
- QA and release reviewers

## Definitions
- MCP: The read-only Model Context Protocol server that exposes documentation retrieval tools.
- Keyword index: The existing SQLite FTS index populated by the crawler.
- Vector index: An externally managed vector store such as Chroma.
- Chunk: A searchable text segment stored in the vector index.
- Best-effort search: Search behavior that returns useful results from whatever index data is currently available.
- Hybrid search: Search behavior that combines vector and keyword results.

## Background / Context
The current MCP server exposes keyword search through `search_docs(site_name, query, limit=10)` and reads indexed documentation pages from SQLite. Issue #1 expands this into a best-effort retrieval layer that can use an external vector index when available, fall back to SQLite keyword search when needed, and expose enough metadata for callers to understand how results were produced.

The main architectural constraint is that MCP must not own indexing. Chunking, embedding generation, and vector index updates remain outside the MCP server. MCP may embed the incoming query at request time when semantic search is requested, but it should only read existing SQLite and vector index data.

## Requirements
### Functional Requirements
- FR-1: MCP must work when the vector index is absent.
- FR-2: MCP must work when the vector index is partial.
- FR-3: MCP must work when the vector index is complete.
- FR-4: MCP must fall back to SQLite keyword search when vector search cannot produce usable results.
- FR-5: MCP must not perform document chunking, document embedding generation, or index writes.
- FR-6: MCP must expose semantic search for documentation queries.
- FR-7: MCP must support hybrid search when both keyword and vector indexes are available.
- FR-8: MCP responses must identify the search mode used: `vector`, `keyword`, or `hybrid`.
- FR-9: MCP responses should include vector hit count and keyword hit count when available.

### Non-Functional Requirements
- NFR-1: Missing vector data must not crash MCP tools.
- NFR-2: Embedding service failures must degrade to keyword search when keyword search is available.
- NFR-3: Search result contracts should stay stable across keyword-only, vector-only, and hybrid modes.
- NFR-4: Partial vector indexes must not impose full-dataset availability checks.
- NFR-5: Vector integration should be optional through configuration.

## Design / Behavior
### Stage 1: Define Search Contracts
Goal: Establish the stable result schema before adding vector behavior.

Deliverables:
- Define a shared search response shape for keyword, vector, and hybrid results.
- Define result fields:
  - `text`
  - `page_url`
  - `title`
  - `score`
  - `source`
- Define response metadata fields:
  - `mode`
  - `vector_hits`
  - `keyword_hits`
- Decide whether the current `search_docs` output remains a string for MCP compatibility or becomes structured JSON.

Acceptance criteria:
- A documented schema exists for all search modes.
- Keyword search can return the new metadata without requiring a vector index.
- Existing MCP clients have a migration path if the response shape changes.

### Stage 2: Harden Keyword-Only Best-Effort Search
Goal: Make the existing SQLite path the reliable fallback for every later stage.

Deliverables:
- Normalize keyword search result formatting to match the shared schema.
- Return `mode: "keyword"` when vector search is unavailable, disabled, or not configured.
- Add safe handling for missing or empty SQLite indexes.
- Add tests for empty index, missing site, and valid keyword result cases.

Acceptance criteria:
- Keyword search succeeds without vector configuration.
- Missing vector configuration causes no errors.
- Empty keyword results return a valid response with `keyword_hits: 0`.

### Stage 3: Add Optional Vector Client Boundary
Goal: Add a read-only adapter for an external vector index without changing crawler responsibilities.

Deliverables:
- Add configuration for vector search availability and connection details.
- Add a vector client interface that can query existing chunks by site and query embedding.
- Ensure vector client initialization is optional and lazy enough that MCP can start without a vector DB.
- Keep all vector index writes out of MCP code.

Acceptance criteria:
- MCP starts successfully with no vector DB installed or configured.
- Vector client failures are caught and converted into keyword fallback.
- No chunking, document embedding generation, or vector writes are introduced in MCP.

### Stage 4: Implement Semantic Search Tool
Goal: Expose semantic retrieval when vector data and query embedding are available.

Deliverables:
- Add `semantic_search_docs(query: str, limit: int)` or a site-scoped equivalent if site isolation is required by the existing tool model.
- Embed the incoming query at request time.
- Query the external vector index for top-K chunks.
- Return text, page URL, title, and similarity score for each result.
- Return `mode: "vector"` when only vector results are used.

Acceptance criteria:
- Semantic search returns top-K similar chunks from existing vector data.
- Semantic search handles partial vector indexes by querying only available chunks.
- Embedding failure returns a valid fallback response when keyword search can be used.
- Missing vector DB does not crash the MCP server.

### Stage 5: Implement Hybrid Search
Goal: Combine semantic and keyword results when both indexes can answer the query.

Deliverables:
- Add hybrid search behavior to `search_docs` or a dedicated `hybrid_search_docs` tool.
- Query vector and keyword sources independently.
- Merge results using a simple documented ranking strategy.
- Deduplicate results by stable keys such as page URL plus chunk identity or normalized text.
- Fall back to keyword mode when vector results are empty or unavailable.

Acceptance criteria:
- When both indexes return results, response metadata reports `mode: "hybrid"`.
- When vector returns no results, response metadata reports `mode: "keyword"`.
- Duplicate results are not returned to callers.
- Ranking behavior is deterministic and documented.

### Stage 6: Add Observability And Degradation Tests
Goal: Prove the system behaves correctly across missing, partial, and failing dependencies.

Deliverables:
- Add tests for:
  - No vector index.
  - Partial vector index.
  - Full vector index.
  - Vector DB unavailable.
  - Embedding provider failure.
  - Empty vector results with keyword fallback.
- Add structured logging for selected search mode and fallback reason.
- Add manual verification steps for local keyword-only and vector-enabled runs.

Acceptance criteria:
- Test coverage demonstrates graceful degradation for all issue #1 failure modes.
- Logs identify whether a query used keyword, vector, or hybrid mode.
- No test requires a fully indexed dataset unless it is specifically testing the full-index case.

### Stage 7: Documentation And Release Readiness
Goal: Make the feature understandable and safe to operate.

Deliverables:
- Update MCP server documentation with new tools and response schemas.
- Update configuration documentation with optional vector settings.
- Update operations and troubleshooting docs with fallback behavior.
- Document external indexing assumptions and the read-only MCP boundary.

Acceptance criteria:
- Users can tell which components are required for keyword-only, vector, and hybrid modes.
- Operators can diagnose why a query fell back to keyword mode.
- Documentation states that MCP uses existing data and does not create vector index data.

### Suggested Delivery Order
1. Stage 1: Define Search Contracts
2. Stage 2: Harden Keyword-Only Best-Effort Search
3. Stage 3: Add Optional Vector Client Boundary
4. Stage 4: Implement Semantic Search Tool
5. Stage 5: Implement Hybrid Search
6. Stage 6: Add Observability And Degradation Tests
7. Stage 7: Documentation And Release Readiness

## API Contract
### Search Response
```json
{
  "mode": "keyword",
  "vector_hits": 0,
  "keyword_hits": 2,
  "results": [
    {
      "text": "Result snippet or chunk text",
      "page_url": "https://docs.example.com/page",
      "title": "Page title",
      "score": 0.87,
      "source": "keyword"
    }
  ]
}
```

### Semantic Search Tool
```python
semantic_search_docs(query: str, limit: int)
```

If site isolation remains required by the current configuration model, use:

```python
semantic_search_docs(site_name: str, query: str, limit: int)
```

## Edge Cases
- No vector DB configured: return keyword results with `mode: "keyword"`.
- Vector DB unavailable: log the fallback reason and return keyword results if possible.
- Embedding provider failure: log the fallback reason and return keyword results if possible.
- Empty SQLite index and no vector index: return an empty result set without crashing.
- Partial vector index: query only available chunks and do not require full crawl coverage.
- Duplicate keyword and vector hits: keep one result and preserve the best available score or merged rank.
- Score scale mismatch: normalize or rank within each source before merging hybrid results.

## Testing Strategy
- Unit tests:
  - Search response schema serialization.
  - Keyword fallback decisions.
  - Vector client error handling.
  - Hybrid merge and deduplication behavior.
- Integration tests:
  - Keyword-only MCP search against SQLite.
  - Vector-enabled search against a test vector adapter or fixture.
  - Hybrid search with overlapping keyword and vector results.
- Manual verification:
  - Start MCP with no vector config and run keyword search.
  - Start MCP with vector config and run semantic search.
  - Stop or misconfigure vector DB and verify keyword fallback.

## Rollout / Migration
- Keep keyword search as the first stable fallback before exposing vector features.
- Introduce vector configuration as optional and disabled by default until local verification is reliable.
- Preserve existing `search_docs` behavior or document any response shape migration before release.
- Update user-facing docs in the same change that exposes new MCP tools.

## Risks and Mitigations
- Risk: MCP becomes coupled to a specific indexing pipeline.
  - Mitigation: Depend on a read-only vector client interface and document the external indexing boundary.
- Risk: Hybrid ranking produces confusing result order.
  - Mitigation: Start with a simple deterministic merge and record the ranking strategy in documentation.
- Risk: Semantic search requires a site scope but the issue proposes a global function signature.
  - Mitigation: Align the final tool signature with the repository's existing `site_name` configuration model.
- Risk: Structured responses may break clients expecting string output.
  - Mitigation: Add a compatibility plan before changing existing tool output.

## Open Questions
- Should semantic search be global, or should it require `site_name` like the existing MCP tools?
- Which embedding provider should be used for query embeddings?
- Which vector database should be supported first?
- Should hybrid search replace `search_docs` or be exposed as a separate tool?
- What stable chunk identifier should be used for deduplication?

## References
- [Issue #1: Epic: Semantic Search over External Vector Index](https://github.com/veep2012/doc_mcp/issues/1)
- [documentation/mcp-server.md](./mcp-server.md)
- [documentation/crawling.md](./crawling.md)
- [src/docmcp/tools.py](../src/docmcp/tools.py)
- [src/docmcp/index_store.py](../src/docmcp/index_store.py)
