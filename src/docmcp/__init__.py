"""docmcp package metadata and shared helpers."""

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def _read_version_from_pyproject() -> str:
    """Read the project version from the source-tree pyproject.toml."""
    try:
        import tomllib
    except ModuleNotFoundError:
        raise RuntimeError("tomllib is required to read pyproject.toml")

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        pyproject_text = pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError(f"Unable to read version from {pyproject}") from exc

    try:
        project_data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Invalid TOML in {pyproject}") from exc

    try:
        return project_data["project"]["version"]
    except KeyError as exc:
        raise RuntimeError(f"Missing project.version in {pyproject}") from exc
    except TypeError as exc:
        raise RuntimeError(f"Invalid project.version structure in {pyproject}") from exc


def _load_version() -> str:
    """Resolve the package version for source checkouts and installed wheels."""
    try:
        return _read_version_from_pyproject()
    except (FileNotFoundError, RuntimeError):
        pass

    try:
        return package_version("doc-mcp")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _load_version()
