"""Read-only operational evidence projections; never business Authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256


class EvidenceSnapshotPort(Protocol):
    def snapshot(self) -> dict[str, Any]: ...


class EvidenceIntegrityPort(Protocol):
    def verify(self, references: list[dict[str, Any]]) -> dict[str, Any]: ...


class EvidenceBackupPort(Protocol):
    def records(self, directory: Path, database: dict[str, Any]) -> dict[str, Any]: ...
    def plan(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]: ...
    def backup(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]: ...
    def restore_check(self, bundle: Path) -> dict[str, Any]: ...


class EvidenceApplication:
    def __init__(
        self,
        source: EvidenceSnapshotPort,
        integrity: EvidenceIntegrityPort,
        artifact_root: Path,
        backup: EvidenceBackupPort,
        verify_archive: Callable[[UUID], Any],
        verify_backtest: Callable[[UUID], Any],
    ) -> None:
        self._source = source
        self._integrity = integrity
        self._root = artifact_root
        self._backup = backup
        self._verify_archive = verify_archive
        self._verify_backtest = verify_backtest

    def inventory(self, *, logical_role: str = "UNSPECIFIED", records_directory: Path | None = None) -> dict[str, Any]:
        snapshot = self._source.snapshot()
        snapshot["database"]["logical_role"] = logical_role
        references = snapshot.pop("artifacts")
        records = self._backup.records(records_directory, snapshot["database"]) if records_directory is not None else {}
        return {
            **snapshot,
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_INDEX",
            "artifact_root": {
                "path": str(self._root),
                "binding_sha256": canonical_json_sha256(
                    {
                        "database": snapshot["database"],
                        "path": str(self._root),
                    }
                ),
            },
            "artifact_count": len(references),
            "artifact_bytes": sum(item["size_bytes"] for item in references),
            "artifact_roster_sha256": canonical_json_sha256(references),
            "latest_successful_backup": None,
            "last_restore_drill_at": None,
            "last_artifact_integrity_scan": None,
            "status": "INVENTORIED_PHYSICAL_VERIFICATION_REQUIRED",
            **records,
        }

    def verify(self) -> dict[str, Any]:
        snapshot = self._source.snapshot()
        result = self._integrity.verify(snapshot["artifacts"])
        reconciliations = self._reconcile(snapshot) if result["matched"] else []
        result["mismatch_count"] += sum(item["mismatch_count"] for item in reconciliations)
        result["matched"] = result["mismatch_count"] == 0
        return {
            **result,
            "reconciliations": reconciliations,
            "database": snapshot["database"],
            "observed_at": snapshot["observed_at"],
            "artifact_root": str(self._root.resolve()),
            "artifact_roster_sha256": canonical_json_sha256(snapshot["artifacts"]),
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_INDEX",
        }

    def backup_plan(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]:
        return self._backup.plan(directory, expected_name=expected_name, expected_oid=expected_oid, minimum_free_bytes=minimum_free_bytes)

    def backup(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]:
        return self._backup.backup(directory, expected_name=expected_name, expected_oid=expected_oid, minimum_free_bytes=minimum_free_bytes)

    def restore_check(self, bundle: Path) -> dict[str, Any]:
        result = self._backup.restore_check(bundle)
        reconciliations = self._reconcile(self._source.snapshot()) if result["matched"] else []
        result["mismatch_count"] += sum(item["mismatch_count"] for item in reconciliations)
        result["matched"] = result["mismatch_count"] == 0
        return {**result, "reconciliations": reconciliations}

    def _reconcile(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for kind, roster, key, verify in (
            ("ARCHIVE", snapshot["archives"], "market_archive_id", self._verify_archive),
            ("BACKTEST", snapshot["backtests"], "exploratory_backtest_run_id", self._verify_backtest),
        ):
            for item in roster:
                observed = verify(UUID(item[key]))
                results.append({"kind": kind, "id": item[key], "matched": observed.matched, "mismatch_count": observed.mismatch_count})
        return results
