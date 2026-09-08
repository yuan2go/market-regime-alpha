from pathlib import Path

from scripts import check_repository_hygiene as hygiene
from scripts.check_docs_links import check_archived_snapshot
from scripts.repository_inventory import imports, unresolved_imports

import ast
import json
from hashlib import sha256


def test_comment_noise_is_rejected_but_frozen_identity_strings_are_not(tmp_path: Path) -> None:
    source = tmp_path / "src" / "owner.py"
    source.parent.mkdir()
    source.write_text('IDENTITY = "WP-18Q-v1"\n')
    assert hygiene.check_commentary(tmp_path) == []
    source.write_text('# WP-18Q temporary owner\nIDENTITY = "WP-18Q-v1"\n')
    assert len(hygiene.check_commentary(tmp_path)) == 1


def test_stale_schema_count_cannot_pass_with_an_unchanged_epoch(tmp_path: Path) -> None:
    path = tmp_path / "docs/status/Current-State.md"
    path.parent.mkdir(parents=True)
    path.write_text(hygiene.schema_facts().replace("**194**", "**192**"))
    assert hygiene.check_schema_facts(tmp_path) == ["Current-State schema facts differ from executable schema contract"]


def test_current_docs_cannot_reactivate_a_historical_work_package(tmp_path: Path) -> None:
    path = tmp_path / "docs/README.md"
    path.parent.mkdir()
    path.write_text("Resume WP-18Q from its old plan.\n")
    assert hygiene.check_active_context(tmp_path)
    path.write_text("Read [Historical archive](archive/README.md) only for provenance.\n")
    assert hygiene.check_active_context(tmp_path) == []


def test_archived_record_corruption_fails_even_when_the_path_is_unchanged(tmp_path: Path) -> None:
    archived = tmp_path / "docs/archive/pre-hygiene/docs/references/record.md"
    archived.parent.mkdir(parents=True)
    original = b"# frozen negative result\n"
    archived.write_bytes(original)
    manifest = {
        "baseline_sha": "1" * 40,
        "baseline_paths": ["docs/references/record.md"],
        "files": {"docs/references/record.md": {
            "archived_path": archived.relative_to(tmp_path).as_posix(),
            "sha256": sha256(original).hexdigest(), "size": len(original),
        }},
    }
    (tmp_path / "docs/archive/manifest.json").write_text(json.dumps(manifest))
    assert check_archived_snapshot(tmp_path) == []
    archived.write_bytes(original.replace(b"negative", b"positive"))
    assert any("archive bytes changed" in error for error in check_archived_snapshot(tmp_path))


def test_inventory_resolves_relative_import_aliases_without_losing_the_member() -> None:
    tree = ast.parse("from . import owner as selected\nfrom ..domain import Fact")
    names = imports(tree, "sample.application.commands", False)
    assert "sample.application.owner" in names
    assert "sample.domain.Fact" in names


def test_inventory_rejects_a_removed_internal_module_instead_of_resolving_its_parent() -> None:
    tree = ast.parse("from tests.contracts.removed_fixture import existing_helper")
    assert unresolved_imports(tree, "tests.consumer", False, {"tests", "tests.contracts"}) == [
        "tests.contracts.removed_fixture"
    ]


def test_inventory_rejects_a_removed_script_imported_through_its_namespace() -> None:
    tree = ast.parse("from scripts import removed_runner as cli")
    assert unresolved_imports(tree, "tests.consumer", False, {"scripts"}) == [
        "scripts.removed_runner"
    ]
