"""Immutable Decision Run preparation and closed-authority models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import re
from uuid import UUID

from market_regime_alpha.decision_support.domain.vocabulary import (
    CandidateDisposition,
    DecisionReferenceAvailabilityStatus,
    DecisionReferenceFinalityStatus,
    DecisionReferenceSourceKind,
    DecisionReferenceValueStatus,
    DecisionRunStatus,
    DecisionRuntimeMode,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_TARGET_TIMEFRAMES = frozenset(
    {"MINUTE_1", "MINUTE_5", "MINUTE_15", "MINUTE_30", "MINUTE_60", "DAILY"}
)
_TARGET_PRICE_BASES = frozenset(
    {"RAW_UNADJUSTED", "FORWARD_ADJUSTED", "BACKWARD_ADJUSTED"}
)
_TARGET_VALUE_FIELDS = frozenset({"OPEN", "HIGH", "LOW", "CLOSE"})
_GAP_KINDS = frozenset(
    {"MISSING", "PLACEHOLDER", "PROVIDER_FAILURE", "CONFLICT", "INVALID_OHLC"}
)
_GAP_REASONS = frozenset(
    {
        "PROVIDER_FAILURE",
        "NO_ROWS_RETURNED",
        "EXPECTED_OBSERVATION_MISSING",
        "EXACT_BAR_MISSING",
        "NULL_OHLC_PLACEHOLDER",
        "CONFLICTING_SOURCE_REVISIONS",
        "INVALID_OHLC",
    }
)


def _utc(value: datetime, field_name: str) -> datetime:
    return require_utc(value, field=field_name)


def _hash(value: ContentHash | str, field_name: str) -> str:
    try:
        return str(value if isinstance(value, ContentHash) else ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a lowercase SHA-256") from exc


@dataclass(frozen=True, slots=True)
class RequestedDecisionTarget:
    target_definition_id: UUID
    reference_provider_product_id: UUID

    @staticmethod
    def roster(
        targets: tuple[RequestedDecisionTarget, ...],
    ) -> tuple[RequestedDecisionTarget, ...]:
        if not targets:
            raise ValueError("Decision Target roster must be non-empty")
        identities = tuple(item.target_definition_id for item in targets)
        if len(set(identities)) != len(identities):
            raise ValueError("Decision Target roster contains a duplicate Target")
        return targets


@dataclass(frozen=True, slots=True)
class OpenDecisionRunRequest:
    candidate_set_id: UUID
    targets: tuple[RequestedDecisionTarget, ...]

    def validated_targets(self) -> tuple[RequestedDecisionTarget, ...]:
        return RequestedDecisionTarget.roster(self.targets)

    @property
    def request_roster_sha256(self) -> str:
        return canonical_json_sha256(
            tuple(
                {
                    "ordinal": ordinal,
                    "reference_provider_product_id": (
                        target.reference_provider_product_id
                    ),
                    "target_definition_id": target.target_definition_id,
                }
                for ordinal, target in enumerate(self.targets, start=1)
            )
        )


@dataclass(frozen=True, slots=True)
class CandidateDecisionFact:
    candidate_id: UUID
    candidate_set_id: UUID
    instrument_id: UUID
    disposition: CandidateDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, CandidateDisposition):
            raise TypeError("candidate disposition must be typed")


@dataclass(frozen=True, slots=True)
class CandidateSetDecisionSnapshot:
    candidate_set_id: UUID
    content_sha256: str
    dataset_id: UUID
    candidate_policy_id: UUID
    decision_time: datetime
    population_count: int
    selected_count: int
    ranked_not_selected_count: int
    unrankable_count: int
    candidates: tuple[CandidateDecisionFact, ...]
    candidate_roster_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", _hash(self.content_sha256, "CandidateSet hash"))
        object.__setattr__(self, "decision_time", _utc(self.decision_time, "candidate decision_time"))
        counts = (
            self.population_count,
            self.selected_count,
            self.ranked_not_selected_count,
            self.unrankable_count,
        )
        if any(isinstance(item, bool) or item < 0 for item in counts):
            raise ValueError("CandidateSet counts must be non-negative")
        if self.population_count != len(self.candidates):
            raise ValueError("CandidateSet population count does not match its roster")
        if self.population_count != sum(counts[1:]):
            raise ValueError("CandidateSet disposition counts do not reconcile")
        if any(item.candidate_set_id != self.candidate_set_id for item in self.candidates):
            raise ValueError("Candidate belongs to another CandidateSet")
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        instruments = tuple(item.instrument_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Candidate roster contains duplicate identities")
        if len(set(instruments)) != len(instruments):
            raise ValueError("Candidate roster contains duplicate instruments")
        actual_counts = {
            disposition: sum(item.disposition is disposition for item in self.candidates)
            for disposition in CandidateDisposition
        }
        if (
            actual_counts[CandidateDisposition.SELECTED] != self.selected_count
            or actual_counts[CandidateDisposition.RANKED_NOT_SELECTED]
            != self.ranked_not_selected_count
            or actual_counts[CandidateDisposition.UNRANKABLE] != self.unrankable_count
        ):
            raise ValueError("Candidate roster disposition facts do not reconcile")
        ordered = tuple(sorted(self.candidates, key=lambda item: str(item.candidate_id)))
        object.__setattr__(
            self,
            "candidate_roster_sha256",
            canonical_json_sha256(
                tuple(
                    {
                        "candidate_id": item.candidate_id,
                        "disposition": item.disposition,
                        "instrument_id": item.instrument_id,
                    }
                    for item in ordered
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderProductDecisionSnapshot:
    provider_product_id: UUID
    provider_id: UUID
    product_code: str
    revision: int
    decision_visibility_policy: str
    source_availability_policy: str

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.product_code):
            raise ValueError("Provider Product code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("Provider Product revision must be positive")
        if self.decision_visibility_policy != "KNOWN_AT":
            raise ValueError("Provider Product must use KNOWN_AT Decision visibility")
        if not self.source_availability_policy:
            raise ValueError("Provider Product source availability policy is required")


@dataclass(frozen=True, slots=True)
class TargetDecisionSnapshot:
    target_definition_id: UUID
    target_code: str
    version: int
    content_sha256: str
    target_checkpoint_id: UUID
    checkpoint_content_sha256: str
    checkpoint_ordinal: int
    timeframe: str
    price_basis: str
    value_field: str
    reference_rule: str
    availability_rule: str
    finality_rule: str
    reference_provider_product: ProviderProductDecisionSnapshot

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", self.target_code):
            raise ValueError("Target code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Target version must be positive")
        object.__setattr__(self, "content_sha256", _hash(self.content_sha256, "Target hash"))
        object.__setattr__(
            self,
            "checkpoint_content_sha256",
            _hash(self.checkpoint_content_sha256, "Target checkpoint hash"),
        )
        if isinstance(self.checkpoint_ordinal, bool) or self.checkpoint_ordinal < 1:
            raise ValueError("Decision reference checkpoint ordinal must be positive")
        if self.timeframe not in _TARGET_TIMEFRAMES:
            raise ValueError("Target reference timeframe is unsupported")
        if self.price_basis not in _TARGET_PRICE_BASES:
            raise ValueError("Target reference price basis is unsupported")
        if self.value_field not in _TARGET_VALUE_FIELDS:
            raise ValueError("Target reference value field is unsupported")
        if self.reference_rule != "EXACT_SESSION_BAR":
            raise ValueError("Target reference rule must require the exact session bar")
        if self.availability_rule != "EXACT_REVISION_OR_SOURCE_GAP":
            raise ValueError("Target availability rule is unsupported")
        if self.finality_rule != "RECORD_UNKNOWN":
            raise ValueError("WP-09 can only record UNKNOWN finality")


@dataclass(frozen=True, slots=True)
class RuntimeDecisionSnapshot:
    run_id: UUID
    step_id: UUID
    attempt_id: UUID
    fence_token: int
    step_key: str
    step_kind: str
    runtime_mode: DecisionRuntimeMode
    decision_time: datetime
    code_sha: str
    config_artifact_id: UUID
    config_hash: str

    def __post_init__(self) -> None:
        if isinstance(self.fence_token, bool) or self.fence_token < 1:
            raise ValueError("Runtime fence must be positive")
        if not self.step_key:
            raise ValueError("Runtime Step key is required")
        if self.step_kind != "OPEN_DECISION_RUN":
            raise ValueError("Decision Run requires an OPEN_DECISION_RUN Step")
        if not isinstance(self.runtime_mode, DecisionRuntimeMode):
            raise TypeError("Runtime mode must be typed")
        object.__setattr__(self, "decision_time", _utc(self.decision_time, "runtime decision_time"))
        if not _SHA.fullmatch(self.code_sha):
            raise ValueError("Runtime code identity must be a SHA-1 or SHA-256")
        object.__setattr__(self, "config_hash", _hash(self.config_hash, "Runtime config hash"))


@dataclass(frozen=True, slots=True)
class PreparedDecisionInputs:
    candidate_set: CandidateSetDecisionSnapshot
    targets: tuple[TargetDecisionSnapshot, ...]
    references: tuple[PreparedDecisionReference, ...]
    runtime: RuntimeDecisionSnapshot

    def __post_init__(self) -> None:
        RequestedDecisionTarget.roster(
            tuple(
                RequestedDecisionTarget(
                    target_definition_id=item.target_definition_id,
                    reference_provider_product_id=(
                        item.reference_provider_product.provider_product_id
                    ),
                )
                for item in self.targets
            )
        )
        if self.candidate_set.decision_time != self.runtime.decision_time:
            raise ValueError("prepared CandidateSet and Runtime DecisionTime differ")

    def semantic_request_sha256(
        self,
        *,
        request: OpenDecisionRunRequest,
        actor_type: str,
        actor_id: str,
        reason_code: str,
    ) -> str:
        if request.candidate_set_id != self.candidate_set.candidate_set_id:
            raise ValueError("prepared CandidateSet identity differs from request")
        requested = request.validated_targets()
        actual = tuple(
            RequestedDecisionTarget(
                target_definition_id=item.target_definition_id,
                reference_provider_product_id=(
                    item.reference_provider_product.provider_product_id
                ),
            )
            for item in self.targets
        )
        if requested != actual:
            raise ValueError("prepared Target roster differs from request")
        return canonical_json_sha256(
            {
                "actor_id": actor_id,
                "actor_type": actor_type,
                "candidate_roster_sha256": (
                    self.candidate_set.candidate_roster_sha256
                ),
                "candidate_set_content_sha256": self.candidate_set.content_sha256,
                "candidate_set_id": self.candidate_set.candidate_set_id,
                "code_sha": self.runtime.code_sha,
                "config_artifact_id": self.runtime.config_artifact_id,
                "config_hash": self.runtime.config_hash,
                "decision_time": self.runtime.decision_time,
                "reason_code": reason_code,
                "runtime_mode": self.runtime.runtime_mode,
                "runtime_run_id": self.runtime.run_id,
                "targets": tuple(
                    {
                        "ordinal": ordinal,
                        "provider_id": target.reference_provider_product.provider_id,
                        "provider_product_id": (
                            target.reference_provider_product.provider_product_id
                        ),
                        "provider_product_revision": (
                            target.reference_provider_product.revision
                        ),
                        "target_checkpoint_id": target.target_checkpoint_id,
                        "target_checkpoint_sha256": (
                            target.checkpoint_content_sha256
                        ),
                        "target_definition_id": target.target_definition_id,
                        "target_definition_sha256": target.content_sha256,
                        "target_version": target.version,
                    }
                    for ordinal, target in enumerate(self.targets, start=1)
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class PreparedDecisionReference:
    candidate_id: UUID
    target_definition_id: UUID
    target_checkpoint_id: UUID
    provider_product_id: UUID
    provider_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID
    event_start: datetime
    event_end: datetime
    observation_time: datetime
    recorded_at: datetime
    known_at: datetime
    timeframe: str
    price_basis: str
    source_kind: DecisionReferenceSourceKind
    value_status: DecisionReferenceValueStatus
    availability_status: DecisionReferenceAvailabilityStatus
    finality_status: DecisionReferenceFinalityStatus
    value_field: str
    decimal_value: Decimal | None
    bar_revision_id: UUID | None
    bar_revision: int | None
    source_gap_id: UUID | None
    source_gap_kind: str | None
    source_gap_reason_code: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "event_start",
            "event_end",
            "observation_time",
            "recorded_at",
            "known_at",
        ):
            object.__setattr__(self, field_name, _utc(getattr(self, field_name), field_name))
        if self.event_end <= self.event_start or self.observation_time != self.event_end:
            raise ValueError("Decision reference observation interval is invalid")
        if self.known_at < self.recorded_at:
            raise ValueError("reference known_at cannot precede source recording")
        if self.timeframe not in _TARGET_TIMEFRAMES or self.price_basis not in _TARGET_PRICE_BASES:
            raise ValueError("Decision reference timeframe/price basis is invalid")
        if self.value_field not in _TARGET_VALUE_FIELDS:
            raise ValueError("Decision reference value field is invalid")
        if not isinstance(self.source_kind, DecisionReferenceSourceKind):
            raise TypeError("reference source kind must be typed")
        if not isinstance(self.value_status, DecisionReferenceValueStatus):
            raise TypeError("reference value status must be typed")
        if not isinstance(self.availability_status, DecisionReferenceAvailabilityStatus):
            raise TypeError("reference availability status must be typed")
        if self.finality_status is not DecisionReferenceFinalityStatus.UNKNOWN:
            raise ValueError("WP-09 reference finality must be UNKNOWN")
        if self.source_kind is DecisionReferenceSourceKind.BAR_REVISION:
            if (
                self.bar_revision_id is None
                or self.bar_revision is None
                or self.bar_revision < 1
                or self.source_gap_id is not None
                or self.source_gap_kind is not None
                or self.source_gap_reason_code is not None
                or self.decimal_value is None
                or not self.decimal_value.is_finite()
                or self.decimal_value <= 0
                or self.value_status is not DecisionReferenceValueStatus.PRESENT
                or self.availability_status
                is not DecisionReferenceAvailabilityStatus.AVAILABLE
            ):
                raise ValueError("BAR_REVISION reference has an invalid source or state shape")
        else:
            if (
                self.source_gap_id is None
                or self.source_gap_kind not in _GAP_KINDS
                or self.source_gap_reason_code not in _GAP_REASONS
                or self.bar_revision_id is not None
                or self.bar_revision is not None
                or self.decimal_value is not None
            ):
                raise ValueError("SOURCE_GAP reference has an invalid source shape")
            missing = self.source_gap_kind in {"MISSING", "PLACEHOLDER"}
            expected_value = (
                DecisionReferenceValueStatus.UNAVAILABLE
                if missing
                else DecisionReferenceValueStatus.FAILED
            )
            expected_availability = (
                DecisionReferenceAvailabilityStatus.UNAVAILABLE
                if missing
                else DecisionReferenceAvailabilityStatus.FAILED
            )
            if self.value_status is not expected_value or self.availability_status is not expected_availability:
                raise ValueError("SOURCE_GAP reference states do not match its exact gap")


@dataclass(frozen=True, slots=True)
class DecisionRunTargetPlan:
    decision_run_target_id: UUID
    decision_run_id: UUID
    ordinal: int
    target: TargetDecisionSnapshot
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Decision Target ordinal must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "ordinal": self.ordinal,
                    "provider_id": self.target.reference_provider_product.provider_id,
                    "provider_product_id": self.target.reference_provider_product.provider_product_id,
                    "provider_product_revision": self.target.reference_provider_product.revision,
                    "target_checkpoint_id": self.target.target_checkpoint_id,
                    "target_checkpoint_sha256": self.target.checkpoint_content_sha256,
                    "target_definition_id": self.target.target_definition_id,
                    "target_definition_sha256": self.target.content_sha256,
                    "target_version": self.target.version,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class DecisionReferenceObservationPlan:
    decision_reference_observation_id: UUID
    commitment_id: UUID
    decision_run_id: UUID
    decision_run_target_id: UUID
    candidate_set_id: UUID
    candidate_id: UUID
    target_definition_id: UUID
    target_checkpoint_id: UUID
    instrument_id: UUID
    decision_time: datetime
    commitment_recorded_at: datetime
    prepared: PreparedDecisionReference
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _utc(self.decision_time, "reference decision_time"))
        object.__setattr__(
            self,
            "commitment_recorded_at",
            _utc(self.commitment_recorded_at, "reference commitment_recorded_at"),
        )
        if self.prepared.known_at > self.decision_time:
            raise ValueError("reference known_at exceeds DecisionTime")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "availability_status": self.prepared.availability_status,
                    "bar_revision": self.prepared.bar_revision,
                    "bar_revision_id": self.prepared.bar_revision_id,
                    "candidate_id": self.candidate_id,
                    "capture_id": self.prepared.capture_id,
                    "decimal_value": self.prepared.decimal_value,
                    "decision_run_target_id": self.decision_run_target_id,
                    "event_end": self.prepared.event_end,
                    "event_start": self.prepared.event_start,
                    "finality_status": self.prepared.finality_status,
                    "instrument_id": self.instrument_id,
                    "known_at": self.prepared.known_at,
                    "observation_time": self.prepared.observation_time,
                    "price_basis": self.prepared.price_basis,
                    "provider_product_id": self.prepared.provider_product_id,
                    "recorded_at": self.prepared.recorded_at,
                    "session_id": self.prepared.session_id,
                    "source_gap_id": self.prepared.source_gap_id,
                    "source_gap_kind": self.prepared.source_gap_kind,
                    "source_gap_reason_code": self.prepared.source_gap_reason_code,
                    "source_kind": self.prepared.source_kind,
                    "target_checkpoint_id": self.target_checkpoint_id,
                    "timeframe": self.prepared.timeframe,
                    "value_field": self.prepared.value_field,
                    "value_status": self.prepared.value_status,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class DecisionTargetCommitmentPlan:
    commitment_id: UUID
    decision_run_id: UUID
    decision_run_target_id: UUID
    candidate_set_id: UUID
    candidate_id: UUID
    instrument_id: UUID
    candidate_disposition: CandidateDisposition
    target_definition_id: UUID
    decision_time: datetime
    runtime_mode: DecisionRuntimeMode
    commitment_recorded_at: datetime
    reference: DecisionReferenceObservationPlan
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _utc(self.decision_time, "commitment decision_time"))
        object.__setattr__(
            self,
            "commitment_recorded_at",
            _utc(self.commitment_recorded_at, "commitment recorded_at"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "candidate_disposition": self.candidate_disposition,
                    "candidate_id": self.candidate_id,
                    "decision_reference_observation_id": self.reference.decision_reference_observation_id,
                    "decision_reference_sha256": self.reference.content_sha256,
                    "decision_run_target_id": self.decision_run_target_id,
                    "instrument_id": self.instrument_id,
                    "runtime_mode": self.runtime_mode,
                    "target_definition_id": self.target_definition_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class DecisionRunAuthority:
    decision_run_id: UUID
    command_receipt_id: UUID
    candidate_set: CandidateSetDecisionSnapshot
    targets: tuple[DecisionRunTargetPlan, ...]
    commitments: tuple[DecisionTargetCommitmentPlan, ...]
    runtime: RuntimeDecisionSnapshot
    request_identity: str
    request_sha256: str
    request_received_at: datetime
    commitment_recorded_at: datetime
    actor_type: str
    actor_id: str
    reason_code: str
    status: DecisionRunStatus = DecisionRunStatus.OPENED
    candidate_count: int = field(init=False)
    target_count: int = field(init=False)
    commitment_count: int = field(init=False)
    reference_count: int = field(init=False)
    candidate_roster_sha256: str = field(init=False)
    target_roster_sha256: str = field(init=False)
    commitment_roster_sha256: str = field(init=False)
    definition_summary_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_sha256", _hash(self.request_sha256, "Decision request hash"))
        object.__setattr__(self, "request_received_at", _utc(self.request_received_at, "request_received_at"))
        object.__setattr__(
            self,
            "commitment_recorded_at",
            _utc(self.commitment_recorded_at, "commitment_recorded_at"),
        )
        if not _IDEMPOTENCY_KEY.fullmatch(self.request_identity):
            raise ValueError("Decision request identity has an invalid format")
        if self.actor_type not in {"SYSTEM", "OPERATOR", "WORKER"} or not self.actor_id:
            raise ValueError("Decision creation actor provenance is invalid")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", self.reason_code):
            raise ValueError("Decision creation reason code is invalid")
        candidate_count = len(self.candidate_set.candidates)
        target_count = len(self.targets)
        commitment_count = len(self.commitments)
        if target_count < 1:
            raise ValueError("Decision Target roster must be non-empty")
        if commitment_count != candidate_count * target_count:
            raise ValueError("Decision commitment roster is not a complete cross-product")
        object.__setattr__(self, "candidate_count", candidate_count)
        object.__setattr__(self, "target_count", target_count)
        object.__setattr__(self, "commitment_count", commitment_count)
        object.__setattr__(self, "reference_count", commitment_count)
        object.__setattr__(self, "candidate_roster_sha256", self.candidate_set.candidate_roster_sha256)
        target_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": item.content_sha256,
                    "decision_run_target_id": item.decision_run_target_id,
                    "ordinal": item.ordinal,
                }
                for item in self.targets
            )
        )
        commitment_hash = canonical_json_sha256(
            tuple(
                {
                    "commitment_id": item.commitment_id,
                    "content_sha256": item.content_sha256,
                    "decision_run_target_id": item.decision_run_target_id,
                }
                for item in self.commitments
            )
        )
        object.__setattr__(self, "target_roster_sha256", target_hash)
        object.__setattr__(self, "commitment_roster_sha256", commitment_hash)
        object.__setattr__(
            self,
            "definition_summary_sha256",
            canonical_json_sha256(
                {
                    "candidate_count": candidate_count,
                    "candidate_roster_sha256": self.candidate_set.candidate_roster_sha256,
                    "candidate_set_content_sha256": self.candidate_set.content_sha256,
                    "candidate_set_id": self.candidate_set.candidate_set_id,
                    "commitment_count": commitment_count,
                    "commitment_roster_sha256": commitment_hash,
                    "decision_time": self.runtime.decision_time,
                    "reference_count": commitment_count,
                    "request_sha256": self.request_sha256,
                    "runtime_mode": self.runtime.runtime_mode,
                    "target_count": target_count,
                    "target_roster_sha256": target_hash,
                }
            ),
        )


def build_decision_authority(
    *,
    decision_run_id: UUID,
    command_receipt_id: UUID,
    candidate_set: CandidateSetDecisionSnapshot,
    targets: tuple[TargetDecisionSnapshot, ...],
    references: tuple[PreparedDecisionReference, ...],
    runtime: RuntimeDecisionSnapshot,
    request_identity: str,
    request_sha256: str,
    request_received_at: datetime,
    commitment_recorded_at: datetime,
    actor_type: str,
    actor_id: str,
    reason_code: str,
    commitment_id_factory: Callable[[CandidateDecisionFact, TargetDecisionSnapshot], UUID],
    observation_id_factory: Callable[[UUID], UUID],
    target_id_factory: Callable[[TargetDecisionSnapshot, int], UUID] | None = None,
) -> DecisionRunAuthority:
    """Close a prepared immutable cross-product without resolving external facts."""

    RequestedDecisionTarget.roster(
        tuple(
            RequestedDecisionTarget(
                target_definition_id=item.target_definition_id,
                reference_provider_product_id=item.reference_provider_product.provider_product_id,
            )
            for item in targets
        )
    )
    if runtime.decision_time != candidate_set.decision_time:
        raise ValueError("Runtime and CandidateSet DecisionTime must match")
    if commitment_recorded_at < request_received_at:
        raise ValueError("commitment recording cannot precede request receipt")
    target_plans = tuple(
        DecisionRunTargetPlan(
            decision_run_target_id=(
                target_id_factory(target, ordinal)
                if target_id_factory is not None
                else UUID(int=decision_run_id.int ^ target.target_definition_id.int ^ ordinal)
            ),
            decision_run_id=decision_run_id,
            ordinal=ordinal,
            target=target,
        )
        for ordinal, target in enumerate(targets, start=1)
    )
    reference_map: dict[tuple[UUID, UUID], PreparedDecisionReference] = {}
    for reference in references:
        key = (reference.candidate_id, reference.target_definition_id)
        if key in reference_map:
            raise ValueError("Decision reference preparation contains a duplicate")
        reference_map[key] = reference
    expected_keys = {
        (candidate.candidate_id, target.target_definition_id)
        for target in targets
        for candidate in candidate_set.candidates
    }
    if set(reference_map) != expected_keys:
        raise ValueError("Decision reference roster is not the complete cross-product")

    candidates = tuple(sorted(candidate_set.candidates, key=lambda item: str(item.candidate_id)))
    commitments: list[DecisionTargetCommitmentPlan] = []
    seen_commitments: set[UUID] = set()
    seen_observations: set[UUID] = set()
    for target_plan in target_plans:
        target = target_plan.target
        for candidate in candidates:
            prepared = reference_map[(candidate.candidate_id, target.target_definition_id)]
            if (
                prepared.instrument_id != candidate.instrument_id
                or prepared.target_checkpoint_id != target.target_checkpoint_id
                or prepared.provider_product_id
                != target.reference_provider_product.provider_product_id
                or prepared.provider_id != target.reference_provider_product.provider_id
                or prepared.timeframe != target.timeframe
                or prepared.price_basis != target.price_basis
                or prepared.value_field != target.value_field
            ):
                raise ValueError("Decision reference does not match Candidate and Target facts")
            commitment_id = commitment_id_factory(candidate, target)
            observation_id = observation_id_factory(commitment_id)
            if commitment_id in seen_commitments or observation_id in seen_observations:
                raise ValueError("Decision commitment/reference identities must be unique")
            seen_commitments.add(commitment_id)
            seen_observations.add(observation_id)
            observation = DecisionReferenceObservationPlan(
                decision_reference_observation_id=observation_id,
                commitment_id=commitment_id,
                decision_run_id=decision_run_id,
                decision_run_target_id=target_plan.decision_run_target_id,
                candidate_set_id=candidate_set.candidate_set_id,
                candidate_id=candidate.candidate_id,
                target_definition_id=target.target_definition_id,
                target_checkpoint_id=target.target_checkpoint_id,
                instrument_id=candidate.instrument_id,
                decision_time=runtime.decision_time,
                commitment_recorded_at=commitment_recorded_at,
                prepared=prepared,
            )
            commitments.append(
                DecisionTargetCommitmentPlan(
                    commitment_id=commitment_id,
                    decision_run_id=decision_run_id,
                    decision_run_target_id=target_plan.decision_run_target_id,
                    candidate_set_id=candidate_set.candidate_set_id,
                    candidate_id=candidate.candidate_id,
                    instrument_id=candidate.instrument_id,
                    candidate_disposition=candidate.disposition,
                    target_definition_id=target.target_definition_id,
                    decision_time=runtime.decision_time,
                    runtime_mode=runtime.runtime_mode,
                    commitment_recorded_at=commitment_recorded_at,
                    reference=observation,
                )
            )
    return DecisionRunAuthority(
        decision_run_id=decision_run_id,
        command_receipt_id=command_receipt_id,
        candidate_set=candidate_set,
        targets=target_plans,
        commitments=tuple(commitments),
        runtime=runtime,
        request_identity=request_identity,
        request_sha256=request_sha256,
        request_received_at=request_received_at,
        commitment_recorded_at=commitment_recorded_at,
        actor_type=actor_type,
        actor_id=actor_id,
        reason_code=reason_code,
    )


__all__ = [
    "CandidateDecisionFact",
    "CandidateSetDecisionSnapshot",
    "DecisionReferenceObservationPlan",
    "DecisionRunAuthority",
    "DecisionRunTargetPlan",
    "DecisionTargetCommitmentPlan",
    "OpenDecisionRunRequest",
    "PreparedDecisionInputs",
    "PreparedDecisionReference",
    "ProviderProductDecisionSnapshot",
    "RequestedDecisionTarget",
    "RuntimeDecisionSnapshot",
    "TargetDecisionSnapshot",
    "build_decision_authority",
]
