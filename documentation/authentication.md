# Authentication

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-25
- Version: v1.1

## Change Log
- 2026-04-25 | v1.1 | Updated commands and references for installed docmcp-auth package entry point.
- 2026-04-24 | v1.0 | Reformatted the authentication guide and documented the current headful session flow.

## Purpose
Describe how `doc-mcp` authenticates to a documentation site, validates stored sessions, and saves browser state for later crawls.

## Scope
- In scope:
  - CLI commands for listing and authenticating sites.
  - Session validation and persistence behavior.
- Out of scope:
  - Site-specific login page design.
  - Multi-mode authentication flows that are not implemented.

## Design / Behavior
### Commands
- List configured sites:
```bash
docmcp-auth --list
```

- Authenticate a site:
```bash
docmcp-auth --site "My Docs"
```

- Force re-authentication:
```bash
docmcp-auth --site "My Docs" --force
```

### Session Flow
1. The CLI loads the site definition from `config/sites.yaml`.
2. If `auth_required` is false, authentication is skipped.
3. If a session file exists, the code checks whether the cookie expiry still looks valid.
4. The saved session is opened in a headless browser and the protected URL is visited.
5. If the browser is redirected to a login-like URL, the session is treated as invalid.
6. If the session is valid, authentication is skipped.
7. If the session is missing or expired, Playwright opens a visible browser window and the user logs in manually.
8. Playwright saves cookies and storage state to `storage/<site>.json`.

### What Gets Saved
- The saved session is the Playwright storage state JSON file.
- It contains cookies and browser storage needed for later crawling.

### Practical Notes
- Authentication is per site.
- The login browser is headful so the user can complete MFA, email-code, or magic-link flows manually.
- The crawler reuses the saved session if it is still valid.

## Edge Cases
- If a cookie has expired, the saved session is treated as invalid before the browser check runs.
- If a site does not require auth, the flow exits without creating a session file.
- If the browser is redirected to a login path, the existing session is discarded and recreated.

## References
- [auth_cli.py](../auth_cli.py)
- [src/docmcp/auth_cli.py](../src/docmcp/auth_cli.py)
- [src/docmcp/auth/session.py](../src/docmcp/auth/session.py)
- [config/sites.yaml](../config/sites.yaml)
