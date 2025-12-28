"""Nox sessions for RhythmSlicer development tasks."""

from __future__ import annotations

from pathlib import Path

import sys
import nox


ROOT = Path(__file__).parent

nox.options.error_on_missing_interpreters = False


def _has_mypy_config() -> bool:
    if (ROOT / "mypy.ini").is_file():
        return True
    if (ROOT / "setup.cfg").is_file():
        return True
    if (ROOT / "tox.ini").is_file():
        return True
    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        return "[tool.mypy]" in pyproject.read_text(encoding="utf-8")
    return False


@nox.session
def lint(session: nox.Session) -> None:
    """Run ruff linting and formatting checks."""
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(name="lint-fix")
def lint_fix(session: nox.Session) -> None:
    """Apply ruff fixes and formatting."""
    session.install("ruff")
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session
def tests(session: nox.Session) -> None:
    """Run pytest in CI-friendly mode."""
    session.install("-e", ".[dev]")
    session.env["RHYTHM_SLICER_CI"] = "1"
    try:
        session.run("pytest", "-q")
    finally:
        session.env.pop("RHYTHM_SLICER_CI", None)


@nox.session
def typecheck(session: nox.Session) -> None:
    """Run mypy when a config is present."""
    if not _has_mypy_config():
        session.skip("mypy config not found")
    session.install("mypy")
    session.run("mypy", "src/rhythm_slicer")


@nox.session
def build(session: nox.Session) -> None:
    """Build sdist and wheel artifacts."""
    session.install("build")
    session.run("python", "-m", "build")


@nox.session
def coverage(session: nox.Session) -> None:
    """Run coverage reporting."""
    session.install("-e", ".[dev]")
    session.install("coverage")
    session.run("coverage", "run", "--source=rhythm_slicer", "-m", "pytest")
    session.run("coverage", "report", "--fail-under=80", "-m")


# --------------------------------------------------
#                  LOCAL DEV TESTING
# --------------------------------------------------


@nox.session(name="lint-fix-dev", venv_backend="none")
def lint_fix_dev(session: nox.Session) -> None:
    """Apply ruff fixes and formatting."""
    session.run("python", "-m", "ruff", "check", "--fix", ".", external=True)
    session.run("python", "-m", "ruff", "format", ".", external=True)


@nox.session(name="lint-dev", venv_backend="none")
def lint_dev(session: nox.Session) -> None:
    """Fast local lint using active venv."""
    session.run("python", "-m", "ruff", "check", ".", external=True)
    session.run("python", "-m", "ruff", "format", "--check", ".", external=True)


@nox.session(name="tests-dev", venv_backend="none")
def tests_dev(session: nox.Session) -> None:
    """Fast local pytest using active venv."""
    session.run("python", "-m", "pytest", "-q", external=True)


@nox.session(name="typecheck-dev", venv_backend="none")
def typecheck_dev(session: nox.Session) -> None:
    """Fast local mypy using active venv."""
    if not _has_mypy_config():
        session.skip("mypy config not found")
    session.run("python", "-m", "mypy", "src/rhythm_slicer", external=True)


@nox.session(name="coverage-dev", venv_backend="none")
def coverage_dev(session: nox.Session) -> None:
    """Fast local coverage using active venv."""
    session.run(
        "python",
        "-m",
        "coverage",
        "run",
        "--source=rhythm_slicer",
        "-m",
        "pytest",
        external=True,
    )
    session.run(
        "python",
        "-m",
        "coverage",
        "report",
        "--fail-under=80",
        "-m",
        external=True,
    )


@nox.session(name="local-dev", venv_backend="none")
def local_dev(session: nox.Session) -> None:
    """Run the fast local dev checks (lint, typecheck, tests, coverage)."""
    session.run(
        sys.executable,
        "-m",
        "nox",
        "-s",
        "lint-fix-dev",
        "lint-dev",
        "typecheck-dev",
        "tests-dev",
        # "coverage-dev",
        external=True,
    )
