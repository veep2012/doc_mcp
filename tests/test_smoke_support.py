import os
import shutil
import subprocess
import sys
import textwrap

import pytest

from tests.conftest import REPO_ROOT
from tests.smoke.support import require_existing_path, require_executable


def test_make_test_declares_unit_before_smoke():
    excluded = {"CONTAINER_BIN", "MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"}
    env = {key: value for key, value in os.environ.items() if key not in excluded}
    result = subprocess.run(
        ["make", "-pn", "test"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "test: test-unit test-smoke" in result.stdout
    assert "test-unit: " in result.stdout or "test-unit:" in result.stdout
    assert "test-smoke: " in result.stdout or "test-smoke:" in result.stdout


def test_direct_pytest_excludes_smoke_by_default(tmp_path):
    probe_dir = REPO_ROOT / ".pytest-probe"
    probe_dir.mkdir(exist_ok=True)
    probe = probe_dir / "test_probe.py"

    try:
        probe.write_text(
            textwrap.dedent(
                """
                import pytest

                def test_fast():
                    pass

                @pytest.mark.smoke
                def test_smoke():
                    pass
                """
            ),
            encoding="utf-8",
        )

        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(probe)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        assert "1 passed, 1 deselected" in result.stdout
    finally:
        probe.unlink(missing_ok=True)
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_missing_container_runtime_fails_with_actionable_message():
    with pytest.raises(pytest.fail.Exception, match="Install Podman or Docker"):
        require_executable("definitely-missing-runtime", "Install Podman or Docker.")


def test_missing_prepared_index_fails_with_actionable_message(tmp_path):
    with pytest.raises(pytest.fail.Exception, match="Prepare the index with docmcp-crawl"):
        require_existing_path(
            tmp_path / "missing.db",
            "Prepare the index with docmcp-crawl or point DOCMCP_SMOKE_INDEX at a prepared SQLite file.",
        )
