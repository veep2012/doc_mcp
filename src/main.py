"""Compatibility wrapper for source-tree invocations."""

try:
    from .docmcp.main import main
except ImportError:
    from src.docmcp.main import main


if __name__ == "__main__":
    main()
