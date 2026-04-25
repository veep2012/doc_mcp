"""
MCP server entry point for installed console scripts.
"""

import logging
import os
import sys

from dotenv import load_dotenv

from .tools import mcp


def _configure_stdio() -> None:
    """Ensure stdio can carry UTF-8 tool output on platforms that need it."""
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    """Run the MCP server in stdio mode."""
    _configure_stdio()
    load_dotenv()
    logging.basicConfig(
        level=getattr(logging, os.environ.get("MCP_LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
