from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_docs_links.py"
SPEC = importlib.util.spec_from_file_location("check_docs_links", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
docs_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs_check)


def test_repository_documentation_is_consistent() -> None:
    assert docs_check.validate(docs_check.ROOT) == []


def test_duplicate_status_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# A\n\n> **Status:** CURRENT_STATUS\n\n> **Status:** ROADMAP\n",
        encoding="utf-8",
    )

    errors = docs_check.check_statuses([doc])

    assert any("exactly one Status" in error for error in errors)


def test_constitution_implementation_state_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "constitution" / "08-Roadmap.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Roadmap\n\n> **Status:** CONSTITUTION\n\n"
        "## Current Repository Migration Audit\n",
        encoding="utf-8",
    )

    errors = docs_check.check_constitution(tmp_path)

    assert any("implementation-state heading" in error for error in errors)


def test_unexpected_document_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "audit" / "stale.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Stale\n\n> **Status:** HISTORICAL\n",
        encoding="utf-8",
    )

    errors = docs_check.check_canonical_inventory(tmp_path, [doc])

    assert any("unexpected document" in error for error in errors)


def test_missing_code_evidence_metadata_is_rejected(tmp_path: Path) -> None:
    for relative in docs_check.CANONICAL_DOCS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "HISTORICAL" if relative == "docs/archive/README.md" else "CURRENT_STATUS"
        path.write_text(
            f"# X\n\n> **Status:** {status}\n> **Code Evidence:** current code\n",
            encoding="utf-8",
        )
    target = tmp_path / "docs/status/Current-State.md"
    target.write_text(
        "# Current\n\n> **Status:** CURRENT_STATUS\n",
        encoding="utf-8",
    )

    errors = docs_check.check_current_metadata(tmp_path)

    assert errors == ["docs/status/Current-State.md: missing Code Evidence metadata"]
