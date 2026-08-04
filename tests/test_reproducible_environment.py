from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


def test_setuptools_remains_the_build_backend() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'build-backend = "setuptools.build_meta"' in project
    assert 'postgres = [' in project
    assert 'dev = [' in project
