from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from market_regime_alpha.persistence.migration_report import (
    CHECKSUM_FILE,
    MigrationReport,
    MigrationReportPublisher,
    MigrationReportReader,
)


def _report() -> MigrationReport:
    return MigrationReport.create(
        manifest_hash="sha256:" + "1" * 64,
        created_at=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        code_revision="a" * 40,
        postgres_server_version="16.14",
        postgres_schema="test_authority",
        applied_migrations=((1, "one", "2" * 64),),
        sources=(),
        tables=(),
        sequence_repairs=(),
    )


def test_migration_report_publish_read_and_idempotency(tmp_path: Path) -> None:
    report = _report()
    publisher = MigrationReportPublisher()

    first = publisher.publish(report, tmp_path)
    second = publisher.publish(report, tmp_path)

    assert first == second
    assert MigrationReportReader().read(first) == report


def test_migration_report_rejects_tamper_and_extra_files(tmp_path: Path) -> None:
    report_path = MigrationReportPublisher().publish(_report(), tmp_path)
    (report_path / CHECKSUM_FILE).write_text("0" * 64 + "  migration-report.json\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        MigrationReportReader().read(report_path)

    report_path = MigrationReportPublisher().publish(_report(), tmp_path / "second")
    (report_path / "extra.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="file set"):
        MigrationReportReader().read(report_path)
