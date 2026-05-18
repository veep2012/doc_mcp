# Configuration

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-05-17
- Version: v1.2

## Change Log
- 2026-05-17 | v1.2 | Added local vector sidecar and vectorizer configuration keys plus runtime notes for sqlite-vec.
- 2026-04-25 | v1.1 | Documented runtime root resolution through DOC_MCP_HOME and updated implementation references.
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
- `CONFIG_FILE` sets the site configuration path. Default: `config/sites.yaml`
- `DOC_MCP_HOME` sets the runtime root for relative config, session, and index paths. Default: the current working directory.
- `MCP_SERVER_NAME` sets the MCP server name. Default: `docs-mcp`
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
- `crawl.block_images`: block image, font, and media requests
- `crawl.ignore_anchor_links`: skip fragment-only links
- `crawl.ignore_https_errors`: ignore TLS errors for that site
- `crawl.allow_patterns`: optional allow-list glob patterns
- `crawl.deny_patterns`: optional deny-list glob patterns
- `index_file`: SQLite database path for the site index
- `vector_index_file`: SQLite vector sidecar path for the site
- `vectorizer.chunk_size`: maximum words stored in each vector chunk
- `vectorizer.chunk_overlap`: overlapping words retained between adjacent chunks
- `vectorizer.embedding_dimensions`: embedding size written to the local vector index

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
    vector_index_file: "index/my_docs.vec.db"
    vectorizer:
      chunk_size: 200
      chunk_overlap: 40
      embedding_dimensions: 32
```

### Notes On Example Fields
The sample config file also includes a few future-facing keys such as `auth_mode`, `auth_type`, and `respect_robots_txt`.
- `auth_mode` is currently informational only.
- `auth_type` is currently informational only.
- `respect_robots_txt` is not consumed by the current crawler implementation.
- `vector_index_file` is optional. If omitted, the runtime derives a sidecar path from `index_file` by replacing `*.db` with `*.vec.db`.
- `vectorizer` settings are consumed by `docmcp-vectorize`, not by `docmcp-server`.
- Crawl-time vectorization is disabled by default. Run `docmcp-vectorize --site "My Docs"` explicitly after crawl when you want to build or refresh vector data.
- The local vector backend requires `sqlite-vec` in the active Python environment. Install it with `pip install sqlite-vec` or by installing the project dependencies.

## Edge Cases
- Unset placeholders resolve to an empty string instead of crashing.
- `CONFIG_FILE` can override the default config path.
- Relative `CONFIG_FILE`, `session_file`, `index_file`, and `vector_index_file` values should be interpreted from `DOC_MCP_HOME` or the process working directory.
- Informational keys should not be treated as enforced runtime behavior.
- Missing or broken vector sidecar data does not block keyword search because MCP does not write vector data at query time and the vectorizer is a separate CLI.

## References
- [src/docmcp/config/loader.py](../src/docmcp/config/loader.py)
- [src/docmcp/vector_index.py](../src/docmcp/vector_index.py)
- [config/sites.yaml](../config/sites.yaml)
- [config/sites.yaml.example](../config/sites.yaml.example)
- [.env.example](../.env.example)
