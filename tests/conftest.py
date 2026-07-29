"""Shared pytest fixtures for the contextlens test suite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def python_executable() -> str:
    """Path to the python interpreter running the tests."""
    return sys.executable


def _run_cli(
    executable: str,
    args: list[str],
    stdin_text: str,
) -> subprocess.CompletedProcess[str]:
    """Run a CLI subprocess, raising on OS-level failure only."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return subprocess.run(
        [executable, *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


@pytest.fixture
def run_cli(python_executable: str):
    """Factory: invoke a contextlens CLI subprocess and return the
    CompletedProcess for assertion."""

    def _factory(args: list[str], stdin_text: str = "") -> subprocess.CompletedProcess[str]:
        return _run_cli(python_executable, ["-m", "contextlens", *args], stdin_text)

    return _factory


@pytest.fixture
def run_mcp(python_executable: str):
    """Factory: invoke ``python -m contextlens.mcp`` and return the
    CompletedProcess."""

    def _factory(stdin_text: str) -> subprocess.CompletedProcess[str]:
        return _run_cli(
            python_executable,
            ["-m", "contextlens.mcp"],
            stdin_text,
        )

    return _factory