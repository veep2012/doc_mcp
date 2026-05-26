# Configuration

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-05-26
- Version: v1.6

## Change Log
- 2026-05-26 | v1.6 | Documented `crawl.start_delay_seconds` for headful crawls that need a setup window before the first request.
- 2026-05-22 | v1.5 | Documented `crawl.redirect_policy`, updated site examples, and aligned the configuration reference with the v0.1.4 crawler redirect behavior.
- 2026-05-21 | v1.4 | Documented `MCP_LOG_LEVEL`, clarified workspace `.env` resolution, and aligned runtime path notes with the loader.
- 2026-04-25 | v1.1 | Documented runtime root resolution through DOC_MCP_HOME and updated implementation references.
- 2026-04-24 | v1.0 | Reformatted the configuration reference and documented the live loader behavior.

## Purpose
Describe the local configuration files used by `doc-mcp` and the fields the runtime currently consumes.

## Scope
- In scope:
  - `.env` values available during config resolution.
  - `config/sites.yaml` site definitions and crawl settings.
- Out of scope:
  - Secrets management outside the local workspace.
  - Fields that are not consumed by the current runtime.

## Design / Behavior
### Environment Variables
- The loader resolves `${NAME}` placeholders recursively in `config/sites.yaml`.
- The loader reads `.env` from the runtime root when it exists and merges those values with the process environment for config resolution.
- `CONFIG_FILE` sets the site configuration path. Default: `config/sites.yaml`
- `DOC_MCP_HOME` sets the runtime root for relative config, session, and index paths. Default: the current working directory.
- `MCP_SERVER_NAME` sets the MCP server name. Default: `docs-mcp`
- `MCP_LOG_LEVEL` sets the server log level. Default: `INFO`
- `HTTP_PROXY` and `HTTPS_PROXY` are available to Playwright and other libraries through the process environment.
- `SITE1_USERNAME` and `SITE1_PASSWORD` can be used in site definitions.

Example:
```env
CONFIG_FILE=config/sites.yaml
DOC_MCP_HOME=/path/to/doc_mcp
MCP_SERVER_NAME=docs-mcp
SITE1_USERNAME=user@example.com
SITE1_PASSWORD=replace-me
```

### Site Configuration
`config/sites.yaml` contains a `sites` list. Each site entry should define:
- `name`: display name used by the CLI and MCP tools
- `url`: the site root or base URL
- `auth_required`: `true` or `false`
- `session_file`: where to save Playwright storage state
- `crawl.start_url`: crawl entry point
- `crawl.max_depth`: breadth-first crawl depth
- `crawl.delay_seconds`: pause between page fetches
- `crawl.start_delay_seconds`: headful-only pause before the first crawl request
- `crawl.block_images`: block image, font, and media requests
- `crawl.redirect_policy`: handle redirected pages as `final`, `requested`, or `skip`
- `crawl.ignore_query_links`: skip discovered links that contain a query string
- `crawl.ignore_anchor_links`: skip fragment-only links
- `crawl.ignore_https_errors`: ignore TLS errors for that site
- `crawl.allow_patterns`: optional allow-list glob patterns
- `crawl.deny_patterns`: optional deny-list glob patterns
- `index_file`: SQLite database path for the site index

Example:
```yaml
sites:
  - name: "My Docs"
    url: "https://docs.example.com"
    auth_required: true
    session_file: "storage/my_docs.json"
    crawl:
      start_url: "https://docs.example.com/docs"
      max_depth: 5
      delay_seconds: 1.0
      start_delay_seconds: 10.0
      block_images: true
      redirect_policy: final
      ignore_query_links: true
      ignore_anchor_links: true
      ignore_https_errors: false
      allow_patterns: []
      deny_patterns: []
    index_file: "index/my_docs.db"
```

### Notes On Example Fields
The sample config file also includes a few future-facing keys such as `auth_mode`, `auth_type`, and `respect_robots_txt`.
- `auth_mode` is currently informational only.
- `auth_type` is currently informational only.
- `respect_robots_txt` is not consumed by the current crawler implementation.
- `crawl.redirect_policy` defaults to `final`, which preserves the existing behavior of indexing the landing URL after a redirect.
- `crawl.start_delay_seconds` is off by default. Use it when you want a visible headful browser to sit on the start page for a few seconds before crawling begins.

## Edge Cases
- Unset placeholders resolve to an empty string instead of crashing.
- Workspace `.env` values are only used for config resolution; loading config does not mutate process env.
- `CONFIG_FILE` can override the default config path.
- Relative `CONFIG_FILE`, `session_file`, and `index_file` values should be interpreted from `DOC_MCP_HOME` or the process working directory.
- `crawl.start_url` is used as the initial crawl seed and is preserved exactly as configured, including any query string.
- `crawl.redirect_policy: requested` stores the original requested URL when a page redirects, while `skip` leaves redirected pages out of the index.
- `crawl.start_delay_seconds` only applies in headful mode; headless runs ignore it.
- `crawl.ignore_query_links: true` skips discovered links that contain a query string, while `false` allows them to be crawled and indexed as distinct URLs.
- Informational keys should not be treated as enforced runtime behavior.

## References
- [src/docmcp/config/loader.py](../src/docmcp/config/loader.py)
- [config/sites.yaml](../config/sites.yaml)
- [config/sites.yaml.example](../config/sites.yaml.example)
- [.env.example](../.env.example)
