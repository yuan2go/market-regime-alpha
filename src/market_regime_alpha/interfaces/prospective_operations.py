"""Machine-local research operation intent; never business or admission Authority."""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import UUID

import market_regime_alpha
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class ProspectiveOperationConfig:
    version: int
    database_name: str
    database_oid: int
    cluster_identity: str
    schema_epoch: str
    baseline_checksum: str
    catalog_checksum: str
    artifact_root_binding_sha256: str
    source_sha256: str
    series_code: str
    target_definition_id: str
    target_sha256: str
    backup_directory: str
    backup_sha256: str
    backup_receipt_sha256: str
    maximum_backup_age_hours: int
    minimum_free_bytes: int
    minimum_calendar_sessions: int
    maximum_pool_connections: int
    provider_kind: str
    provider_timeout_seconds: int
    provider_maximum_rows: int
    provider_maximum_response_bytes: int
    maximum_attempts_per_tick: int
    maximum_tick_seconds: int
    code_sha: str
    actor_id: str
    worker_id: str
    lease_seconds: int
    wakeup_seconds: int

    def __post_init__(self) -> None:
        integers = {
            "version": (1, 1), "database_oid": (1, 2**32 - 1),
            "maximum_backup_age_hours": (1, 168),
            "minimum_free_bytes": (1, 2**63 - 1),
            "minimum_calendar_sessions": (3, 512),
            "maximum_pool_connections": (1, 4),
            "provider_timeout_seconds": (1, 30),
            "provider_maximum_rows": (1, 100_000),
            "provider_maximum_response_bytes": (1, 33_554_432),
            "maximum_attempts_per_tick": (1, 512),
            "maximum_tick_seconds": (1, 3600),
            "lease_seconds": (1, 3600), "wakeup_seconds": (1, 3600),
        }
        for name, (minimum, maximum) in integers.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("operation configuration has an invalid numeric budget")
        for item in fields(self):
            if item.name not in integers:
                value = getattr(self, item.name)
                if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
                    raise ValueError("operation configuration has an invalid text field")
        for name in ("baseline_checksum", "catalog_checksum", "artifact_root_binding_sha256",
                     "source_sha256", "target_sha256", "backup_sha256", "backup_receipt_sha256"):
            if re.fullmatch("[0-9a-f]{64}", getattr(self, name)) is None:
                raise ValueError("operation configuration requires exact content hashes")
        if re.fullmatch("[0-9a-f]{40}", self.code_sha) is None:
            raise ValueError("operation configuration requires an exact code SHA")
        if not self.cluster_identity.isdecimal() or not Path(self.backup_directory).is_absolute():
            raise ValueError("operation configuration requires exact cluster and local backup")
        if self.schema_epoch != "MRA_REFOUNDATION_1" or self.provider_kind != "BAOSTOCK_EXPLORATORY":
            raise ValueError("operation configuration uses an unsupported schema or Provider")
        try:
            UUID(self.target_definition_id)
        except ValueError as exc:
            raise ValueError("operation configuration requires an exact Target") from exc
        if self.lease_seconds <= self.provider_timeout_seconds:
            raise ValueError("operation configuration lease must exceed one Provider call")

    @property
    def content_sha256(self) -> str:
        return str(canonical_json_sha256(self))


def load_operation_config(path: Path) -> ProspectiveOperationConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("operation configuration cannot be read") from exc
    expected = {item.name for item in fields(ProspectiveOperationConfig)}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("operation configuration has missing or unknown fields")
    return ProspectiveOperationConfig(**data)


def implementation_source_sha256() -> str:
    """Content identity is independent of checkout/install path and bytecode."""
    root = Path(market_regime_alpha.__file__).resolve().parent
    roster = [
        (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*")) if path.is_file() and path.suffix in {".py", ".sql"}
    ]
    return str(canonical_json_sha256(roster))


def validate_operation_arguments(config: ProspectiveOperationConfig, arguments: object) -> None:
    for name in ("series_code", "code_sha", "actor_id", "worker_id", "lease_seconds", "wakeup_seconds"):
        value = getattr(arguments, name)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("operation configuration differs from service arguments")
        if value != getattr(config, name):
            raise ValueError("operation configuration differs from service arguments")
    if getattr(arguments, "expected_database_name") != config.database_name:
        raise ValueError("operation configuration differs from expected database")
