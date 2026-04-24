"""
MCP Server entry point — runs in stdio mode using FastMCP.
Usage:
    python -m src.main
    python src/main.py
"""

import os
import sys
from dotenv import load_dotenv

import logging
from src.docmcp.tools import mcp

# Ensure stdout/stderr use UTF-8 on Windows to handle Unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.environ.get("MCP_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    """Run the MCP server in stdio mode."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
