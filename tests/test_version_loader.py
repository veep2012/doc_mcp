import pytest

import docmcp


def test_read_version_from_pyproject_falls_back_when_file_is_missing(monkeypatch, tmp_path):
    fake_module_file = tmp_path / "src" / "docmcp" / "__init__.py"
    monkeypatch.setattr(docmcp, "__file__", str(fake_module_file))

    assert docmcp._read_version_from_pyproject() == "0.0.0"


def test_read_version_from_pyproject_raises_on_invalid_toml(monkeypatch, tmp_path):
    fake_module_file = tmp_path / "src" / "docmcp" / "__init__.py"
    (tmp_path / "pyproject.toml").write_text("[project\nversion = '0.1.0'\n", encoding="utf-8")
    monkeypatch.setattr(docmcp, "__file__", str(fake_module_file))

    with pytest.raises(RuntimeError, match="Invalid TOML"):
        docmcp._read_version_from_pyproject()
