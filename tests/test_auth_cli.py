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


def test_auth_cli_list_reports_supported_authentication_status(monkeypatch, capsys):
    monkeypatch.setattr(
        auth_cli,
        "get_sites",
        lambda: [
            {
                "name": "Private Docs",
                "url": "https://private.example.test",
                "auth_required": True,
                "auth_mode": "unsupported metadata",
            },
            {
                "name": "Public Docs",
                "url": "https://public.example.test",
                "auth_required": False,
            },
        ],
    )
    monkeypatch.setattr(sys, "argv", ["docmcp-auth", "--list"])

    auth_cli.main()

    output = capsys.readouterr().out
    assert "Private Docs (auth required) — https://private.example.test" in output
    assert "Public Docs (public) — https://public.example.test" in output
    assert "auth_mode" not in output
    assert "unsupported metadata" not in output
