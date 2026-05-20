"""docmcp package metadata and shared helpers."""

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def _read_version_from_pyproject() -> str:
    """Fallback to the project version when the package is run from source."""
    try:
        import tomllib
    except ModuleNotFoundError:
        return "0.0.0"

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        return "0.0.0"


try:
    __version__ = package_version("doc-mcp")
except PackageNotFoundError:
    __version__ = _read_version_from_pyproject()
