from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent
TEST_DEPENDENCY_INSTALL_COMMAND = "python -m pip install -r requirements-dev.txt"


def require_test_dependency(module_name: str, dependency_name: str, purpose: str):
    """Skip tests consistently when an optional test dependency is unavailable."""
    return pytest.importorskip(
        module_name,
        reason=(
            f"{dependency_name} is required for {purpose}. "
            f"Install the repository test dependencies with: {TEST_DEPENDENCY_INSTALL_COMMAND}"
        ),
    )
