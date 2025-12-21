"""Nox sessions for RhythmSlicer development tasks."""

from __future__ import annotations

from pathlib import Path

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


@nox.session(python="3.12")
def lint(session: nox.Session) -> None:
    """Run ruff linting and formatting checks."""
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(name="lint-fix", python="3.12")
def lint_fix(session: nox.Session) -> None:
    """Apply ruff fixes and formatting."""
    session.install("ruff")
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session(python=["3.11", "3.12"])
def tests(session: nox.Session) -> None:
    """Run pytest in CI-friendly mode."""
    session.install("-e", ".[dev]")
    session.env["RHYTHM_SLICER_CI"] = "1"
    try:
        session.run("pytest", "-q")
    finally:
        session.env.pop("RHYTHM_SLICER_CI", None)


@nox.session(python="3.12")
def typecheck(session: nox.Session) -> None:
    """Run mypy when a config is present."""
    if not _has_mypy_config():
        session.skip("mypy config not found")
    session.install("mypy")
    session.run("mypy", "src/rhythm_slicer")


@nox.session(python="3.12")
def build(session: nox.Session) -> None:
    """Build sdist and wheel artifacts."""
    session.install("build")
    session.run("python", "-m", "build")


@nox.session(python="3.12")
def coverage(session: nox.Session) -> None:
    """Run coverage reporting."""
    session.install("-e", ".[dev]")
    session.install("coverage")
    session.run("coverage", "run", "-m", "pytest")
    session.run("coverage", "report", "-m")
