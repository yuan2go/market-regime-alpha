import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BARE_PYTHON_COMMAND = re.compile(
    r"^(?:[A-Z][A-Z0-9_]*=\S+\s+)?python(?:\s|$)"
)
PROJECT_ENVIRONMENT_GATE_COMMANDS = (
    "uv run python scripts/check_docs_links.py",
    "uv run python -m pytest -q tests/scripts/test_check_docs_links.py",
    "uv run python -m pytest -q tests/platform",
    "uv run python -m pytest -q",
    "uv run python -m ruff check .",
    "uv run python -m mypy",
    "uv run python -m build",
)


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


def test_repository_entrypoint_gates_use_the_project_environment() -> None:
    for relative_path in ("AGENTS.md", "README.md"):
        lines = (ROOT / relative_path).read_text(encoding="utf-8").splitlines()

        assert "uv sync --frozen --extra dev --extra postgres" in lines
        for command in PROJECT_ENVIRONMENT_GATE_COMMANDS:
            assert any(
                line == command or line.endswith(f" {command}") for line in lines
            ), f"{relative_path}: missing project-environment command: {command}"

        bare_commands = [
            line for line in lines if BARE_PYTHON_COMMAND.match(line)
        ]
        assert bare_commands == [], (
            f"{relative_path}: bare Python commands bypass the uv project environment: "
            f"{bare_commands}"
        )


def test_setuptools_remains_the_build_backend() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'build-backend = "setuptools.build_meta"' in project
    assert 'postgres = [' in project
    assert 'dev = [' in project
    assert 'pythonpath = ["src", "."]' in project
