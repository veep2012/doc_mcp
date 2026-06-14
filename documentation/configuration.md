# Configuration

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-06-14
- Version: v1.8

## Change Log
- 2026-06-14 | v1.8 | Added FastEmbed model-selection guidance, clarified that supported models depend on the installed FastEmbed version, and documented when to use multilingual versus English-focused embeddings.
- 2026-05-26 | v1.7 | Documented crawl timing constraints for `delay_seconds` and `start_delay_seconds`, clarified redirect behavior, and updated the site examples to reflect the merged crawl config.
- 2026-05-24 | v1.6 | Added the `docmcp_vectorizer` console script alias, documented vectorizer `--debug` diagnostics, clarified that chained crawl/vectorize inherits debug output, and kept the vector table inspection guidance platform-neutral.
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
- `crawl.delay_seconds`: pause between page fetches; must be a finite number greater than or equal to 0
- `crawl.start_delay_seconds`: headful-only pause after the start page loads, before crawling begins; must be a finite number greater than or equal to 0
- `crawl.block_images`: block image, font, and media requests
- `crawl.redirect_policy`: handle redirected pages as `final`, `requested`, or `skip`
- `crawl.ignore_query_links`: skip discovered links that contain a query string
- `crawl.ignore_anchor_links`: skip fragment-only links
- `crawl.ignore_https_errors`: ignore TLS errors for that site
- `crawl.allow_patterns`: optional allow-list glob patterns
- `crawl.deny_patterns`: optional deny-list glob patterns
- `index_file`: SQLite database path for the site index
- `search_engine`: per-site search mode. Default: `hybrid`. Use `keyword` to disable vector lookup entirely, `vector` for vector-only semantic search, or `hybrid` to merge keyword and vector results
- `vector_index_file`: local sqlite-vec sidecar path for that site's chunk embeddings; if omitted, the runtime uses the same directory and file stem as `index_file` with a `.vec.db` suffix
- `vectorizer.chunk_size`: maximum normalized chunk length in characters for post-crawl vector records
- `vectorizer.chunk_overlap`: overlapping trailing characters reused when the vectorizer creates the next chunk
- `vectorizer.embedding_model`: FastEmbed text model used to build and query the vector sidecar. Default: `BAAI/bge-small-en-v1.5`
- Before changing this value, check the models supported by the installed FastEmbed package. Supported models depend on the FastEmbed version installed in your environment:
  ```bash
  .venv/bin/python - <<'PY'
  from fastembed import TextEmbedding

  print([m["model"] for m in TextEmbedding.list_supported_models()])
  PY
  ```
  - `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is a good multilingual option when your search corpus spans multiple languages.
  - `BAAI/bge-small-en-v1.5` is a good default when your corpus is primarily English and you want a smaller, faster embedding model.
- Example snapshot of models that may appear in a given FastEmbed release:
  - `BAAI/bge-base-en`
  - `BAAI/bge-base-en-v1.5`
  - `BAAI/bge-large-en-v1.5`
  - `BAAI/bge-small-en`
  - `BAAI/bge-small-en-v1.5`
  - `BAAI/bge-small-zh-v1.5`
  - `mixedbread-ai/mxbai-embed-large-v1`
  - `snowflake/snowflake-arctic-embed-xs`
  - `snowflake/snowflake-arctic-embed-s`
  - `snowflake/snowflake-arctic-embed-m`
  - `snowflake/snowflake-arctic-embed-m-long`
  - `snowflake/snowflake-arctic-embed-l`
  - `jinaai/jina-clip-v1`
  - `Qdrant/clip-ViT-B-32-text`
  - `sentence-transformers/all-MiniLM-L6-v2`
  - `jinaai/jina-embeddings-v2-base-en`
  - `jinaai/jina-embeddings-v2-small-en`
  - `jinaai/jina-embeddings-v2-base-de`
  - `jinaai/jina-embeddings-v2-base-code`
  - `jinaai/jina-embeddings-v2-base-zh`
  - `jinaai/jina-embeddings-v2-base-es`
  - `thenlper/gte-base`
  - `thenlper/gte-large`
  - `nomic-ai/nomic-embed-text-v1.5`
  - `nomic-ai/nomic-embed-text-v1.5-Q`
  - `nomic-ai/nomic-embed-text-v1`
  - `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  - `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
  - `intfloat/multilingual-e5-large`
  - `jinaai/jina-embeddings-v3`

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
    search_engine: "hybrid"
    vector_index_file: "index/my_docs.vec.db"
    vectorizer:
      chunk_size: 800
      chunk_overlap: 120
      embedding_model: "BAAI/bge-small-en-v1.5"  # English-focused default; multilingual docs can use sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

### Notes On Example Fields
The sample config file also includes a few future-facing keys such as `auth_mode`, `auth_type`, and `respect_robots_txt`.
- `auth_mode` is currently informational only.
- `auth_type` is currently informational only.
- `respect_robots_txt` is not consumed by the current crawler implementation.
- `crawl.redirect_policy` defaults to `final`, which preserves the existing behavior of indexing the landing URL after a redirect.
- `crawl.start_delay_seconds` is off by default. Use it when you want a visible headful browser to load the start page, pause, and let you switch to the exact page you want to scan.

### Local Vector Sidecar Notes
- `search_engine: keyword` keeps the site on keyword-only search, `search_engine: vector` uses the vector sidecar only, and `search_engine: hybrid` combines both.
- `docmcp-crawl` still writes only the keyword SQLite index in this stage.
- Build or refresh the local vector sidecar explicitly with `docmcp-vectorize --site "<Site Name>"`, `docmcp_vectorizer --site "<Site Name>"`, or `docmcp-crawl --vectorize --site "<Site Name>"` after crawling.
- The vectorizer reads the existing `index_file`, chunks page Markdown deterministically, generates FastEmbed embeddings, and rewrites the configured `vector_index_file`.
- Install the vector backend with `pip install sqlite-vec fastembed` if you are running from source. The packaged project now declares both dependencies as runtime requirements.
- Changing `vectorizer.embedding_model` changes the vector space and requires rebuilding the sidecar.
- `docmcp-vectorize --debug` and `docmcp_vectorizer --debug` enable chunk-level vectorizer diagnostics; normal runs stay at page-level progress.
- When `docmcp-crawl --debug --vectorize` runs the vectorizer immediately after a successful crawl, that debug mode is inherited.
- To inspect the vector tables with `sqlite3`, use a shell that supports extension loading, open `index/<site>.vec.db`, and load the platform-appropriate `vec0` library before running `.tables`:
  - `sqlite3 index/<site>.vec.db`
  - `.load <path-to-sqlite_vec>/vec0.<platform-extension>` where the platform-specific filename is `vec0.dylib` on macOS, `vec0.so` on Linux, or `vec0.dll` on Windows
- Crawl-time vectorization chaining is available as an explicit opt-in via `docmcp-crawl --vectorize`, while the vectorizer still remains a separate post-crawl step.

## Edge Cases
- Unset placeholders resolve to an empty string instead of crashing.
- Workspace `.env` values are only used for config resolution; loading config does not mutate process env.
- `CONFIG_FILE` can override the default config path.
- Relative `CONFIG_FILE`, `session_file`, `index_file`, and `vector_index_file` values should be interpreted from `DOC_MCP_HOME` or the process working directory.
- `crawl.start_url` is used as the initial crawl seed and is preserved exactly as configured, including any query string.
- `crawl.start_url` is used as the initial crawl seed and is preserved exactly as configured, including any query string.
- `crawl.redirect_policy: requested` stores the original requested URL when a page redirects, while `skip` leaves redirected pages out of the index but still crawls the loaded page and discovers links from it.
- `crawl.start_delay_seconds` only applies in headful mode; headless runs ignore it. When it is used, the crawl starts from the page that is open when the pause ends.
- `crawl.ignore_query_links: true` skips discovered links that contain a query string, while `false` allows them to be crawled and indexed as distinct URLs.
- `crawl.redirect_policy: final` preserves the landing URL after a redirect, which matches the current default behavior.
- If `vector_index_file` is omitted, the vectorizer writes `<index_file stem>.vec.db` alongside the keyword SQLite index.
- If sqlite-vec cannot be loaded, `docmcp-vectorize` and `docmcp_vectorizer` fail clearly but crawl and keyword-only MCP search still work.
- Informational keys should not be treated as enforced runtime behavior.

## References
- [src/docmcp/config/loader.py](../src/docmcp/config/loader.py)
- [config/sites.yaml](../config/sites.yaml)
- [config/sites.yaml.example](../config/sites.yaml.example)
- [.env.example](../.env.example)
