# Crawling And Indexing

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
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
python crawl_cli.py --list
```

- Crawl a site:
```bash
python crawl_cli.py --site "My Docs"
```

- Force re-authentication before crawling:
```bash
python crawl_cli.py --site "My Docs" --force-auth
```

- Run the browser headless:
```bash
python crawl_cli.py --site "My Docs" --headless
```

### Crawl Behavior
- The current crawler uses Playwright directly instead of Crawl4AI.
- It starts from `crawl.start_url`.
- It uses breadth-first traversal up to `crawl.max_depth`.
- It normalizes URLs by stripping query strings and fragments.
- It restricts crawling to the same host and the same starting path prefix.
- It skips static assets such as images, fonts, CSS, JavaScript, and archives.
- It optionally skips anchor-only links.
- It applies `allow_patterns` and `deny_patterns`.
- It waits `delay_seconds` between pages.
- It stops if it detects a redirect to a login page.

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

### Useful Behavior To Know
- A site can be crawled again after content changes without creating duplicate rows.
- If a session expires during a crawl, the crawler stops and tells you to re-authenticate.
- Anchor-heavy documentation sites remain indexed as canonical pages instead of fragment-only records.

## Edge Cases
- Static resources are filtered out before indexing so they do not pollute search results.
- If the saved session becomes invalid while crawling, the run should stop rather than continue with partial content.
- If a site uses fragment-heavy URLs, canonicalization strips the fragment before storage.

## References
- [crawl_cli.py](../crawl_cli.py)
- [src/index/store.py](../src/index/store.py)
- [requirements.txt](../requirements.txt)
