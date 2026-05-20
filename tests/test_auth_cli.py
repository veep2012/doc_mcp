import sys

import pytest

import docmcp.auth_cli as auth_cli
from docmcp import __version__


def test_auth_cli_version_and_help_include_current_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-auth", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        auth_cli.main()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"docmcp-auth {__version__}"

    monkeypatch.setattr(sys, "argv", ["docmcp-auth", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        auth_cli.main()
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert f"Version: {__version__}" in help_text


def test_auth_cli_version_rejects_other_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-auth", "--version", "--list"])
    with pytest.raises(SystemExit) as excinfo:
        auth_cli.main()
    assert excinfo.value.code == 2
    assert "--version cannot be combined with other arguments" in capsys.readouterr().err
