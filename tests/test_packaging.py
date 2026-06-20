from pathlib import Path
import tomllib


def test_pyproject_exposes_vectorizer_console_scripts():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]

    assert scripts["docmcp-vectorize"] == "docmcp.vectorize_cli:main"
    assert "docmcp_vectorizer" not in scripts
