import pytest

import docmcp


def test_read_version_from_pyproject_raises_when_file_is_missing(monkeypatch, tmp_path):
    fake_module_file = tmp_path / "src" / "docmcp" / "__init__.py"
    monkeypatch.setattr(docmcp, "__file__", str(fake_module_file))

    with pytest.raises(FileNotFoundError):
        docmcp._read_version_from_pyproject()


def test_read_version_from_pyproject_raises_on_invalid_toml(monkeypatch, tmp_path):
    fake_module_file = tmp_path / "src" / "docmcp" / "__init__.py"
    (tmp_path / "pyproject.toml").write_text("[project\nversion = '0.1.0'\n", encoding="utf-8")
    monkeypatch.setattr(docmcp, "__file__", str(fake_module_file))

    with pytest.raises(RuntimeError, match="Invalid TOML"):
        docmcp._read_version_from_pyproject()


def test_load_version_falls_back_to_package_metadata(monkeypatch, tmp_path):
    fake_module_file = tmp_path / "dist" / "docmcp" / "__init__.py"
    monkeypatch.setattr(docmcp, "__file__", str(fake_module_file))
    monkeypatch.setattr(
        docmcp, "_read_version_from_pyproject", lambda: (_ for _ in ()).throw(FileNotFoundError())
    )
    monkeypatch.setattr(docmcp, "package_version", lambda name: "0.99.2")

    assert docmcp._load_version() == "0.99.2"
