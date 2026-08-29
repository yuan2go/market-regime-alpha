"""Schema-epoch discovery, bootstrap, verification, and explicit recreate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from importlib.resources import files
import json
import re
import secrets
from typing import Any, Final

import psycopg

from market_regime_alpha.market.domain import (
    BarTimeframe,
    CaptureStatus,
    CorporateActionType,
    EvidenceScope,
    GapFactKind,
    GapKind,
    GapReasonCode,
    InstrumentFactKind,
    InstrumentType,
    ListingStatus,
    MarketFactKind,
    MembershipStatus,
    PriceBasis,
    ProviderKind,
    SecurityStatus,
    SourceAvailabilityStatus,
    SpecialTreatmentStatus,
)
from market_regime_alpha.selection.domain import (
    CriterionOperator,
    CriterionResult,
    CriterionValueKind,
    EligibilityRuleKind,
    EligibilityStatus,
    MarketEvidenceStatus,
    UniverseMembershipStatus,
)
from market_regime_alpha.research_qualification.domain import (
    DatasetSourceRole,
    FeatureAvailabilityRule,
    FeatureCellStatus,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)
from market_regime_alpha.shared.errors import MraError
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes


APPLICATION_SCHEMA: Final = "mra"
SCHEMA_EPOCH: Final = "MRA_REFOUNDATION_1"
BASELINE_VERSION: Final = 1
BASELINE_NAME: Final = "001_baseline"
BASELINE_RELEASE_STATE: Final = "DRAFT"
_SCHEMA_COMMENT: Final = (
    "Market Regime Alpha MRA_REFOUNDATION_1 unreleased draft authority schema"
)
_BOOTSTRAP_LOCK_KEY: Final = "market-regime-alpha:mra:bootstrap"

EXPECTED_FOUNDATION_TABLES: Final[frozenset[str]] = frozenset(
    {
        "schema_epoch",
        "schema_migrations",
        "command_receipt",
        "runtime_schedule",
        "runtime_run",
        "runtime_step",
        "runtime_step_dependency",
        "runtime_attempt",
        "audit_event",
        "artifact",
        "artifact_dependency",
        "artifact_verification",
        "artifact_gc_candidate",
    }
)

EXPECTED_MARKET_TABLES: Final[frozenset[str]] = frozenset(
    {
        "provider",
        "provider_product",
        "data_capture",
        "instrument",
        "instrument_identifier",
        "trading_session",
        "classification",
        "classification_membership_revision",
        "market_bar_revision",
        "instrument_fact_revision",
        "corporate_action_revision",
        "source_gap",
    }
)

EXPECTED_SELECTION_CORE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "universe",
        "universe_revision",
        "universe_member",
        "eligibility_policy",
        "eligibility_rule",
        "eligibility_assessment",
        "eligibility_reason",
    }
)

EXPECTED_CANDIDATE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "candidate_policy",
        "candidate_policy_component",
        "candidate_set",
        "candidate",
        "candidate_score_component",
    }
)

EXPECTED_SELECTION_TABLES: Final[frozenset[str]] = (
    EXPECTED_SELECTION_CORE_TABLES | EXPECTED_CANDIDATE_TABLES
)

EXPECTED_RESEARCH_DEFINITION_TABLES: Final[frozenset[str]] = frozenset(
    {
        "dataset",
        "dataset_source",
        "feature_definition",
    }
)

EXPECTED_TARGET_TABLES: Final[frozenset[str]] = (
    EXPECTED_FOUNDATION_TABLES
    | EXPECTED_MARKET_TABLES
    | EXPECTED_SELECTION_TABLES
    | EXPECTED_RESEARCH_DEFINITION_TABLES
)

_LEGACY_TABLE_SIGNATURES: Final[frozenset[str]] = frozenset(
    {
        "continuous_research_run",
        "continuous_runtime_tick",
        "governance_commands",
        "lifecycle_runs",
        "model_registrations",
        "pit_authority_action",
        "position_books",
        "state_current_pointer",
    }
)

_REFERENCE_VOCABULARY: Final[dict[str, tuple[str, ...]]] = {
    "provider_kind": tuple(item.value for item in ProviderKind),
    "instrument_type": tuple(item.value for item in InstrumentType),
    "market_fact_kind": tuple(item.value for item in MarketFactKind),
    "instrument_fact_kind": tuple(item.value for item in InstrumentFactKind),
    "gap_fact_kind": tuple(item.value for item in GapFactKind),
    "price_basis": tuple(item.value for item in PriceBasis),
    "bar_timeframe": tuple(item.value for item in BarTimeframe),
    "capture_status": tuple(item.value for item in CaptureStatus),
    "corporate_action_type": tuple(item.value for item in CorporateActionType),
    "runtime_step_kind": (
        "CAPTURE",
        "NORMALIZE_PIT",
        "FREEZE_UNIVERSE",
        "ASSESS_ELIGIBILITY",
        "REGISTER_DATASET",
        "BUILD_CANDIDATE_SET",
        "ASSESS_CONTEXT",
        "SIGNAL_AND_FORECAST",
        "DECIDE_AND_RISK",
        "PERSIST_DECISION",
        "SETTLE_OUTCOME",
        "ATTRIBUTE",
        "ASSESS_RESEARCH",
    ),
    "runtime_mode": (
        "OPERATIONAL",
        "HISTORICAL",
        "REPLAY",
        "SHADOW",
        "PROSPECTIVE",
    ),
    "external_effect_class": (
        "NONE",
        "PURE_READ",
        "CONTENT_PUT",
        "IDEMPOTENT_REMOTE_COMMAND",
        "NON_IDEMPOTENT_REMOTE_COMMAND",
        "OBSERVATION_ONLY",
    ),
    "fact_evidence_scope": tuple(item.value for item in EvidenceScope),
    "fact_value_kind": ("STATUS", "DECIMAL"),
    "membership_status": tuple(item.value for item in MembershipStatus),
    "security_status": tuple(item.value for item in SecurityStatus),
    "listing_status": tuple(item.value for item in ListingStatus),
    "special_treatment_status": tuple(
        item.value for item in SpecialTreatmentStatus
    ),
    "source_availability_status": tuple(
        item.value for item in SourceAvailabilityStatus
    ),
    "source_gap_kind": tuple(item.value for item in GapKind),
    "source_gap_reason": tuple(item.value for item in GapReasonCode),
    "universe_membership_status": tuple(
        item.value for item in UniverseMembershipStatus
    ),
    "selection_market_evidence_status": tuple(
        item.value for item in MarketEvidenceStatus
    ),
    "eligibility_status": tuple(item.value for item in EligibilityStatus),
    "eligibility_criterion_result": tuple(item.value for item in CriterionResult),
    "eligibility_rule_kind": tuple(item.value for item in EligibilityRuleKind),
    "eligibility_rule_value_kind": tuple(
        item.value
        for item in CriterionValueKind
        if item is not CriterionValueKind.MISSING
    ),
    "eligibility_observed_value_kind": tuple(
        item.value for item in CriterionValueKind
    ),
    "eligibility_operator": tuple(item.value for item in CriterionOperator),
    "feature_value_type": tuple(item.value for item in FeatureValueType),
    "feature_interval_unit": tuple(item.value for item in FeatureIntervalUnit),
    "feature_source_requirement": tuple(
        item.value for item in FeatureSourceRequirement
    ),
    "feature_availability_rule": tuple(
        item.value for item in FeatureAvailabilityRule
    ),
    "feature_missingness_policy": tuple(
        item.value for item in FeatureMissingnessPolicy
    ),
    "feature_cell_status": tuple(item.value for item in FeatureCellStatus),
    "dataset_source_role": tuple(item.value for item in DatasetSourceRole),
}


class SchemaError(MraError):
    code = "SCHEMA_ERROR"


class SchemaMissingError(SchemaError):
    code = "SCHEMA_MISSING"


class SchemaEpochMismatchError(SchemaError):
    code = "SCHEMA_EPOCH_MISMATCH"


class SchemaChecksumMismatchError(SchemaError):
    code = "SCHEMA_CHECKSUM_MISMATCH"


class LegacySchemaPresentError(SchemaError):
    code = "LEGACY_SCHEMA_PRESENT"


class UnexpectedCatalogError(SchemaError):
    code = "UNEXPECTED_CATALOG_OBJECTS"


class CatalogDriftError(SchemaError):
    code = "CATALOG_DRIFT"


class UnsafeRecreateError(SchemaError):
    code = "UNSAFE_RECREATE"


class RecreatePlanStaleError(SchemaError):
    code = "RECREATE_PLAN_STALE"


@dataclass(frozen=True, slots=True)
class DatabaseIdentity:
    database_name: str
    database_oid: int
    database_owner: str
    connected_role: str


@dataclass(frozen=True, slots=True)
class SchemaVerification:
    created: bool
    epoch: str
    schema_name: str
    release_state: str
    baseline_version: int
    baseline_checksum: str
    seed_checksum: str
    catalog_checksum: str
    reference_vocabulary_checksum: str
    tables: frozenset[str]
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class RecreateAuthorization:
    expected_database_name: str
    expected_database_oid: int
    operator_id: str
    reason: str
    backup_attestation: str

    def __post_init__(self) -> None:
        for name, value in (
            ("expected_database_name", self.expected_database_name),
            ("operator_id", self.operator_id),
            ("reason", self.reason),
            ("backup_attestation", self.backup_attestation),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if isinstance(self.expected_database_oid, bool) or self.expected_database_oid <= 0:
            raise ValueError("expected_database_oid must be positive")


@dataclass(frozen=True, slots=True)
class RecreatePlan:
    database_name: str
    database_oid: int
    database_owner: str
    connected_role: str
    application_schema: str
    schema_owner: str
    detected_epoch: str
    detected_schema_name: str
    detected_release_state: str
    detected_baseline_version: int
    detected_baseline_checksum: str
    detected_seed_checksum: str
    detected_reference_vocabulary_checksum: str
    catalog_checksum: str
    catalog_objects: tuple[str, ...]
    active_connection_pids: tuple[int, ...]
    unexpected_objects: tuple[str, ...]
    operator_id: str
    reason: str
    backup_attestation: str
    generated_at: datetime
    expires_at: datetime
    nonce: str
    plan_hash: str
    challenge: str

    def __post_init__(self) -> None:
        for name in (
            "database_name",
            "database_owner",
            "connected_role",
            "application_schema",
            "schema_owner",
            "detected_epoch",
            "detected_schema_name",
            "detected_release_state",
            "operator_id",
            "reason",
            "backup_attestation",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if isinstance(self.database_oid, bool) or self.database_oid <= 0:
            raise ValueError("database_oid must be positive")
        if (
            isinstance(self.detected_baseline_version, bool)
            or self.detected_baseline_version <= 0
        ):
            raise ValueError("detected_baseline_version must be positive")
        for name in (
            "detected_baseline_checksum",
            "detected_seed_checksum",
            "detected_reference_vocabulary_checksum",
            "catalog_checksum",
            "plan_hash",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if not isinstance(self.nonce, str) or not re.fullmatch(
            r"[0-9a-f]{32}", self.nonce
        ):
            raise ValueError("nonce must be 128-bit lowercase hexadecimal")
        if not isinstance(self.challenge, str) or not re.fullmatch(
            r"[0-9a-f]{24}", self.challenge
        ):
            raise ValueError("challenge must be 96-bit lowercase hexadecimal")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        if not self.generated_at < self.expires_at <= self.generated_at + timedelta(
            hours=1
        ):
            raise ValueError("recreate plan expiry must be within one hour")
        if (
            not isinstance(self.catalog_objects, tuple)
            or not self.catalog_objects
            or any(not isinstance(item, str) or not item for item in self.catalog_objects)
            or tuple(sorted(set(self.catalog_objects))) != self.catalog_objects
        ):
            raise ValueError("catalog_objects must be a non-empty sorted unique tuple")
        if (
            not isinstance(self.active_connection_pids, tuple)
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item <= 0
                for item in self.active_connection_pids
            )
        ):
            raise ValueError("active_connection_pids must contain positive integers")
        if (
            not isinstance(self.unexpected_objects, tuple)
            or any(not isinstance(item, str) or not item for item in self.unexpected_objects)
        ):
            raise ValueError("unexpected_objects must contain object identities")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, payload: str) -> RecreatePlan:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("recreate plan is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("recreate plan must be a JSON object")
        try:
            raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
            raw["expires_at"] = datetime.fromisoformat(raw["expires_at"])
            for key in (
                "catalog_objects",
                "active_connection_pids",
                "unexpected_objects",
            ):
                if not isinstance(raw[key], list):
                    raise ValueError(f"{key} must be a JSON array")
                raw[key] = tuple(raw[key])
            return cls(**raw)
        except (KeyError, TypeError) as exc:
            raise ValueError("recreate plan does not satisfy the required shape") from exc


@dataclass(frozen=True, slots=True)
class RecreateResult:
    plan_hash: str
    removed_application_schema: str
    removed_schema_owner: str
    removed_epoch: str
    removed_baseline_checksum: str
    removed_seed_checksum: str
    removed_catalog_checksum: str
    removed_catalog_objects: tuple[str, ...]
    verification: SchemaVerification


@dataclass(frozen=True, slots=True)
class _EpochRow:
    epoch_name: str
    schema_name: str
    release_state: str
    baseline_version: int
    baseline_checksum: str
    seed_checksum: str
    catalog_checksum: str
    reference_vocabulary_checksum: str


class SchemaManager:
    """Own the target epoch lifecycle without importing the legacy migrator."""

    def __init__(
        self,
        database_url: str,
        *,
        recreate_plan_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        if recreate_plan_ttl <= timedelta(0) or recreate_plan_ttl > timedelta(hours=1):
            raise ValueError("recreate_plan_ttl must be between zero and one hour")
        self._database_url = database_url
        self._recreate_plan_ttl = recreate_plan_ttl
        self._baseline_sql = _read_package_text("migrations", "001_baseline.sql")
        self._seed_sql = _read_package_text("seeds", "001_reference_seed.sql")
        self.baseline_checksum = sha256_bytes(self._baseline_sql.encode("utf-8"))
        self.seed_checksum = sha256_bytes(self._seed_sql.encode("utf-8"))
        self.reference_vocabulary_checksum = canonical_json_sha256(
            _REFERENCE_VOCABULARY
        )

    def database_identity(self) -> DatabaseIdentity:
        with self._connect(read_only=True) as connection:
            return _database_identity(connection)

    def bootstrap(self) -> SchemaVerification:
        """Create only an empty, allowed catalog; otherwise perform verify-only."""

        with self._connect() as connection:
            _take_bootstrap_lock(connection)
            _require_non_system_database(_database_identity(connection))
            if _schema_exists(connection, APPLICATION_SCHEMA):
                verification = self._verify_connection(connection, created=False)
                connection.commit()
                return verification
            self._require_empty_allowed_catalog(connection)
            connection.execute(self._baseline_sql)
            catalog_checksum = _target_catalog_checksum(connection)
            connection.execute(
                self._seed_sql,
                (
                    self.baseline_checksum,
                    self.seed_checksum,
                    catalog_checksum,
                    self.reference_vocabulary_checksum,
                    self.baseline_checksum,
                ),
            )
            verification = self._verify_connection(connection, created=True)
            connection.commit()
            return verification

    def verify(self) -> SchemaVerification:
        """Read-only preflight used by ordinary Runtime and inspection."""

        with self._connect(read_only=True) as connection:
            return self._verify_connection(connection, created=False)

    def plan_recreate(self, authorization: RecreateAuthorization) -> RecreatePlan:
        """Generate a short-lived, database- and catalog-bound destructive plan."""

        with self._connect() as connection:
            _take_bootstrap_lock(connection)
            identity = _database_identity(connection)
            _validate_recreate_identity(identity, authorization)
            _require_database_owner(identity)
            active_connection_pids = _require_no_other_connections(connection)
            unexpected_objects = self._require_no_external_catalog(connection)
            if not _schema_exists(connection, APPLICATION_SCHEMA):
                raise UnsafeRecreateError("target application schema does not exist")
            schema_owner = _schema_owner(connection)
            _require_schema_owner(identity, schema_owner)
            epoch = _read_epoch(connection)
            _validate_recreate_epoch(epoch)
            catalog_checksum = _target_catalog_checksum(connection)
            catalog_objects = _target_catalog_objects(connection)
            if catalog_checksum != epoch.catalog_checksum:
                raise CatalogDriftError(
                    "stored catalog checksum does not match the detected target schema"
                )
            now = _database_now(connection)
            nonce = secrets.token_hex(16)
            base = {
                "database_name": identity.database_name,
                "database_oid": identity.database_oid,
                "database_owner": identity.database_owner,
                "connected_role": identity.connected_role,
                "application_schema": APPLICATION_SCHEMA,
                "schema_owner": schema_owner,
                "detected_epoch": epoch.epoch_name,
                "detected_schema_name": epoch.schema_name,
                "detected_release_state": epoch.release_state,
                "detected_baseline_version": epoch.baseline_version,
                "detected_baseline_checksum": epoch.baseline_checksum,
                "detected_seed_checksum": epoch.seed_checksum,
                "detected_reference_vocabulary_checksum": (
                    epoch.reference_vocabulary_checksum
                ),
                "catalog_checksum": catalog_checksum,
                "catalog_objects": catalog_objects,
                "active_connection_pids": active_connection_pids,
                "unexpected_objects": unexpected_objects,
                "operator_id": authorization.operator_id,
                "reason": authorization.reason,
                "backup_attestation": authorization.backup_attestation,
                "generated_at": now,
                "expires_at": now + self._recreate_plan_ttl,
                "nonce": nonce,
            }
            plan_hash = canonical_json_sha256(base)
            challenge = sha256_bytes(
                f"{plan_hash}:{nonce}:{authorization.operator_id}".encode("utf-8")
            )[:24]
            connection.commit()
            return RecreatePlan(
                database_name=identity.database_name,
                database_oid=identity.database_oid,
                database_owner=identity.database_owner,
                connected_role=identity.connected_role,
                application_schema=APPLICATION_SCHEMA,
                schema_owner=schema_owner,
                detected_epoch=epoch.epoch_name,
                detected_schema_name=epoch.schema_name,
                detected_release_state=epoch.release_state,
                detected_baseline_version=epoch.baseline_version,
                detected_baseline_checksum=epoch.baseline_checksum,
                detected_seed_checksum=epoch.seed_checksum,
                detected_reference_vocabulary_checksum=(
                    epoch.reference_vocabulary_checksum
                ),
                catalog_checksum=catalog_checksum,
                catalog_objects=catalog_objects,
                active_connection_pids=active_connection_pids,
                unexpected_objects=unexpected_objects,
                operator_id=authorization.operator_id,
                reason=authorization.reason,
                backup_attestation=authorization.backup_attestation,
                generated_at=now,
                expires_at=now + self._recreate_plan_ttl,
                nonce=nonce,
                plan_hash=plan_hash,
                challenge=challenge,
            )

    def apply_recreate(
        self,
        plan: RecreatePlan,
        *,
        challenge: str,
        operator_id: str,
    ) -> RecreateResult:
        """Atomically replace the exact planned target schema and bootstrap it."""

        if not operator_id.strip() or not secrets.compare_digest(
            operator_id, plan.operator_id
        ):
            raise RecreatePlanStaleError("RECREATE_OPERATOR_MISMATCH")
        expected_hash = _recreate_plan_hash(plan)
        expected_challenge = sha256_bytes(
            f"{expected_hash}:{plan.nonce}:{plan.operator_id}".encode("utf-8")
        )[:24]
        if expected_hash != plan.plan_hash:
            raise RecreatePlanStaleError("RECREATE_PLAN_HASH_MISMATCH")
        if not secrets.compare_digest(challenge, plan.challenge) or not secrets.compare_digest(
            challenge, expected_challenge
        ):
            raise RecreatePlanStaleError("RECREATE_CHALLENGE_MISMATCH")

        with self._connect() as connection:
            _take_bootstrap_lock(connection)
            identity = _database_identity(connection)
            _validate_plan_identity(identity, plan)
            _require_database_owner(identity)
            active_connection_pids = _require_no_other_connections(connection)
            unexpected_objects = self._require_no_external_catalog(connection)
            schema_owner = _schema_owner(connection)
            _require_schema_owner(identity, schema_owner)
            now = _database_now(connection)
            if now > plan.expires_at.astimezone(timezone.utc):
                raise RecreatePlanStaleError("RECREATE_PLAN_EXPIRED")
            epoch = _read_epoch(connection)
            _validate_recreate_epoch(epoch)
            current_catalog_checksum = _target_catalog_checksum(connection)
            current_catalog_objects = _target_catalog_objects(connection)
            current_identity = (
                epoch.epoch_name,
                epoch.schema_name,
                epoch.release_state,
                epoch.baseline_version,
                epoch.baseline_checksum,
                epoch.seed_checksum,
                epoch.reference_vocabulary_checksum,
                current_catalog_checksum,
            )
            planned_identity = (
                plan.detected_epoch,
                plan.detected_schema_name,
                plan.detected_release_state,
                plan.detected_baseline_version,
                plan.detected_baseline_checksum,
                plan.detected_seed_checksum,
                plan.detected_reference_vocabulary_checksum,
                plan.catalog_checksum,
            )
            if current_identity != planned_identity:
                raise RecreatePlanStaleError(
                    "RECREATE_PLAN_STALE: catalog or epoch changed after planning"
                )
            if current_catalog_checksum != epoch.catalog_checksum:
                raise CatalogDriftError(
                    "stored catalog checksum does not match the detected target schema"
                )
            if (
                schema_owner != plan.schema_owner
                or current_catalog_objects != plan.catalog_objects
                or active_connection_pids != plan.active_connection_pids
                or unexpected_objects != plan.unexpected_objects
            ):
                raise RecreatePlanStaleError(
                    "RECREATE_PLAN_STALE: ownership, connections, or object manifest changed"
                )

            connection.execute("DROP SCHEMA mra CASCADE")
            connection.execute(self._baseline_sql)
            catalog_checksum = _target_catalog_checksum(connection)
            connection.execute(
                self._seed_sql,
                (
                    self.baseline_checksum,
                    self.seed_checksum,
                    catalog_checksum,
                    self.reference_vocabulary_checksum,
                    self.baseline_checksum,
                ),
            )
            verification = self._verify_connection(connection, created=True)
            connection.commit()
            return RecreateResult(
                plan_hash=plan.plan_hash,
                removed_application_schema=plan.application_schema,
                removed_schema_owner=plan.schema_owner,
                removed_epoch=epoch.epoch_name,
                removed_baseline_checksum=epoch.baseline_checksum,
                removed_seed_checksum=epoch.seed_checksum,
                removed_catalog_checksum=current_catalog_checksum,
                removed_catalog_objects=current_catalog_objects,
                verification=verification,
            )

    def _verify_connection(
        self,
        connection: psycopg.Connection[Any],
        *,
        created: bool,
    ) -> SchemaVerification:
        self._require_no_external_catalog(connection)
        if not _schema_exists(connection, APPLICATION_SCHEMA):
            raise SchemaMissingError("target schema mra is absent; ordinary startup performs no DDL")
        epoch = _read_epoch(connection)
        if epoch.epoch_name != SCHEMA_EPOCH:
            raise SchemaEpochMismatchError(
                f"expected {SCHEMA_EPOCH}, found {epoch.epoch_name}"
            )
        if epoch.schema_name != APPLICATION_SCHEMA:
            raise SchemaEpochMismatchError(
                f"expected schema {APPLICATION_SCHEMA}, found {epoch.schema_name}"
            )
        if epoch.release_state != BASELINE_RELEASE_STATE:
            raise SchemaEpochMismatchError(
                f"expected release state {BASELINE_RELEASE_STATE}, found {epoch.release_state}"
            )
        if epoch.baseline_version != BASELINE_VERSION:
            raise SchemaEpochMismatchError(
                f"expected baseline version {BASELINE_VERSION}, found {epoch.baseline_version}"
            )
        if epoch.baseline_checksum != self.baseline_checksum:
            raise SchemaChecksumMismatchError(
                "BASELINE_CHECKSUM_MISMATCH: explicit recreate is required for a changed draft baseline"
            )
        if epoch.seed_checksum != self.seed_checksum:
            raise SchemaChecksumMismatchError(
                "SEED_CHECKSUM_MISMATCH: explicit recreate is required for a changed draft seed"
            )
        if epoch.reference_vocabulary_checksum != self.reference_vocabulary_checksum:
            raise SchemaChecksumMismatchError(
                "REFERENCE_VOCABULARY_CHECKSUM_MISMATCH: explicit recreate is required"
            )
        tables = _target_tables(connection)
        if tables != EXPECTED_TARGET_TABLES:
            missing = sorted(EXPECTED_TARGET_TABLES - tables)
            unexpected = sorted(tables - EXPECTED_TARGET_TABLES)
            raise CatalogDriftError(
                f"Target table inventory differs; missing={missing}, unexpected={unexpected}"
            )
        catalog_checksum = _target_catalog_checksum(connection)
        if catalog_checksum != epoch.catalog_checksum:
            raise CatalogDriftError(
                "CATALOG_DRIFT: detected target objects differ from the installed catalog checksum"
            )
        _verify_migration_registry(connection, self.baseline_checksum)
        _verify_primary_keys(connection, tables)
        _verify_foreign_key_indexes(connection)
        return SchemaVerification(
            created=created,
            epoch=epoch.epoch_name,
            schema_name=epoch.schema_name,
            release_state=epoch.release_state,
            baseline_version=epoch.baseline_version,
            baseline_checksum=epoch.baseline_checksum,
            seed_checksum=epoch.seed_checksum,
            catalog_checksum=epoch.catalog_checksum,
            reference_vocabulary_checksum=epoch.reference_vocabulary_checksum,
            tables=tables,
            verified_at=_database_now(connection),
        )

    def _require_empty_allowed_catalog(self, connection: psycopg.Connection[Any]) -> None:
        objects = _external_catalog_objects(connection)
        legacy = sorted(
            item for item in objects if item.split(":", 2)[-1] in _LEGACY_TABLE_SIGNATURES
        )
        if legacy:
            raise LegacySchemaPresentError(f"recognized legacy objects: {legacy}")
        if objects:
            raise UnexpectedCatalogError(f"unexpected user objects: {sorted(objects)}")

    def _require_no_external_catalog(
        self, connection: psycopg.Connection[Any]
    ) -> tuple[str, ...]:
        objects = _external_catalog_objects(connection)
        legacy = sorted(
            item for item in objects if item.split(":", 2)[-1] in _LEGACY_TABLE_SIGNATURES
        )
        if legacy:
            raise LegacySchemaPresentError(f"recognized legacy objects: {legacy}")
        if objects:
            raise UnexpectedCatalogError(f"unexpected user objects: {sorted(objects)}")
        return tuple(sorted(objects))

    def _connect(self, *, read_only: bool = False) -> psycopg.Connection[Any]:
        connection = psycopg.connect(self._database_url, autocommit=False)
        connection.read_only = read_only
        connection.execute("SELECT set_config('search_path', 'pg_catalog', false)")
        connection.execute("SELECT set_config('timezone', 'UTC', false)")
        connection.execute(
            "SELECT set_config('application_name', 'market-regime-alpha-refoundation-schema', false)"
        )
        connection.execute("SELECT set_config('statement_timeout', '30s', false)")
        connection.execute("SELECT set_config('lock_timeout', '5s', false)")
        return connection


def _read_package_text(package: str, name: str) -> str:
    resource = files(f"market_regime_alpha.infrastructure.postgres.{package}").joinpath(name)
    return resource.read_text(encoding="utf-8")


def _schema_exists(connection: psycopg.Connection[Any], schema_name: str) -> bool:
    row = connection.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
        (schema_name,),
    ).fetchone()
    return bool(row and row[0])


def _take_bootstrap_lock(connection: psycopg.Connection[Any]) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (_BOOTSTRAP_LOCK_KEY,),
    )


def _database_identity(connection: psycopg.Connection[Any]) -> DatabaseIdentity:
    row = connection.execute(
        """
        SELECT database.datname, database.oid::bigint, owner.rolname, current_user
        FROM pg_database AS database
        JOIN pg_roles AS owner ON owner.oid = database.datdba
        WHERE database.datname = current_database()
        """
    ).fetchone()
    if row is None:
        raise SchemaError("database identity could not be resolved")
    return DatabaseIdentity(
        database_name=str(row[0]),
        database_oid=int(row[1]),
        database_owner=str(row[2]),
        connected_role=str(row[3]),
    )


def _database_now(connection: psycopg.Connection[Any]) -> datetime:
    row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise SchemaError("database clock could not be resolved")
    return row[0].astimezone(timezone.utc)


def _external_catalog_objects(connection: psycopg.Connection[Any]) -> frozenset[str]:
    relations = connection.execute(
        """
        SELECT namespace.nspname, object.relkind, object.relname
        FROM pg_class AS object
        JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'mra')
          AND namespace.nspname NOT LIKE 'pg_toast%'
          AND object.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_class'::regclass
                AND dependency.objid = object.oid
                AND dependency.deptype = 'e'
          )
        ORDER BY namespace.nspname, object.relkind, object.relname
        """
    ).fetchall()
    routines = connection.execute(
        """
        SELECT namespace.nspname, 'function', routine.proname
        FROM pg_proc AS routine
        JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'mra')
          AND namespace.nspname NOT LIKE 'pg_toast%'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_proc'::regclass
                AND dependency.objid = routine.oid
                AND dependency.deptype = 'e'
          )
        ORDER BY namespace.nspname, routine.proname
        """
    ).fetchall()
    return frozenset(
        f"{schema}:{kind}:{name}" for schema, kind, name in (*relations, *routines)
    )


def _schema_owner(connection: psycopg.Connection[Any]) -> str:
    row = connection.execute(
        """
        SELECT owner.rolname
        FROM pg_namespace AS namespace
        JOIN pg_roles AS owner ON owner.oid = namespace.nspowner
        WHERE namespace.nspname = 'mra'
        """
    ).fetchone()
    if row is None:
        raise SchemaMissingError("target schema mra is absent")
    return str(row[0])


def _target_catalog_objects(connection: psycopg.Connection[Any]) -> tuple[str, ...]:
    relations = connection.execute(
        """
        SELECT format('relation:%s:%s', object.relkind, object.relname)
        FROM pg_class AS object
        JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
        WHERE namespace.nspname = 'mra'
          AND object.relkind IN ('r', 'p', 'v', 'm', 'i', 'S', 'f')
        """
    ).fetchall()
    routines = connection.execute(
        """
        SELECT format(
            'routine:%s:%s(%s)',
            routine.prokind,
            routine.proname,
            pg_get_function_identity_arguments(routine.oid)
        )
        FROM pg_proc AS routine
        JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = 'mra'
        """
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT format('constraint:%s:%s', table_object.relname, constraint_item.conname)
        FROM pg_constraint AS constraint_item
        JOIN pg_class AS table_object ON table_object.oid = constraint_item.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra'
        """
    ).fetchall()
    triggers = connection.execute(
        """
        SELECT format('trigger:%s:%s', table_object.relname, trigger_item.tgname)
        FROM pg_trigger AS trigger_item
        JOIN pg_class AS table_object ON table_object.oid = trigger_item.tgrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra' AND NOT trigger_item.tgisinternal
        """
    ).fetchall()
    return tuple(
        sorted(
            {
                "schema:mra",
                *(str(row[0]) for row in relations),
                *(str(row[0]) for row in routines),
                *(str(row[0]) for row in constraints),
                *(str(row[0]) for row in triggers),
            }
        )
    )


def _target_tables(connection: psycopg.Connection[Any]) -> frozenset[str]:
    rows = connection.execute(
        """
        SELECT object.relname
        FROM pg_class AS object
        JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
        WHERE namespace.nspname = 'mra' AND object.relkind IN ('r', 'p')
        ORDER BY object.relname
        """
    ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def _target_catalog_checksum(connection: psycopg.Connection[Any]) -> str:
    schema_row = connection.execute(
        """
        SELECT owner.rolname, obj_description(namespace.oid, 'pg_namespace')
        FROM pg_namespace AS namespace
        JOIN pg_roles AS owner ON owner.oid = namespace.nspowner
        WHERE namespace.nspname = 'mra'
        """
    ).fetchone()
    if schema_row is None:
        raise SchemaMissingError("target schema mra is absent")
    relations = connection.execute(
        """
        SELECT object.relkind, object.relname, owner.rolname,
               object.relpersistence, object.relrowsecurity, object.relforcerowsecurity,
               CASE WHEN object.relkind IN ('v', 'm') THEN pg_get_viewdef(object.oid, true) ELSE NULL END
        FROM pg_class AS object
        JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
        JOIN pg_roles AS owner ON owner.oid = object.relowner
        WHERE namespace.nspname = 'mra'
          AND object.relkind IN ('r', 'p', 'v', 'm', 'i', 'S', 'f')
        ORDER BY object.relkind, object.relname
        """
    ).fetchall()
    columns = connection.execute(
        """
        SELECT table_object.relname, column_item.attnum, column_item.attname,
               format_type(column_item.atttypid, column_item.atttypmod),
               column_item.attnotnull,
               pg_get_expr(default_item.adbin, default_item.adrelid)
        FROM pg_attribute AS column_item
        JOIN pg_class AS table_object ON table_object.oid = column_item.attrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        LEFT JOIN pg_attrdef AS default_item
          ON default_item.adrelid = column_item.attrelid
         AND default_item.adnum = column_item.attnum
        WHERE namespace.nspname = 'mra'
          AND table_object.relkind IN ('r', 'p', 'v', 'm')
          AND column_item.attnum > 0
          AND NOT column_item.attisdropped
        ORDER BY table_object.relname, column_item.attnum
        """
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT table_object.relname, constraint_item.conname,
               constraint_item.contype, constraint_item.convalidated,
               constraint_item.condeferrable, constraint_item.condeferred,
               pg_get_constraintdef(constraint_item.oid, true)
        FROM pg_constraint AS constraint_item
        JOIN pg_class AS table_object ON table_object.oid = constraint_item.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra'
        ORDER BY table_object.relname, constraint_item.conname
        """
    ).fetchall()
    indexes = connection.execute(
        """
        SELECT index_object.relname, index_item.indisvalid, index_item.indisready,
               index_item.indislive, index_item.indisunique, index_item.indisprimary,
               pg_get_indexdef(index_object.oid)
        FROM pg_class AS index_object
        JOIN pg_namespace AS namespace ON namespace.oid = index_object.relnamespace
        JOIN pg_index AS index_item ON index_item.indexrelid = index_object.oid
        WHERE namespace.nspname = 'mra' AND index_object.relkind = 'i'
        ORDER BY index_object.relname
        """
    ).fetchall()
    functions = connection.execute(
        """
        SELECT routine.proname, routine.prokind, routine.provolatile,
               routine.proparallel, routine.prosecdef,
               pg_get_function_identity_arguments(routine.oid),
               pg_get_functiondef(routine.oid)
        FROM pg_proc AS routine
        JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = 'mra'
        ORDER BY routine.proname, pg_get_function_identity_arguments(routine.oid)
        """
    ).fetchall()
    triggers = connection.execute(
        """
        SELECT table_object.relname, trigger_item.tgname, trigger_item.tgenabled,
               pg_get_triggerdef(trigger_item.oid, true)
        FROM pg_trigger AS trigger_item
        JOIN pg_class AS table_object ON table_object.oid = trigger_item.tgrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra' AND NOT trigger_item.tgisinternal
        ORDER BY table_object.relname, trigger_item.tgname
        """
    ).fetchall()
    payload = {
        "schema": APPLICATION_SCHEMA,
        "owner": schema_row[0],
        "comment": schema_row[1],
        "relations": [list(row) for row in relations],
        "columns": [list(row) for row in columns],
        "constraints": [list(row) for row in constraints],
        "indexes": [list(row) for row in indexes],
        "functions": [list(row) for row in functions],
        "triggers": [list(row) for row in triggers],
    }
    return canonical_json_sha256(payload)


def _read_epoch(connection: psycopg.Connection[Any]) -> _EpochRow:
    if not _schema_exists(connection, APPLICATION_SCHEMA):
        raise SchemaMissingError("target schema mra is absent")
    relation = connection.execute("SELECT to_regclass('mra.schema_epoch')").fetchone()
    if relation is None or relation[0] is None:
        raise SchemaEpochMismatchError("mra objects exist without schema_epoch")
    try:
        rows = connection.execute(
            """
            SELECT epoch_name, schema_name, release_state, baseline_version,
                   baseline_checksum, seed_checksum, catalog_checksum,
                   reference_vocabulary_checksum
            FROM mra.schema_epoch
            """
        ).fetchall()
    except psycopg.Error as exc:
        raise SchemaEpochMismatchError(
            "schema_epoch does not satisfy the target epoch contract"
        ) from exc
    if len(rows) != 1:
        raise SchemaEpochMismatchError(
            f"schema_epoch must contain exactly one row, found {len(rows)}"
        )
    row = rows[0]
    return _EpochRow(
        epoch_name=str(row[0]),
        schema_name=str(row[1]),
        release_state=str(row[2]),
        baseline_version=int(row[3]),
        baseline_checksum=str(row[4]),
        seed_checksum=str(row[5]),
        catalog_checksum=str(row[6]),
        reference_vocabulary_checksum=str(row[7]),
    )


def _verify_migration_registry(
    connection: psycopg.Connection[Any], baseline_checksum: str
) -> None:
    rows = connection.execute(
        """
        SELECT version, name, checksum, transactional, epoch_name
        FROM mra.schema_migrations
        ORDER BY version
        """
    ).fetchall()
    expected = [(BASELINE_VERSION, BASELINE_NAME, baseline_checksum, True, SCHEMA_EPOCH)]
    actual = [tuple(row) for row in rows]
    if actual != expected:
        raise CatalogDriftError(
            f"migration registry differs from the draft baseline: {actual!r}"
        )


def _verify_primary_keys(
    connection: psycopg.Connection[Any], tables: frozenset[str]
) -> None:
    rows = connection.execute(
        """
        SELECT table_object.relname
        FROM pg_constraint AS constraint_item
        JOIN pg_class AS table_object ON table_object.oid = constraint_item.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra' AND constraint_item.contype = 'p'
        """
    ).fetchall()
    with_primary_key = frozenset(str(row[0]) for row in rows)
    if with_primary_key != tables:
        raise CatalogDriftError(
            f"every target table requires a primary key; missing={sorted(tables - with_primary_key)}"
        )


def _verify_foreign_key_indexes(connection: psycopg.Connection[Any]) -> None:
    foreign_keys = connection.execute(
        """
        SELECT table_object.relname, constraint_item.conname,
               constraint_item.conkey::smallint[]
        FROM pg_constraint AS constraint_item
        JOIN pg_class AS table_object ON table_object.oid = constraint_item.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra' AND constraint_item.contype = 'f'
        ORDER BY table_object.relname, constraint_item.conname
        """
    ).fetchall()
    indexes = connection.execute(
        """
        SELECT table_object.relname, index_item.indkey::smallint[]
        FROM pg_index AS index_item
        JOIN pg_class AS table_object ON table_object.oid = index_item.indrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_object.relnamespace
        WHERE namespace.nspname = 'mra' AND index_item.indisvalid
        """
    ).fetchall()
    by_table: dict[str, list[tuple[int, ...]]] = {}
    for table_name, index_columns in indexes:
        by_table.setdefault(str(table_name), []).append(tuple(index_columns))
    missing: list[str] = []
    for table_name, constraint_name, key_columns in foreign_keys:
        key = tuple(key_columns)
        if not any(candidate[: len(key)] == key for candidate in by_table.get(str(table_name), [])):
            missing.append(f"{table_name}.{constraint_name}")
    if missing:
        raise CatalogDriftError(f"foreign keys lack leading indexes: {missing}")


def _validate_recreate_identity(
    identity: DatabaseIdentity, authorization: RecreateAuthorization
) -> None:
    _require_non_system_database(identity)
    if identity.database_name != authorization.expected_database_name:
        raise UnsafeRecreateError("database name does not match explicit authorization")
    if identity.database_oid != authorization.expected_database_oid:
        raise UnsafeRecreateError("database OID does not match explicit authorization")


def _validate_plan_identity(identity: DatabaseIdentity, plan: RecreatePlan) -> None:
    _require_non_system_database(identity)
    if (
        identity.database_name,
        identity.database_oid,
        identity.database_owner,
        identity.connected_role,
    ) != (
        plan.database_name,
        plan.database_oid,
        plan.database_owner,
        plan.connected_role,
    ):
        raise RecreatePlanStaleError("database identity or role changed after planning")


def _require_database_owner(identity: DatabaseIdentity) -> None:
    if identity.connected_role != identity.database_owner:
        raise UnsafeRecreateError(
            "destructive recreate requires the exact database owner maintenance role"
        )


def _require_non_system_database(identity: DatabaseIdentity) -> None:
    if identity.database_name in {"postgres", "template0", "template1"}:
        raise UnsafeRecreateError(f"refusing default/system database {identity.database_name}")


def _validate_recreate_epoch(epoch: _EpochRow) -> None:
    detected = (
        epoch.epoch_name,
        epoch.schema_name,
        epoch.release_state,
        epoch.baseline_version,
    )
    expected = (
        SCHEMA_EPOCH,
        APPLICATION_SCHEMA,
        BASELINE_RELEASE_STATE,
        BASELINE_VERSION,
    )
    if detected != expected:
        raise UnsafeRecreateError(
            "destructive recreate accepts only the current unreleased target draft epoch"
        )


def _require_no_other_connections(
    connection: psycopg.Connection[Any],
) -> tuple[int, ...]:
    rows = connection.execute(
        """
        SELECT pid
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND backend_type = 'client backend'
        ORDER BY pid
        """
    ).fetchall()
    pids = tuple(int(row[0]) for row in rows)
    if pids:
        raise UnsafeRecreateError(
            "destructive recreate requires zero other client connections; "
            f"found pids={list(pids)}"
        )
    return pids


def _require_schema_owner(identity: DatabaseIdentity, schema_owner: str) -> None:
    if identity.connected_role != schema_owner:
        raise UnsafeRecreateError(
            "destructive recreate requires the exact target schema owner maintenance role"
        )


def _recreate_plan_hash(plan: RecreatePlan) -> str:
    payload = asdict(plan)
    payload.pop("plan_hash")
    payload.pop("challenge")
    return canonical_json_sha256(payload)


__all__ = [
    "APPLICATION_SCHEMA",
    "BASELINE_RELEASE_STATE",
    "CatalogDriftError",
    "DatabaseIdentity",
    "EXPECTED_FOUNDATION_TABLES",
    "EXPECTED_MARKET_TABLES",
    "EXPECTED_RESEARCH_DEFINITION_TABLES",
    "EXPECTED_SELECTION_TABLES",
    "EXPECTED_TARGET_TABLES",
    "LegacySchemaPresentError",
    "RecreateAuthorization",
    "RecreatePlan",
    "RecreateResult",
    "RecreatePlanStaleError",
    "SCHEMA_EPOCH",
    "SchemaChecksumMismatchError",
    "SchemaEpochMismatchError",
    "SchemaError",
    "SchemaManager",
    "SchemaMissingError",
    "SchemaVerification",
    "UnexpectedCatalogError",
    "UnsafeRecreateError",
]
