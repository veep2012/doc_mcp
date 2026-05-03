"""
MCP server entry point for installed console scripts.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config.loader import ConfigError, validate_config


def _configure_stdio() -> None:
    """Ensure stdio can carry UTF-8 tool output on platforms that need it."""
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")


def _log_startup_configuration(config: dict) -> None:
    """Emit the resolved runtime configuration to stderr for smoke/debug visibility."""
    logger = logging.getLogger("docmcp.startup")
    runtime_root = Path(os.environ.get("DOC_MCP_HOME", Path.cwd())).expanduser()
    config_file = os.environ.get("CONFIG_FILE", "config/sites.yaml")
    logger.info("DOC_MCP_HOME=%s", runtime_root)
    logger.info("CONFIG_FILE=%s", config_file)

    for site in config.get("sites", []):
        crawl_cfg = site.get("crawl", {})
        start_url = crawl_cfg.get("start_url", site.get("url", ""))
        logger.info(
            "Site=%s url=%s start_url=%s auth_required=%s",
            site.get("name", "<unnamed>"),
            site.get("url", ""),
            start_url,
            site.get("auth_required", False),
        )


def main() -> None:
    """Run the MCP server in stdio mode."""
    _configure_stdio()
    load_dotenv()
    logging.basicConfig(
        level=getattr(logging, os.environ.get("MCP_LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        config = validate_config()
    except ConfigError as exc:
        print(f"[docmcp-server] Startup configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    _log_startup_configuration(config)

    from .tools import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
