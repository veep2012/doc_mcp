import base64
import hashlib
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

from scripts.build_mcp_wheel import build_mcp_wheel


def _write_minimal_source_wheel(path: Path) -> None:
    files = {
        "docmcp/__init__.py": b"VALUE = 'installed'\n",
        "docmcp/main.py": b"def main(): pass\n",
        "doc_mcp-1.2.3.dist-info/METADATA": (
            b"Metadata-Version: 2.1\n"
            b"Name: doc-mcp\n"
            b"Version: 1.2.3\n"
            b"Requires-Python: >=3.11\n"
            b"Requires-Dist: crawler==1.0\n"
        ),
        "doc_mcp-1.2.3.dist-info/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Generator: test\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
        "doc_mcp-1.2.3.dist-info/entry_points.txt": (
            b"[console_scripts]\n"
            b"docmcp-server = docmcp.main:main\n"
            b"docmcp-crawl = docmcp.crawl_cli:main\n"
        ),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_pyproject_exposes_vectorizer_console_scripts():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]

    assert scripts["docmcp-vectorize"] == "docmcp.vectorize_cli:main"
    assert "docmcp_vectorizer" not in scripts


def test_build_mcp_wheel_rewrites_and_installs_minimal_wheel(tmp_path: Path):
    """TS-TF-022: Rewrite, validate, and install a minimal MCP-only wheel."""
    source = tmp_path / "doc_mcp-1.2.3-py3-none-any.whl"
    requirements = tmp_path / "requirements-mcp.txt"
    output_dir = tmp_path / "dist"
    install_dir = tmp_path / "install"
    _write_minimal_source_wheel(source)
    requirements.write_text("# pinned\nmcp==9.9.9\nfastembed==8.8.8\n", encoding="utf-8")

    output = build_mcp_wheel(source, output_dir, requirements)

    assert output.name == "doc_mcp_no_crawler-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(output) as archive:
        members = {
            name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
        }
    assert "doc_mcp_no_crawler-1.2.3.dist-info/METADATA" in members
    assert all("doc_mcp-1.2.3.dist-info" not in name for name in members)

    metadata = members["doc_mcp_no_crawler-1.2.3.dist-info/METADATA"].decode()
    assert "Name: doc-mcp-no-crawler\n" in metadata
    assert "Requires-Dist: mcp==9.9.9\n" in metadata
    assert "Requires-Dist: fastembed==8.8.8\n" in metadata
    assert "Requires-Dist: crawler==1.0\n" not in metadata
    assert (
        members["doc_mcp_no_crawler-1.2.3.dist-info/entry_points.txt"].decode()
        == "[console_scripts]\ndocmcp-server = docmcp.main:main\n"
    )

    record_name = "doc_mcp_no_crawler-1.2.3.dist-info/RECORD"
    record_rows = [line.split(",") for line in members[record_name].decode().splitlines()]
    record = {row[0]: row[1:] for row in record_rows}
    assert record[record_name] == ["", ""]
    for name, data in members.items():
        if name == record_name:
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        assert record[name] == [f"sha256={digest}", str(len(data))]

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_dir),
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-c", "import docmcp; print(docmcp.VALUE)"],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": str(Path(sys.executable).parent), "PYTHONPATH": str(install_dir)},
    )
    assert result.stdout.strip() == "installed"
