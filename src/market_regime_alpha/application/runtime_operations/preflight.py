"""Typed engineering-readiness report; it never grants business authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.free_data_runtime import (
    FREE_DATA_MODEL_SLOTS,
    FREE_DATA_RUNTIME_SCOPE,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
    load_controlled_trading_calendar,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
)
from market_regime_alpha.evidence.canonical import canonical_datetime, require_text
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import (
    PostgresMigrator,
    load_packaged_migrations,
)
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


class PreflightStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


_STATUS_RANK = {
    PreflightStatus.READY: 0,
    PreflightStatus.DEGRADED: 1,
    PreflightStatus.BLOCKED: 2,
}


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    check_name: str
    status: PreflightStatus
    reason_codes: tuple[str, ...]
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_text("check_name", self.check_name)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Preflight reason codes must be unique and sorted")
        for reason in self.reason_codes:
            require_text("reason_code", reason)
        if self.status is PreflightStatus.READY and self.reason_codes:
            raise ValueError("READY Preflight check cannot have reason codes")

    @classmethod
    def ready(
        cls,
        check_name: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> PreflightCheck:
        return cls(check_name, PreflightStatus.READY, (), details or {})

    @classmethod
    def degraded(
        cls,
        check_name: str,
        *,
        reason_codes: tuple[str, ...],
        details: Mapping[str, Any] | None = None,
    ) -> PreflightCheck:
        return cls(
            check_name,
            PreflightStatus.DEGRADED,
            tuple(sorted(set(reason_codes))),
            details or {},
        )

    @classmethod
    def blocked(
        cls,
        check_name: str,
        *,
        reason_codes: tuple[str, ...],
        details: Mapping[str, Any] | None = None,
    ) -> PreflightCheck:
        return cls(
            check_name,
            PreflightStatus.BLOCKED,
            tuple(sorted(set(reason_codes))),
            details or {},
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class PreflightReport:
    checked_at: datetime
    trading_date: date
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = "canonical-runtime-preflight/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "canonical-runtime-preflight/v1":
            raise ValueError("unsupported Canonical Runtime Preflight schema")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        names = tuple(item.check_name for item in self.checks)
        if names != tuple(sorted(set(names))):
            raise ValueError("Preflight checks must be unique and sorted")
        expected_status = max(
            (item.status for item in self.checks),
            key=lambda item: _STATUS_RANK[item],
            default=PreflightStatus.BLOCKED,
        )
        if self.status is not expected_status:
            raise ValueError("Preflight status does not match its checks")
        expected_reasons = tuple(
            sorted({reason for item in self.checks for reason in item.reason_codes})
        )
        if self.reason_codes != expected_reasons:
            raise ValueError("Preflight reasons do not match its checks")

    @classmethod
    def create(
        cls,
        *,
        checked_at: datetime,
        trading_date: date,
        checks: tuple[PreflightCheck, ...],
    ) -> PreflightReport:
        ordered = tuple(sorted(checks, key=lambda item: item.check_name))
        status = max(
            (item.status for item in ordered),
            key=lambda item: _STATUS_RANK[item],
            default=PreflightStatus.BLOCKED,
        )
        reasons = tuple(
            sorted({reason for item in ordered for reason in item.reason_codes})
        )
        return cls(
            checked_at=checked_at,
            trading_date=trading_date,
            status=status,
            checks=ordered,
            reason_codes=reasons,
        )

    @property
    def grants_trading_authority(self) -> bool:
        return False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checked_at": canonical_datetime(self.checked_at),
            "trading_date": self.trading_date.isoformat(),
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "checks": [item.to_canonical_dict() for item in self.checks],
            "authority": {
                "engineering_readiness_only": True,
                "grants_model_authority": False,
                "grants_entry_authority": False,
                "grants_broker_authority": False,
            },
        }


@dataclass(frozen=True, slots=True)
class RuntimePreflightRequest:
    trading_date: date
    runtime_mode: RuntimeAuthorityMode
    provider_profile_id: str
    operational_policy_effective_from: date
    artifact_root: Path
    runtime_configuration_path: Path
    trading_calendar_path: Path
    run_id: ArtifactId | None = None
    required_model_slots: tuple[str, ...] = tuple(
        sorted(set(FREE_DATA_MODEL_SLOTS.values()))
    )
    runtime_scope: str = FREE_DATA_RUNTIME_SCOPE
    minimum_free_bytes: int = 1_000_000_000
    maximum_clock_skew: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        require_text("provider_profile_id", self.provider_profile_id)
        require_text("runtime_scope", self.runtime_scope)
        if self.required_model_slots != tuple(
            sorted(set(self.required_model_slots))
        ):
            raise ValueError("required model slots must be unique and sorted")
        if (
            isinstance(self.minimum_free_bytes, bool)
            or self.minimum_free_bytes < 0
        ):
            raise ValueError("minimum_free_bytes must be non-negative")
        if self.maximum_clock_skew < timedelta(0):
            raise ValueError("maximum_clock_skew must be non-negative")


class CanonicalRuntimePreflight:
    """Read current operational dependencies without executing the Runtime."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Any | None = None,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._factory = factory
        self._clock = clock or (
            lambda: datetime.now(UTC).replace(microsecond=0)
        )

    def inspect(self, request: RuntimePreflightRequest) -> PreflightReport:
        if not isinstance(request, RuntimePreflightRequest):
            raise TypeError("request must be RuntimePreflightRequest")
        checked_at = self._clock()
        checks: list[PreflightCheck] = []
        db_time: datetime | None = None
        try:
            with self._factory.connection(read_only=True) as connection:
                row = connection.execute(
                    """
                    SELECT current_setting('server_version'),
                           current_setting('TimeZone'), clock_timestamp(),
                           timezone('Asia/Shanghai', clock_timestamp())
                    """
                ).fetchone()
            if row is None:
                raise RuntimeError("PostgreSQL clock probe returned no row")
            db_time = row[2]
            checks.append(
                PreflightCheck.ready(
                    "POSTGRESQL_CONNECTIVITY",
                    details={
                        "server_version": str(row[0]),
                        "database_timezone": str(row[1]),
                        "database_clock": canonical_datetime(db_time),
                        "trusted_timezone": "Asia/Shanghai",
                        "trusted_local_clock": row[3].isoformat(),
                    },
                )
            )
        except Exception as exc:
            checks.append(
                PreflightCheck.blocked(
                    "POSTGRESQL_CONNECTIVITY",
                    reason_codes=("POSTGRESQL_UNAVAILABLE",),
                    details={"error_type": type(exc).__name__},
                )
            )

        checks.append(self._migration_check())
        checks.append(self._schema_check())
        checks.append(self._clock_check(checked_at, db_time, request))
        checks.append(self._provider_check(request))
        checks.append(self._configuration_check(request))
        checks.append(self._policy_check(request))
        checks.append(self._governance_check(request))
        checks.append(self._artifact_root_check(request))
        checks.append(self._runtime_recovery_check(request, checked_at))
        return PreflightReport.create(
            checked_at=checked_at,
            trading_date=request.trading_date,
            checks=tuple(checks),
        )

    def _migration_check(self) -> PreflightCheck:
        packaged = load_packaged_migrations()
        try:
            # Constructor proves the packaged sequence itself is contiguous.
            PostgresMigrator(migrations=packaged)
            with self._factory.connection(read_only=True) as connection:
                rows = connection.execute(
                    """
                    SELECT version, name, checksum
                    FROM schema_migrations ORDER BY version
                    """
                ).fetchall()
            actual = tuple((int(row[0]), str(row[1]), str(row[2])) for row in rows)
            expected = tuple(
                (item.version, item.name, item.checksum) for item in packaged
            )
            if actual != expected:
                return PreflightCheck.blocked(
                    "MIGRATION_CONSISTENCY",
                    reason_codes=("MIGRATION_HEAD_OR_CHECKSUM_MISMATCH",),
                    details={
                        "expected_head": packaged[-1].version,
                        "actual_head": actual[-1][0] if actual else None,
                    },
                )
            return PreflightCheck.ready(
                "MIGRATION_CONSISTENCY",
                details={
                    "migration_head": packaged[-1].version,
                    "migration_name": packaged[-1].name,
                },
            )
        except Exception as exc:
            return PreflightCheck.blocked(
                "MIGRATION_CONSISTENCY",
                reason_codes=("MIGRATION_REGISTRY_UNAVAILABLE",),
                details={"error_type": type(exc).__name__},
            )

    def _schema_check(self) -> PreflightCheck:
        required = (
            "continuous_research_run",
            "continuous_runtime_tick",
            "continuous_runtime_event",
            "continuous_provider_attempt",
            "model_runtime_assignment",
            "research_daily_summary",
            "state_research_stage_authority",
        )
        try:
            with self._factory.connection(read_only=True) as connection:
                rows = connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = ANY(%s)
                    """,
                    (list(required),),
                ).fetchall()
            present = {str(row[0]) for row in rows}
            missing = tuple(sorted(set(required) - present))
            if missing:
                return PreflightCheck.blocked(
                    "RUNTIME_SCHEMA",
                    reason_codes=("RUNTIME_SCHEMA_INCOMPLETE",),
                    details={"missing_tables": list(missing)},
                )
            return PreflightCheck.ready(
                "RUNTIME_SCHEMA", details={"required_table_count": len(required)}
            )
        except Exception as exc:
            return PreflightCheck.blocked(
                "RUNTIME_SCHEMA",
                reason_codes=("RUNTIME_SCHEMA_UNAVAILABLE",),
                details={"error_type": type(exc).__name__},
            )

    def _clock_check(
        self,
        checked_at: datetime,
        db_time: datetime | None,
        request: RuntimePreflightRequest,
    ) -> PreflightCheck:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            return PreflightCheck.blocked(
                "TRUSTED_CLOCK",
                reason_codes=("RUNTIME_CLOCK_NOT_TIMEZONE_AWARE",),
            )
        if db_time is None:
            return PreflightCheck.blocked(
                "TRUSTED_CLOCK",
                reason_codes=("DATABASE_CLOCK_UNAVAILABLE",),
            )
        skew_seconds = abs((checked_at - db_time).total_seconds())
        if skew_seconds > request.maximum_clock_skew.total_seconds():
            return PreflightCheck.blocked(
                "TRUSTED_CLOCK",
                reason_codes=("CLOCK_SKEW_EXCEEDS_POLICY",),
                details={
                    "clock_skew_seconds": skew_seconds,
                    "maximum_clock_skew_seconds": (
                        request.maximum_clock_skew.total_seconds()
                    ),
                },
            )
        return PreflightCheck.ready(
            "TRUSTED_CLOCK",
            details={"clock_skew_seconds": skew_seconds},
        )

    def _provider_check(
        self, request: RuntimePreflightRequest
    ) -> PreflightCheck:
        if request.provider_profile_id != TENCENT_FREE_OPERATIONAL_PROFILE_ID:
            return PreflightCheck.blocked(
                "PROVIDER_CONFIGURATION",
                reason_codes=("NON_CANONICAL_PROVIDER_PROFILE",),
                details={
                    "configured_profile": request.provider_profile_id,
                    "required_profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID,
                    "automatic_fallback": False,
                },
            )
        return PreflightCheck.ready(
            "PROVIDER_CONFIGURATION",
            details={
                "provider_profile_id": request.provider_profile_id,
                "automatic_fallback": False,
            },
        )

    def _configuration_check(
        self, request: RuntimePreflightRequest
    ) -> PreflightCheck:
        reasons: set[str] = set()
        details: dict[str, Any] = {}
        try:
            configuration = load_controlled_runtime_configuration(
                request.runtime_configuration_path.resolve()
            )
            details["runtime_configuration_id"] = str(
                configuration.configuration_id
            )
            details["runtime_configuration_hash"] = (
                configuration.configuration_hash
            )
        except Exception as exc:
            reasons.add("RUNTIME_CONFIGURATION_INVALID")
            details["runtime_configuration_error"] = type(exc).__name__
            configuration = None
        try:
            calendar = load_controlled_trading_calendar(
                request.trading_calendar_path.resolve()
            )
            details["trading_calendar_id"] = str(calendar.artifact_id)
            details["trading_calendar_hash"] = calendar.content_hash
            details["trading_calendar_timezone"] = calendar.timezone_name
            if not calendar.contains(request.trading_date):
                reasons.add("TRADING_DATE_NOT_IN_CALENDAR")
        except Exception as exc:
            reasons.add("TRADING_CALENDAR_INVALID")
            details["trading_calendar_error"] = type(exc).__name__
            calendar = None
        if request.run_id is not None:
            try:
                with self._factory.connection(read_only=True) as connection:
                    row = connection.execute(
                        """
                        SELECT command_json FROM continuous_research_run
                        WHERE run_id = %s
                        """,
                        (str(request.run_id),),
                    ).fetchone()
                if row is None:
                    reasons.add("RUNTIME_RUN_NOT_FOUND")
                else:
                    import json

                    command = json.loads(str(row[0]))
                    if configuration is not None and (
                        command["research_configuration_id"]
                        != str(configuration.configuration_id)
                        or command["research_configuration_hash"]
                        != configuration.configuration_hash
                    ):
                        reasons.add("RUNTIME_CONFIGURATION_LINEAGE_MISMATCH")
                    if calendar is not None and (
                        command["trading_calendar_id"] != str(calendar.artifact_id)
                        or command["trading_calendar_hash"] != calendar.content_hash
                    ):
                        reasons.add("TRADING_CALENDAR_LINEAGE_MISMATCH")
            except Exception as exc:
                reasons.add("RUNTIME_CONFIGURATION_LINEAGE_UNAVAILABLE")
                details["lineage_error"] = type(exc).__name__
        if reasons:
            return PreflightCheck.blocked(
                "RUNTIME_CONFIGURATION",
                reason_codes=tuple(sorted(reasons)),
                details=details,
            )
        return PreflightCheck.ready("RUNTIME_CONFIGURATION", details=details)

    def _policy_check(self, request: RuntimePreflightRequest) -> PreflightCheck:
        if request.operational_policy_effective_from > request.trading_date:
            return PreflightCheck.blocked(
                "OPERATIONAL_POLICY",
                reason_codes=("OPERATIONAL_POLICY_NOT_EFFECTIVE",),
                details={
                    "effective_from": (
                        request.operational_policy_effective_from.isoformat()
                    )
                },
            )
        return PreflightCheck.ready(
            "OPERATIONAL_POLICY",
            details={
                "effective_from": request.operational_policy_effective_from.isoformat(),
                "formal_pit": False,
            },
        )

    def _governance_check(
        self, request: RuntimePreflightRequest
    ) -> PreflightCheck:
        repository = PostgresModelGovernanceRepository(self._factory)
        missing: list[str] = []
        duplicate: list[str] = []
        for slot in request.required_model_slots:
            assignments = repository.list_assignments(
                runtime_scope=request.runtime_scope,
                model_slot=slot,
                purpose=request.runtime_mode.runtime_purpose,
            )
            champions = tuple(
                item
                for item in assignments
                if item.lane.value == "CHAMPION" and item.status.value == "ACTIVE"
            )
            if not champions:
                missing.append(slot)
            elif len(champions) > 1:
                duplicate.append(slot)
        reasons: set[str] = set()
        if missing:
            reasons.add("CHAMPION_AUTHORITY_MISSING")
        if duplicate:
            reasons.add("DUPLICATE_CHAMPION_AUTHORITY")
        details = {
            "runtime_scope": request.runtime_scope,
            "runtime_purpose": request.runtime_mode.runtime_purpose.value,
            "required_slots": list(request.required_model_slots),
            "missing_slots": missing,
            "duplicate_slots": duplicate,
        }
        if reasons:
            return PreflightCheck.blocked(
                "MODEL_GOVERNANCE",
                reason_codes=tuple(sorted(reasons)),
                details=details,
            )
        return PreflightCheck.ready("MODEL_GOVERNANCE", details=details)

    def _artifact_root_check(
        self, request: RuntimePreflightRequest
    ) -> PreflightCheck:
        root = request.artifact_root.resolve()
        if not root.is_dir():
            return PreflightCheck.blocked(
                "ARTIFACT_STORAGE",
                reason_codes=("ARTIFACT_ROOT_MISSING",),
                details={"artifact_root": str(root)},
            )
        writable = os.access(root, os.W_OK | os.X_OK)
        usage = shutil.disk_usage(root)
        reasons: set[str] = set()
        if not writable:
            reasons.add("ARTIFACT_ROOT_NOT_WRITABLE")
        if usage.free < request.minimum_free_bytes:
            reasons.add("ARTIFACT_DISK_CAPACITY_LOW")
        details = {
            "artifact_root": str(root),
            "free_bytes": usage.free,
            "minimum_free_bytes": request.minimum_free_bytes,
            "writable": writable,
        }
        if reasons:
            return PreflightCheck.blocked(
                "ARTIFACT_STORAGE",
                reason_codes=tuple(sorted(reasons)),
                details=details,
            )
        return PreflightCheck.ready("ARTIFACT_STORAGE", details=details)

    def _runtime_recovery_check(
        self,
        request: RuntimePreflightRequest,
        checked_at: datetime,
    ) -> PreflightCheck:
        if request.run_id is None:
            return PreflightCheck.degraded(
                "RUNTIME_RECOVERY",
                reason_codes=("RUN_SCOPE_NOT_SUPPLIED",),
                details={"recoverable_tick": None},
            )
        try:
            with self._factory.connection(read_only=True) as connection:
                row = connection.execute(
                    """
                    SELECT tick_id, status, claim_id, fencing_token,
                           lease_expires_at, retry_at
                    FROM continuous_runtime_tick
                    WHERE run_id = %s
                      AND status IN ('PENDING', 'IN_PROGRESS', 'FAILED')
                    ORDER BY tick_sequence LIMIT 1
                    """,
                    (str(request.run_id),),
                ).fetchone()
            if row is None:
                return PreflightCheck.ready(
                    "RUNTIME_RECOVERY", details={"recoverable_tick": None}
                )
            details = {
                "recoverable_tick": str(row[0]),
                "status": str(row[1]),
                "claim_id": None if row[2] is None else str(row[2]),
                "fencing_token": int(row[3]),
                "lease_expires_at": (
                    None if row[4] is None else canonical_datetime(row[4])
                ),
                "retry_at": (
                    None if row[5] is None else canonical_datetime(row[5])
                ),
            }
            if row[1] == "IN_PROGRESS" and row[4] > checked_at:
                return PreflightCheck.blocked(
                    "RUNTIME_RECOVERY",
                    reason_codes=("ACTIVE_TICK_LEASE",),
                    details=details,
                )
            if row[1] == "IN_PROGRESS":
                return PreflightCheck.degraded(
                    "RUNTIME_RECOVERY",
                    reason_codes=("STALE_LEASE_RECOVERABLE",),
                    details=details,
                )
            return PreflightCheck.degraded(
                "RUNTIME_RECOVERY",
                reason_codes=("UNFINISHED_TICK_RECOVERABLE",),
                details=details,
            )
        except Exception as exc:
            return PreflightCheck.blocked(
                "RUNTIME_RECOVERY",
                reason_codes=("RUNTIME_RECOVERY_STATE_UNAVAILABLE",),
                details={"error_type": type(exc).__name__},
            )


__all__ = [
    "CanonicalRuntimePreflight",
    "PreflightCheck",
    "PreflightReport",
    "PreflightStatus",
    "RuntimePreflightRequest",
]
