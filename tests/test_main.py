import logging
import sys

import pytest

from docmcp.main import _log_startup_configuration
from docmcp import __version__
import docmcp.main as main_cli


def test_startup_logging_does_not_expose_sensitive_site_paths(caplog):
    config = {
        "sites": [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": True,
                "index_file": "/tmp/runtime/index/example.db",
                "session_file": "/tmp/runtime/storage/example.json",
                "crawl": {"start_url": "https://example.test/docs"},
            }
        ]
    }

    caplog.set_level(logging.INFO, logger="docmcp.startup")

    _log_startup_configuration(config)

    output = caplog.text
    assert "Example Docs" in output
    assert "start_url=https://example.test/docs" in output
    assert "auth_required=True" in output
    assert "index_file" not in output
    assert "session_file" not in output


def test_server_cli_version_and_help_include_current_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-server", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        main_cli.main()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"docmcp-server {__version__}"

    monkeypatch.setattr(sys, "argv", ["docmcp-server", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        main_cli.main()
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert f"Version: {__version__}" in help_text
