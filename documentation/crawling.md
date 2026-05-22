# Crawling And Indexing

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-05-22
- Version: v1.7

## Change Log
- 2026-05-22 | v1.7 | Documented `crawl.redirect_policy`, expanded redirect diagnostics, and aligned the crawl behavior guide with the v0.1.4 release.
- 2026-05-21 | v1.6 | Tightened query-link wording so start URLs are preserved exactly and discovered query links are described consistently.
- 2026-05-20 | v1.4 | Clarified debug output routing, queue preview formatting, redirected URL indexing, and crawler trace expectations.
- 2026-04-25 | v1.1 | Updated commands and references for installed docmcp-crawl package entry point and moved index store.
- 2026-04-24 | v1.0 | Reformatted the crawl guide and documented the current Playwright and SQLite flow.

## Purpose
Describe how the crawler walks a site, extracts Markdown content, and stores the resulting pages in SQLite for MCP search and fetch operations.

## Scope
- In scope:
  - Crawl execution and filtering rules.
  - Markdown extraction and indexing behavior.
- Out of scope:
  - Authentication setup details.
  - MCP client configuration.

## Design / Behavior
### Commands
- List configured sites:
```bash
docmcp-crawl --list
```

- Crawl a site:
```bash
docmcp-crawl --site "My Docs"
```

- Force re-authentication before crawling:
```bash
docmcp-crawl --site "My Docs" --force-auth
```

- Run the browser headless:
```bash
docmcp-crawl --site "My Docs" --headless
```

- Run the crawler with detailed diagnostics:
```bash
docmcp-crawl --site "My Docs" --debug
```

- Show the current crawler version:
```bash
docmcp-crawl --version
```

### Crawl Behavior
- The current crawler uses Playwright directly instead of Crawl4AI.
- If `auth_required` is true for the site, the crawl command authenticates before crawling and reuses any still-valid saved session.
- It starts from `crawl.start_url` and preserves that URL exactly as configured, including any query string.
- It uses breadth-first traversal up to `crawl.max_depth`.
- It normalizes URLs by stripping fragments.
- It skips discovered links that contain a query string when `crawl.ignore_query_links` is `true`.
- It crawls and indexes discovered query links as distinct URLs when `crawl.ignore_query_links` is `false`.
- It restricts crawling to the same host and the same starting path prefix.
- It skips static assets such as images, fonts, CSS, JavaScript, and archives.
- It optionally skips discovered query links and anchor-only links independently.
- It applies `allow_patterns` and `deny_patterns`.
- It waits `delay_seconds` between pages.
- It stops if it detects a redirect to a login page.
- It applies `crawl.redirect_policy` when navigation lands on a different URL than the one that was requested.
- `crawl.redirect_policy: final` indexes the final normalized landing URL and preserves the current default behavior.
- `crawl.redirect_policy: requested` stores the original requested URL in the index while still crawling the landing page content.
- `crawl.redirect_policy: skip` skips indexing redirected pages but continues normal handling for pages that do not redirect.

### Content Extraction
- The crawler attempts to extract the most complete rendered HTML it can find.
- It prefers full page HTML from `page.content()`.
- It then checks `main`, `article`, `[role="main"]`, `#content`, `.content`, and `body`.
- The largest candidate is converted to Markdown with `markdownify` when available.
- If `markdownify` is missing, the crawler falls back to plain text extraction.

### Indexing
- The SQLite index stores page URL, page title, Markdown content, and last crawled timestamp.
- The database also includes SQLite FTS5 tables for full-text keyword search.
- Repeated crawls update existing rows by URL, so re-running the crawler refreshes pages in place.

### Runtime Outputs
- Session file: `storage/<site>.json`
- SQLite index: `index/<site>.db`
- Normal runs keep the existing progress output focused on page indexing progress.
- `--debug` adds crawler-only trace lines for navigation, redirect-policy decisions, extracted content sizes, discovered links, skip reasons, queued URLs, and the next breadth-first queue preview before the crawler descends to the next level.
- Debug traces are written to `stderr`, which keeps them separate from the normal crawl progress stream.
- Queue previews summarize the next depth, show up to five URLs, and explicitly mark an empty next queue.

### Useful Behavior To Know
- A site can be crawled again after content changes without creating duplicate rows.
- If a session expires during a crawl, the crawler stops and tells you to re-authenticate.
- Anchor-heavy documentation sites remain indexed as canonical pages instead of fragment-only records.
- Query-driven documentation can opt into separate records for distinct query URLs by setting `crawl.ignore_query_links: false`.
- Redirected navigation defaults to indexing the final page URL, but `crawl.redirect_policy` can preserve the requested URL or skip redirected pages entirely in v0.1.4.

## Edge Cases
- Static resources are filtered out before indexing so they do not pollute search results.
- If the saved session becomes invalid while crawling, the run should stop rather than continue with partial content.
- If a site uses fragment-heavy URLs, canonicalization strips the fragment before storage.
- If a site needs query-based pages, `crawl.ignore_query_links` must be set to `false`; otherwise discovered query links are skipped while the configured `crawl.start_url` keeps its query string exactly as configured.
- If redirect behavior is surprising, check the debug trace for both the requested URL, the normalized landing URL, and the redirect policy line that was applied.

## References
- [crawl_cli.py](../crawl_cli.py)
- [src/docmcp/crawl_cli.py](../src/docmcp/crawl_cli.py)
- [src/docmcp/index_store.py](../src/docmcp/index_store.py)
- [requirements.txt](../requirements.txt)
