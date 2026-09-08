import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BARE_PYTHON_COMMAND = re.compile(
    r"^(?:[A-Z][A-Z0-9_]*=\S+\s+)?python(?:\s|$)"
)
PROJECT_ENVIRONMENT_GATE_COMMANDS = (
    "uv sync --frozen --extra dev --extra postgres",
    "uv run python scripts/check_docs_links.py",
    "uv run python scripts/check_repository_hygiene.py",
    "uv run python -m pytest -q",
    "uv run python -m ruff check .",
    "uv run python -m mypy",
    "uv run python -m build",
)
REPOSITORY_ENTRYPOINTS = ("AGENTS.md", "README.md", "CLAUDE.md")


def test_uv_lock_and_ci_define_the_frozen_python_312_gate() -> None:
    lock = ROOT / "uv.lock"
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert lock.is_file()
    assert 'python-version: "3.12"' in workflow
    assert "astral-sh/setup-uv@" in workflow
    assert "uv sync --frozen --extra dev --extra postgres" in workflow
    for command in (
        "uv run python scripts/check_docs_links.py",
        "uv run pytest",
        "uv run ruff check .",
        "uv run mypy",
        "uv run python -m build",
    ):
        assert command in workflow


def test_one_development_gate_and_entrypoint_links_use_the_project_environment() -> None:
    development = (ROOT / "docs/Development.md").read_text()
    for command in PROJECT_ENVIRONMENT_GATE_COMMANDS:
        assert command in development.splitlines()
    for relative_path in (*REPOSITORY_ENTRYPOINTS, "docs/Development.md"):
        text = (ROOT / relative_path).read_text()
        assert not [line for line in text.splitlines() if BARE_PYTHON_COMMAND.match(line)]
    for relative_path in REPOSITORY_ENTRYPOINTS:
        text = (ROOT / relative_path).read_text()
        assert "docs/README.md" in text
    assert "docs/Development.md" in (ROOT / "AGENTS.md").read_text()


def test_setuptools_remains_the_build_backend() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'build-backend = "setuptools.build_meta"' in project
    assert 'postgres = [' in project
    assert 'dev = [' in project
    assert 'pythonpath = ["src", "."]' in project
