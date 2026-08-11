from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from scripts.apply_postgres_migrations import main as apply_migrations_main
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory as postgres_factory,
)


ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs/operations/Runtime-Runbook.md"


def test_postgres_runbook_references_existing_repository_commands() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    scripts = set(re.findall(r"(?<!tests/)scripts/[a-z0-9_]+\.py", text))

    assert {
        "scripts/bootstrap_postgres.py",
        "scripts/apply_postgres_migrations.py",
        "scripts/check_docs_links.py",
    } <= scripts
    assert all((ROOT / relative).is_file() for relative in scripts)
    assert "scripts/migrate_sqlite_to_postgres.py" not in text
    assert "--sqlite-database" not in text
    assert "PostgreSQL Authority Only" in text


def test_ci_provides_postgres_only_to_test_step() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "image: postgres:16.14-bookworm" in workflow
    assert "MARKET_REGIME_ALPHA_TEST_DATABASE_URL" in workflow
    assert workflow.index("MARKET_REGIME_ALPHA_TEST_DATABASE_URL") > workflow.index("- name: Run tests")
    assert "MARKET_REGIME_ALPHA_DATABASE_URL" not in workflow


def test_tracked_files_exclude_operator_credentials() -> None:
    tracked = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    forbidden = (
        "novel_forge" + ":" + "novel_forge",
        "postgresql://" + "novel_forge" + ":",
        "MARKET_REGIME_ALPHA_DATABASE_URL=" + "postgresql://market_regime_alpha:",
    )
    violations = []
    for raw_path in tracked:
        if not raw_path:
            continue
        path = ROOT / raw_path.decode("utf-8")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(value in text for value in forbidden):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_status_and_runbook_keep_authority_ceiling_explicit() -> None:
    status = (ROOT / "docs/status/Current-State.md").read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    for declaration in (
        "automatic_order_execution = false",
        "broker_integration_proven = false",
        "entry_model_empirically_validated = false",
        "production_ready = false",
    ):
        assert declaration in status
    assert "Expected head: migration 063" in runbook
    assert "Production qualification is currently forced closed" in runbook
    assert "no alternate persistent backend" in runbook


def test_apply_migrations_honors_explicit_application_schema(
    postgres_factory: PostgresConnectionFactory,
    capsys,
) -> None:
    assert apply_migrations_main(
        [
            "--database-url",
            os.environ[TEST_DATABASE_URL_ENV],
            "--database-schema",
            postgres_factory.application_schema,
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["postgres_schema"] == postgres_factory.application_schema
    assert output["latest_migration"] == 63
    assert output["authority_table_count"] == 231
