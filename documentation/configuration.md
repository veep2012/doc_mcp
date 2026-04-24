# Configuration

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
- 2026-04-24 | v1.0 | Reformatted the configuration reference and documented the live loader behavior.

## Purpose
Describe the local configuration files used by `doc-mcp` and the fields the runtime currently consumes.

## Scope
- In scope:
  - `.env` values loaded into the process environment.
  - `config/sites.yaml` site definitions and crawl settings.
- Out of scope:
  - Secrets management outside the local workspace.
  - Fields that are not consumed by the current runtime.

## Design / Behavior
### Environment Variables
- The project uses `.env` for secrets and local runtime overrides.
- The loader resolves `${NAME}` placeholders recursively in `config/sites.yaml`.
- `MCP_SERVER_NAME` sets the MCP server name. Default: `docs-mcp`
- `HTTP_PROXY` and `HTTPS_PROXY` are available to Playwright and other libraries through the process environment.
- `SITE1_USERNAME` and `SITE1_PASSWORD` can be used in site definitions.

Example:
```env
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
- `crawl.block_images`: block image, font, and media requests
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
      block_images: true
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

## Edge Cases
- Unset placeholders resolve to an empty string instead of crashing.
- `CONFIG_FILE` can override the default config path.
- Informational keys should not be treated as enforced runtime behavior.

## References
- [src/config/loader.py](../src/config/loader.py)
- [config/sites.yaml](../config/sites.yaml)
- [config/sites.yaml.example](../config/sites.yaml.example)
- [.env.example](../.env.example)
