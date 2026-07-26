import os
import shutil
import subprocess
import sys
import textwrap

import pytest

from test_support import REPO_ROOT, require_test_dependency


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


def test_optional_dependency_gates_allow_collection_in_minimal_environment(tmp_path):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        textwrap.dedent(
            """
            import importlib.abc
            import sys

            class BlockOptionalDependencies(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split(".", 1)[0] in {"mcp", "playwright"}:
                        raise ModuleNotFoundError(fullname)
                    return None

            sys.meta_path.insert(0, BlockOptionalDependencies())
            """
        ),
        encoding="utf-8",
    )

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(REPO_ROOT / "src"), str(REPO_ROOT)]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/test_playwright_settings.py",
            "tests/smoke/test_mcp_smoke.py",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "2 tests collected" in result.stdout
    assert "MCP is required for smoke tests" in output
    assert "ModuleNotFoundError" not in output


def test_optional_dependency_gate_uses_repository_install_command():
    with pytest.raises(
        pytest.skip.Exception,
        match=r"Install the repository test dependencies with: python -m pip install -r requirements-dev\.txt",
    ):
        require_test_dependency(
            "docmcp_test_dependency_that_is_not_installed",
            "Example dependency",
            "example tests",
        )


def test_shared_helpers_import_without_tests_package(tmp_path):
    """Shared helpers must not require pytest's test-package import behavior."""
    require_test_dependency("mcp.client.stdio", "MCP", "shared smoke test helpers")
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        textwrap.dedent(
            """
            import importlib.abc
            import sys

            class BlockTestsPackage(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "tests" or fullname.startswith("tests."):
                        raise ModuleNotFoundError(fullname)
                    return None

            sys.meta_path.insert(0, BlockTestsPackage())
            """
        ),
        encoding="utf-8",
    )

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(REPO_ROOT / "src"), str(REPO_ROOT)]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import smoke_support\n"
            "from test_support import REPO_ROOT\n"
            "assert (REPO_ROOT / 'pytest.ini').is_file()",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_missing_container_runtime_fails_with_actionable_message():
    from smoke_support import require_executable

    with pytest.raises(pytest.fail.Exception, match="Install Podman or Docker"):
        require_executable("definitely-missing-runtime", "Install Podman or Docker.")


def test_missing_prepared_index_fails_with_actionable_message(tmp_path):
    from smoke_support import require_existing_path

    with pytest.raises(pytest.fail.Exception, match="Prepare the index with docmcp-crawl"):
        require_existing_path(
            tmp_path / "missing.db",
            "Prepare the index with docmcp-crawl or point DOCMCP_SMOKE_INDEX at a prepared SQLite file.",
        )
