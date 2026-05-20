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
        pyproject_text = pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "0.0.0"
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


try:
    __version__ = package_version("doc-mcp")
except PackageNotFoundError:
    __version__ = _read_version_from_pyproject()
