import logging

from docmcp.main import _log_startup_configuration


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
