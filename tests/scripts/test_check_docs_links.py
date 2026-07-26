from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_docs_links.py"
SPEC = importlib.util.spec_from_file_location("check_docs_links", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
docs_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs_check)


def test_duplicate_status_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# A\n\n> **Status:** CURRENT_STATUS\n\n> **Status:** CURRENT\n",
        encoding="utf-8",
    )
    errors = docs_check.check_statuses([doc])
    assert any("exactly one Status" in error for error in errors)


def test_constitution_implementation_state_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "constitution" / "08-Roadmap.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Roadmap\n\n> **Status:** CONSTITUTION\n\n## Current Repository Migration Audit\n",
        encoding="utf-8",
    )
    errors = docs_check.check_constitution(tmp_path)
    assert any("implementation-state heading" in error for error in errors)


def test_missing_code_symbol_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "docs" / "audit").mkdir(parents=True)
    (tmp_path / "docs" / "x.md").write_text(
        "# X\n\n> **Status:** CURRENT_STATUS\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "audit" / "Code-Evidence-Registry.tsv").write_text(
        "document_path\tevidence_type\tevidence_ref\trequired\n"
        "docs/x.md\tsymbol\tMissingSymbol\ttrue\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    errors = docs_check.check_code_evidence(tmp_path)
    assert any("symbol missing" in error for error in errors)


def test_orphan_current_doc_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "current.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Current\n\n> **Status:** CURRENT_STATUS\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    errors = docs_check.check_orphans(tmp_path, [doc])
    assert any("orphan current document" in error for error in errors)


def test_inventory_requires_verified_target(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "audit" / "Docs-Inventory.tsv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "path\tactual_action\ttarget_path\tverification_status\n"
        "docs/a.md\tARCHIVED\tdocs/archive/a.md\tFAILED\n",
        encoding="utf-8",
    )
    errors = docs_check.check_inventory(tmp_path)
    assert any("inventory unresolved" in error for error in errors)
