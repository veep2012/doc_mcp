# Project Requirements: Documentation MCP Server

## Overview

Build an MCP (Model Context Protocol) server that allows AI assistants to access
authenticated documentation sites. The server uses Playwright for semi-manual
authentication and Crawl4AI for crawling and indexing documentation.

---

## Goals

- Provide AI assistants with up-to-date, site-specific documentation via MCP tools
- Support documentation sites that require authentication (email code / magic link)
- Allow any documentation site to be indexed starting from a root/parent URL
- Expose search and fetch capabilities over indexed content

---

## Architecture

```
Playwright (semi-manual auth → saves session/cookies)
        ↓
Crawl4AI (uses saved session → crawls & indexes documentation)
        ↓
MCP Server (exposes tools: search, fetch, list pages)
        ↓
AI Client (Claude, Copilot, etc.)
```

---

## Authentication Flow

Authentication supports **two modes** depending on site configuration.

**Implementation Priority:**
1. **Mode 2 — Semi-manual** *(implement first)*
2. **Mode 1 — Automated** *(implement later, as an enhancement)*

---

### Mode 1: Automated (MCP-driven)
Playwright fills in credentials automatically using values stored in config (username/password).
No user interaction required. Used for sites with standard login forms where credentials are known.

1. MCP server reads credentials from config (`config/sites.yaml` or env variables)
2. Playwright opens the site in **headless mode** and fills in login/password automatically
3. Playwright submits the form and detects successful authentication
4. Session is saved to `storage/<domain>.json` and reused for crawling

### Mode 2: Semi-manual (User-interactive)
Used when a one-time code, magic link, or captcha is required that cannot be automated.
The user is prompted to interact — either in the **browser window** (headful) or via **CLI input** (CMD mode).

1. User runs the auth script for a target site
2. Playwright opens the site — either in a **visible browser window** (headful) or **headless with CLI prompts** (CMD mode)
3. In **headful mode**: user types credentials, code, or clicks magic link directly in the browser
4. In **CMD mode**: Playwright fills what it can automatically; CLI prompts the user to enter the one-time code
5. Playwright detects successful authentication (e.g., redirect to authenticated page)
6. Playwright saves the authenticated session (cookies + local storage) to `storage/<domain>.json`
7. Session is reused for all subsequent crawling — no re-auth needed until session expires

> **Key principle:** Automated auth is preferred. Semi-manual is a fallback for email codes,
> magic links, or MFA steps that cannot be automated.

### Requirements
- [ ] Support **automated auth** — Playwright fills login/password from config without user interaction
- [ ] Support **headful semi-manual auth** — user interacts directly in a visible browser window
- [ ] Support **CMD semi-manual auth** — user enters one-time code via CLI prompt, rest is automated
- [ ] Auth mode must be configurable per site (`auth_mode: auto | headful | cmd`)
- [ ] Credentials (login, password) must be storable in config or environment variables
- [ ] Playwright must wait for the user to complete interactive steps before saving the session
- [ ] A CLI prompt must signal the user when to proceed (e.g., "Enter the code from your email: ")
- [ ] Auth script must support configurable target URL per site
- [ ] Session must be persisted to disk (`storage/<domain>.json`)
- [ ] Session expiry must be detectable (re-auth prompt triggered automatically if session is invalid)
- [ ] Multiple site sessions must be supported (keyed by domain)

---

## Crawling & Indexing

- Uses **Crawl4AI** with the saved Playwright session (cookies injected)
- Starting point: root/parent URL of the documentation site
- Crawl4AI follows internal links to discover all documentation pages
- Each page is converted to clean **Markdown**
- Pages are stored in a **SQLite database** (no page limit — unlimited)
- Re-indexing must be triggerable on demand

### Requirements
- [ ] Accept any root URL as the entry point for crawling
- [ ] Use parent page link structure as the documentation index
- [ ] Store indexed pages as Markdown with metadata (URL, title, last crawled)
- [ ] Support incremental re-indexing (only changed pages)
- [ ] Respect `robots.txt` and crawl rate limits (configurable)
- [ ] Crawling must run in **headless mode** (headful is only used during auth)

---

## MCP Server

Exposes the following tools to AI clients:

| Tool | Description |
|------|-------------|
| `search_docs` | Full-text search across indexed documentation |
| `fetch_page` | Fetch a specific documentation page by URL or title |
| `list_pages` | List all indexed pages for a site |
| `reindex_site` | Trigger re-crawl and re-index of a documentation site |
| `get_sites` | List all configured/indexed documentation sites |

### Requirements
- [ ] MCP server must follow the MCP specification (using `mcp` Python SDK)
- [ ] Server must operate in **stdio mode** as the primary transport (for use with Claude Desktop, Copilot, etc.)
- [ ] Tools must return clean Markdown content
- [ ] Server must be configurable via a config file (`config/sites.yaml`)
- [ ] Server must support multiple documentation sites simultaneously

---

## Configuration

Sites are configured in `config/sites.yaml`:

```yaml
sites:
  - name: "My Docs Site"
    url: "https://docs.example.com"
    auth_required: true
    auth_type: "email_code"
    auth_mode: "cmd"          # auto | headful | cmd
    username: "user@example.com"
    password: "${SITE_PASSWORD}"  # supports env variable substitution
    session_file: "storage/example_com.json"
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Browser Automation | Playwright (async) |
| Web Crawling | Crawl4AI |
| MCP Server | `mcp` Python SDK |
| Storage | SQLite (pages index, unlimited) + JSON (sessions) |
| Config | YAML (`PyYAML`) |
| Async Runtime | `asyncio` |

---

## Project Structure (Proposed)

```
docs-mcp/
├── document/
│   └── requirements.md          # This file
├── src/
│   ├── main.py                  # MCP server entry point
│   ├── auth/
│   │   ├── __init__.py
│   │   └── session.py           # Playwright auth + session management
│   ├── crawler/
│   │   ├── __init__.py
│   │   └── crawl.py             # Crawl4AI integration
│   ├── index/
│   │   ├── __init__.py
│   │   └── store.py             # SQLite index storage
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── tools.py             # MCP tool definitions
│   └── config/
│       ├── __init__.py
│       └── loader.py            # YAML config loader
├── config/
│   └── sites.yaml               # Site configuration
├── storage/                     # Session files (gitignored)
├── index/                       # SQLite index files (gitignored)
├── requirements.txt
└── README.md
```

---

## Out of Scope (v1)

- No web UI
- No cloud deployment
- No OAuth / SSO authentication (only email code / magic link)
- No real-time indexing (on-demand only)
- No encryption of session files on disk (plain JSON for now)
- No vector embeddings / semantic search (use SQLite FTS keyword search for now; vector DB is future)


