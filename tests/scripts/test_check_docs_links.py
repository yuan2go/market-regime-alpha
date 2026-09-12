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


def test_imported_delivery_preserves_bytes_and_declares_external_links(tmp_path: Path) -> None:
    import hashlib
    import json
    base = tmp_path / docs_check.DELIVERY_SNAPSHOTS[0]
    base.mkdir(parents=True)
    data = b"# Frozen original\n[External](unbundled.json)\n"
    (base / "report.md").write_bytes(data)
    manifest = {"schema": "historical-delivery-snapshot-v1", "files": {"report.md": {
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}}, "external_files": {
        "unbundled.json": {"size": 2, "sha256": hashlib.sha256(b"{}").hexdigest(), "availability": "EXTERNAL_NOT_BUNDLED"}}}
    path = base / "snapshot-manifest.json"
    path.write_text(json.dumps(manifest))
    assert docs_check.check_delivery_snapshots(tmp_path) == []
    assert docs_check.markdown_files(tmp_path) == []
    (base / "report.md").write_bytes(data + b"changed")
    assert any("bytes changed" in e for e in docs_check.check_delivery_snapshots(tmp_path))
    (base / "report.md").write_bytes(data)
    manifest["external_files"] = {}
    path.write_text(json.dumps(manifest))
    assert any("undeclared frozen delivery link" in e for e in docs_check.check_delivery_snapshots(tmp_path))


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


def test_historical_records_are_allowed_only_in_the_archive(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "archive" / "record.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Record\n\n> **Status:** HISTORICAL\n",
        encoding="utf-8",
    )

    errors = docs_check.check_canonical_inventory(
        tmp_path,
        [
            *(tmp_path / relative for relative in docs_check.CANONICAL_DOCS),
            doc,
        ],
    )

    assert errors == []


def test_missing_code_evidence_metadata_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for relative in docs_check.CANONICAL_DOCS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "HISTORICAL" if relative == "docs/archive/README.md" else "CURRENT_STATUS"
        path.write_text(
            f"# X\n\n> **Status:** {status}\n> **Code Evidence:** `pyproject.toml`\n",
            encoding="utf-8",
        )
    target = tmp_path / "docs/status/Current-State.md"
    target.write_text(
        "# Current\n\n> **Status:** CURRENT_STATUS\n",
        encoding="utf-8",
    )

    errors = docs_check.check_current_metadata(tmp_path)

    assert errors == [
        "docs/status/Current-State.md: missing resolvable Code Evidence paths"
    ]


def test_nonexistent_code_evidence_path_is_rejected(tmp_path: Path) -> None:
    for relative in docs_check.CANONICAL_DOCS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "HISTORICAL" if relative == "docs/archive/README.md" else "CURRENT_STATUS"
        path.write_text(
            f"# X\n\n> **Status:** {status}\n"
            "> **Code Evidence:** `missing/owner.py`\n",
            encoding="utf-8",
        )

    errors = docs_check.check_current_metadata(tmp_path)

    assert any("Code Evidence path does not resolve" in error for error in errors)
