"""Closed relational Market Target Outcome authority models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import re
from uuid import UUID

from market_regime_alpha.outcome.domain.model import (
    FrozenDecisionReference,
    OutcomeObservationSource,
    OutcomeRevisionDraft,
    OutcomeSessionSource,
    OutcomeTargetDefinition,
)
from market_regime_alpha.outcome.domain.vocabulary import (
    OutcomeReasonDimension,
    OutcomeSourceRole,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_RUNTIME_MODES = frozenset(
    {"OPERATIONAL", "HISTORICAL", "REPLAY", "SHADOW", "PROSPECTIVE"}
)


def _sha(value: str, label: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class OutcomeCommitmentSnapshot:
    commitment_id: UUID
    decision_run_id: UUID
    decision_run_target_id: UUID
    candidate_set_id: UUID
    candidate_id: UUID
    instrument_id: UUID
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: str
    target_checkpoint_id: UUID
    reference_provider_product_id: UUID
    reference_capture_id: UUID
    reference_session_id: UUID
    reference_source_kind: str
    reference_fact_id: UUID
    reference_known_at: datetime
    decision_time: datetime
    runtime_mode: str
    commitment_recorded_at: datetime
    reference: FrozenDecisionReference

    def __post_init__(self) -> None:
        if self.target_version < 1:
            raise ValueError("Outcome commitment Target version must be positive")
        _sha(self.target_definition_sha256, "Outcome commitment Target hash")
        object.__setattr__(
            self,
            "decision_time",
            require_utc(self.decision_time, field="Outcome commitment DecisionTime"),
        )
        object.__setattr__(
            self,
            "commitment_recorded_at",
            require_utc(
                self.commitment_recorded_at,
                field="Outcome commitment recorded time",
            ),
        )
        object.__setattr__(
            self,
            "reference_known_at",
            require_utc(self.reference_known_at, field="Decision reference known_at"),
        )
        if self.runtime_mode not in _RUNTIME_MODES:
            raise ValueError("Outcome commitment Runtime mode is invalid")
        if self.commitment_recorded_at < self.decision_time:
            raise ValueError("Outcome commitment cannot precede DecisionTime")
        if self.reference_known_at > self.decision_time:
            raise ValueError("Outcome Decision reference was not known by DecisionTime")
        if self.reference_source_kind not in {"BAR_REVISION", "SOURCE_GAP"}:
            raise ValueError("Outcome Decision reference source kind is invalid")

    @property
    def decision_reference_observation_id(self) -> UUID:
        return self.reference.decision_reference_observation_id

    @property
    def decision_reference_sha256(self) -> str:
        return self.reference.content_sha256


@dataclass(frozen=True, slots=True)
class OutcomeRuntimeSnapshot:
    run_id: UUID
    step_id: UUID
    attempt_id: UUID
    fence_token: int
    step_key: str
    step_kind: str
    runtime_mode: str
    decision_time: datetime
    code_sha: str
    config_artifact_id: UUID
    config_hash: str

    def __post_init__(self) -> None:
        if self.fence_token < 1 or not self.step_key:
            raise ValueError("Outcome Runtime fence/Step key is invalid")
        if self.step_kind != "SETTLE_OUTCOME":
            raise ValueError("Outcome settlement requires SETTLE_OUTCOME")
        if self.runtime_mode not in _RUNTIME_MODES:
            raise ValueError("Outcome Runtime mode is invalid")
        object.__setattr__(
            self,
            "decision_time",
            require_utc(self.decision_time, field="Outcome Runtime DecisionTime"),
        )
        if not _CODE_SHA.fullmatch(self.code_sha):
            raise ValueError("Outcome Runtime code identity is invalid")
        _sha(self.config_hash, "Outcome Runtime config hash")


@dataclass(frozen=True, slots=True)
class OutcomeRootAuthority:
    market_target_outcome_id: UUID
    commitment: OutcomeCommitmentSnapshot
    created_at: datetime

    @property
    def decision_reference_observation_id(self) -> UUID:
        return self.commitment.decision_reference_observation_id


@dataclass(frozen=True, slots=True)
class OutcomeSourceAuthority:
    market_target_outcome_source_id: UUID
    ordinal: int
    session: OutcomeSessionSource
    observation_source: OutcomeObservationSource | None
    target_checkpoint_id: UUID | None
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    content_sha256: str = field(init=False)

    @property
    def source_role(self) -> OutcomeSourceRole:
        return (
            OutcomeSourceRole.CALENDAR_SESSION
            if self.observation_source is None
            else OutcomeSourceRole.OUTCOME_OBSERVATION
        )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "knowledge_cutoff": self.knowledge_cutoff,
                    "observation_cutoff": self.observation_cutoff,
                    "observation_source": self.observation_source,
                    "ordinal": self.ordinal,
                    "session": self.session,
                    "target_checkpoint_id": self.target_checkpoint_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class OutcomeObservationAuthority:
    market_target_outcome_observation_id: UUID
    ordinal: int
    market_target_outcome_source_id: UUID
    draft_index: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class OutcomeMetricAuthority:
    market_target_outcome_metric_id: UUID
    ordinal: int
    draft_index: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class OutcomeReferenceDependencyAuthority:
    market_target_outcome_metric_reference_id: UUID
    ordinal: int
    draft_index: int
    market_target_outcome_metric_id: UUID
    target_dependency_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class OutcomeObservationDependencyAuthority:
    market_target_outcome_metric_observation_id: UUID
    ordinal: int
    draft_index: int
    market_target_outcome_metric_id: UUID
    market_target_outcome_observation_id: UUID
    target_dependency_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class OutcomeReasonAuthority:
    market_target_outcome_reason_id: UUID
    ordinal: int
    draft_index: int
    market_target_outcome_source_id: UUID | None
    market_target_outcome_observation_id: UUID | None
    market_target_outcome_metric_id: UUID | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class OutcomeRevisionAuthority:
    market_target_outcome_revision_id: UUID
    market_target_outcome_id: UUID
    revision_ordinal: int
    supersedes_revision_id: UUID | None
    supersedes_revision_ordinal: int | None
    draft: OutcomeRevisionDraft
    sources: tuple[OutcomeSourceAuthority, ...]
    observations: tuple[OutcomeObservationAuthority, ...]
    metrics: tuple[OutcomeMetricAuthority, ...]
    reference_dependencies: tuple[OutcomeReferenceDependencyAuthority, ...]
    observation_dependencies: tuple[OutcomeObservationDependencyAuthority, ...]
    reasons: tuple[OutcomeReasonAuthority, ...]
    runtime: OutcomeRuntimeSnapshot
    request_identity: str
    request_sha256: str
    request_received_at: datetime
    settled_at: datetime
    command_receipt_id: UUID
    actor_type: str
    actor_id: str
    reason_code: str
    source_roster_sha256: str = field(init=False)
    observation_roster_sha256: str = field(init=False)
    metric_roster_sha256: str = field(init=False)
    reference_dependency_roster_sha256: str = field(init=False)
    observation_dependency_roster_sha256: str = field(init=False)
    reason_roster_sha256: str = field(init=False)
    definition_summary_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        expected_supersedes_ordinal = (
            None if self.revision_ordinal == 1 else self.revision_ordinal - 1
        )
        if self.revision_ordinal < 1 or (
            (self.revision_ordinal == 1) != (self.supersedes_revision_id is None)
        ):
            raise ValueError("Outcome revision predecessor shape is invalid")
        if self.supersedes_revision_ordinal != expected_supersedes_ordinal:
            raise ValueError("Outcome revision predecessor ordinal is invalid")
        if not _IDEMPOTENCY_KEY.fullmatch(self.request_identity):
            raise ValueError("Outcome request identity is invalid")
        _sha(self.request_sha256, "Outcome request hash")
        if not self.actor_id or not _REASON_CODE.fullmatch(self.reason_code):
            raise ValueError("Outcome creation provenance is invalid")
        received = require_utc(
            self.request_received_at,
            field="Outcome request received time",
        )
        settled = require_utc(self.settled_at, field="Outcome settled time")
        object.__setattr__(self, "request_received_at", received)
        object.__setattr__(self, "settled_at", settled)
        if settled < received:
            raise ValueError("Outcome settlement cannot precede request receipt")
        rosters: tuple[tuple[str, str, tuple[object, ...]], ...] = (
            (
                "source_roster_sha256",
                "market_target_outcome_source_id",
                self.sources,
            ),
            (
                "observation_roster_sha256",
                "market_target_outcome_observation_id",
                self.observations,
            ),
            (
                "metric_roster_sha256",
                "market_target_outcome_metric_id",
                self.metrics,
            ),
            (
                "reference_dependency_roster_sha256",
                "market_target_outcome_metric_reference_id",
                self.reference_dependencies,
            ),
            (
                "observation_dependency_roster_sha256",
                "market_target_outcome_metric_observation_id",
                self.observation_dependencies,
            ),
            (
                "reason_roster_sha256",
                "market_target_outcome_reason_id",
                self.reasons,
            ),
        )
        for name, identity_name, values in rosters:
            object.__setattr__(
                self,
                name,
                canonical_json_sha256(
                    tuple(
                        {
                            "content_sha256": getattr(item, "content_sha256"),
                            identity_name: getattr(item, identity_name),
                            "ordinal": getattr(item, "ordinal"),
                        }
                        for item in values
                    )
                ),
            )
        object.__setattr__(
            self,
            "definition_summary_sha256",
            canonical_json_sha256(
                {
                    "availability_status": self.draft.availability_status,
                    "decision_reference_observation_id": (
                        self.draft.decision_reference_observation_id
                    ),
                    "decision_reference_sha256": (
                        self.draft.decision_reference_sha256
                    ),
                    "finality_status": self.draft.finality_status,
                    "knowledge_cutoff": self.draft.knowledge_cutoff,
                    "metric_count": self.metric_count,
                    "metric_roster_sha256": self.metric_roster_sha256,
                    "observation_count": self.observation_count,
                    "observation_cutoff": self.draft.observation_cutoff,
                    "observation_dependency_count": (
                        self.observation_dependency_count
                    ),
                    "observation_dependency_roster_sha256": (
                        self.observation_dependency_roster_sha256
                    ),
                    "observation_roster_sha256": self.observation_roster_sha256,
                    "outcome_status": self.draft.status,
                    "reason_count": self.reason_count,
                    "reason_roster_sha256": self.reason_roster_sha256,
                    "reference_dependency_count": (
                        self.reference_dependency_count
                    ),
                    "reference_dependency_roster_sha256": (
                        self.reference_dependency_roster_sha256
                    ),
                    "source_count": self.source_count,
                    "source_roster_sha256": self.source_roster_sha256,
                    "target_definition_id": self.draft.target_definition_id,
                    "target_definition_sha256": (
                        self.draft.target_definition_sha256
                    ),
                }
            ),
        )

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @property
    def observation_count(self) -> int:
        return len(self.observations)

    @property
    def metric_count(self) -> int:
        return len(self.metrics)

    @property
    def reference_dependency_count(self) -> int:
        return len(self.reference_dependencies)

    @property
    def observation_dependency_count(self) -> int:
        return len(self.observation_dependencies)

    @property
    def reason_count(self) -> int:
        return len(self.reasons)


@dataclass(frozen=True, slots=True)
class MarketTargetOutcomeAuthority:
    root: OutcomeRootAuthority
    revision: OutcomeRevisionAuthority
    commitment: OutcomeCommitmentSnapshot
    target: OutcomeTargetDefinition


@dataclass(frozen=True, slots=True)
class MarketTargetOutcomeIdentityPlan:
    market_target_outcome_id: UUID
    market_target_outcome_revision_id: UUID
    source_ids: tuple[UUID, ...]
    observation_ids: tuple[UUID, ...]
    metric_ids: tuple[UUID, ...]
    reference_dependency_ids: tuple[UUID, ...]
    observation_dependency_ids: tuple[UUID, ...]
    reason_ids: tuple[UUID, ...]

    @classmethod
    def create(
        cls,
        draft: OutcomeRevisionDraft,
        id_factory: Callable[[], UUID],
        *,
        market_target_outcome_id: UUID | None = None,
    ) -> MarketTargetOutcomeIdentityPlan:
        return cls(
            market_target_outcome_id=market_target_outcome_id or id_factory(),
            market_target_outcome_revision_id=id_factory(),
            source_ids=tuple(
                id_factory() for _ in (*draft.sessions, *draft.sources)
            ),
            observation_ids=tuple(id_factory() for _ in draft.observations),
            metric_ids=tuple(id_factory() for _ in draft.metrics),
            reference_dependency_ids=tuple(
                id_factory() for _ in draft.reference_dependencies
            ),
            observation_dependency_ids=tuple(
                id_factory() for _ in draft.observation_dependencies
            ),
            reason_ids=tuple(id_factory() for _ in draft.reasons),
        )


def build_market_target_outcome_authority(
    *,
    identities: MarketTargetOutcomeIdentityPlan,
    commitment: OutcomeCommitmentSnapshot,
    target: OutcomeTargetDefinition,
    draft: OutcomeRevisionDraft,
    runtime: OutcomeRuntimeSnapshot,
    revision_ordinal: int,
    supersedes_revision_id: UUID | None,
    request_identity: str,
    request_sha256: str,
    request_received_at: datetime,
    settled_at: datetime,
    command_receipt_id: UUID,
    actor_type: str,
    actor_id: str,
    reason_code: str,
) -> MarketTargetOutcomeAuthority:
    """Materialize one fully identified relational revision from the pure draft."""

    if (
        commitment.target_definition_id != target.target_definition_id
        or commitment.target_version != target.version
        or commitment.target_definition_sha256 != target.content_sha256
        or commitment.target_checkpoint_id != target.reference_checkpoint_id
        or commitment.reference != _reference_from_draft(commitment.reference, draft)
    ):
        raise ValueError("Outcome commitment, Target, reference, and draft differ")
    session_by_offset = {item.session_offset: item for item in draft.sessions}
    sources: list[OutcomeSourceAuthority] = []
    for ordinal, (source_id, session) in enumerate(
        zip(identities.source_ids, draft.sessions, strict=False),
        start=1,
    ):
        sources.append(
            OutcomeSourceAuthority(
                market_target_outcome_source_id=source_id,
                ordinal=ordinal,
                session=session,
                observation_source=None,
                target_checkpoint_id=None,
                observation_cutoff=draft.observation_cutoff,
                knowledge_cutoff=draft.knowledge_cutoff,
            )
        )
    checkpoint_by_id = {
        item.target_checkpoint_id: item for item in target.checkpoints
    }
    observation_source_ids: dict[UUID, UUID] = {}
    offset = len(draft.sessions)
    for index, source in enumerate(draft.sources):
        checkpoint = checkpoint_by_id[source.target_checkpoint_id]
        source_id = identities.source_ids[offset + index]
        observation_source_ids[source.target_checkpoint_id] = source_id
        sources.append(
            OutcomeSourceAuthority(
                market_target_outcome_source_id=source_id,
                ordinal=offset + index + 1,
                session=session_by_offset[checkpoint.session_offset],
                observation_source=source,
                target_checkpoint_id=source.target_checkpoint_id,
                observation_cutoff=draft.observation_cutoff,
                knowledge_cutoff=draft.knowledge_cutoff,
            )
        )
    if len(sources) != len(identities.source_ids):
        raise ValueError("Outcome source identity plan does not match draft")

    observations = tuple(
        OutcomeObservationAuthority(
            market_target_outcome_observation_id=observation_id,
            ordinal=index + 1,
            market_target_outcome_source_id=observation_source_ids[
                observation.target_checkpoint_id
            ],
            draft_index=index,
            content_sha256=canonical_json_sha256(
                {
                    "draft_sha256": observation.content_sha256,
                    "market_target_outcome_source_id": observation_source_ids[
                        observation.target_checkpoint_id
                    ],
                    "observation_cutoff": draft.observation_cutoff,
                    "knowledge_cutoff": draft.knowledge_cutoff,
                }
            ),
        )
        for index, (observation_id, observation) in enumerate(
            zip(identities.observation_ids, draft.observations, strict=True)
        )
    )
    metrics = tuple(
        OutcomeMetricAuthority(
            market_target_outcome_metric_id=metric_id,
            ordinal=metric.ordinal,
            draft_index=index,
            content_sha256=canonical_json_sha256(
                {
                    "draft_sha256": metric.content_sha256,
                    "target_definition_id": target.target_definition_id,
                }
            ),
        )
        for index, (metric_id, metric) in enumerate(
            zip(identities.metric_ids, draft.metrics, strict=True)
        )
    )
    metric_id_by_definition = {
        draft.metrics[item.draft_index].target_metric_definition_id: (
            item.market_target_outcome_metric_id
        )
        for item in metrics
    }
    observation_id_by_checkpoint = {
        draft.observations[item.draft_index].target_checkpoint_id: (
            item.market_target_outcome_observation_id
        )
        for item in observations
    }
    dependency_hash_by_id = {
        item.target_metric_dependency_id: item.content_sha256
        for item in target.dependencies
    }
    dependency_ordinal_by_id = {
        item.target_metric_dependency_id: item.ordinal for item in target.dependencies
    }
    reference_dependencies = tuple(
        OutcomeReferenceDependencyAuthority(
            market_target_outcome_metric_reference_id=dependency_id,
            ordinal=dependency_ordinal_by_id[
                dependency.target_metric_dependency_id
            ],
            draft_index=item_index,
            market_target_outcome_metric_id=metric_id_by_definition[
                dependency.target_metric_definition_id
            ],
            target_dependency_sha256=dependency_hash_by_id[
                dependency.target_metric_dependency_id
            ],
            content_sha256=canonical_json_sha256(
                {
                    "decision_reference_observation_id": (
                        dependency.decision_reference_observation_id
                    ),
                    "market_target_outcome_metric_id": metric_id_by_definition[
                        dependency.target_metric_definition_id
                    ],
                    "target_dependency_sha256": dependency_hash_by_id[
                        dependency.target_metric_dependency_id
                    ],
                    "target_metric_dependency_id": (
                        dependency.target_metric_dependency_id
                    ),
                }
            ),
        )
        for item_index, (dependency_id, dependency) in enumerate(
            zip(
                identities.reference_dependency_ids,
                draft.reference_dependencies,
                strict=True,
            )
        )
    )
    observation_dependencies = tuple(
        OutcomeObservationDependencyAuthority(
            market_target_outcome_metric_observation_id=dependency_id,
            ordinal=dependency_ordinal_by_id[
                dependency.target_metric_dependency_id
            ],
            draft_index=item_index,
            market_target_outcome_metric_id=metric_id_by_definition[
                dependency.target_metric_definition_id
            ],
            market_target_outcome_observation_id=observation_id_by_checkpoint[
                dependency.target_checkpoint_id
            ],
            target_dependency_sha256=dependency_hash_by_id[
                dependency.target_metric_dependency_id
            ],
            content_sha256=canonical_json_sha256(
                {
                    "market_target_outcome_metric_id": metric_id_by_definition[
                        dependency.target_metric_definition_id
                    ],
                    "market_target_outcome_observation_id": (
                        observation_id_by_checkpoint[dependency.target_checkpoint_id]
                    ),
                    "target_dependency_sha256": dependency_hash_by_id[
                        dependency.target_metric_dependency_id
                    ],
                    "target_metric_dependency_id": (
                        dependency.target_metric_dependency_id
                    ),
                }
            ),
        )
        for item_index, (dependency_id, dependency) in enumerate(
            zip(
                identities.observation_dependency_ids,
                draft.observation_dependencies,
                strict=True,
            )
        )
    )
    source_id_by_checkpoint = observation_source_ids
    reasons: list[OutcomeReasonAuthority] = []
    for index, (reason_id, reason) in enumerate(
        zip(identities.reason_ids, draft.reasons, strict=True)
    ):
        reason_source_id: UUID | None = None
        reason_observation_id: UUID | None = None
        reason_metric_id: UUID | None = None
        if reason.dimension is OutcomeReasonDimension.SOURCE:
            if reason.target_checkpoint_id is None:
                raise ValueError("Outcome SOURCE reason lacks a checkpoint")
            reason_source_id = source_id_by_checkpoint[reason.target_checkpoint_id]
        elif reason.dimension is OutcomeReasonDimension.OBSERVATION:
            if reason.target_checkpoint_id is None:
                raise ValueError("Outcome OBSERVATION reason lacks a checkpoint")
            reason_observation_id = observation_id_by_checkpoint[
                reason.target_checkpoint_id
            ]
        elif reason.dimension is OutcomeReasonDimension.METRIC:
            if reason.target_metric_definition_id is None:
                raise ValueError("Outcome METRIC reason lacks a metric")
            reason_metric_id = metric_id_by_definition[
                reason.target_metric_definition_id
            ]
        reasons.append(
            OutcomeReasonAuthority(
                market_target_outcome_reason_id=reason_id,
                ordinal=reason.ordinal,
                draft_index=index,
                market_target_outcome_source_id=reason_source_id,
                market_target_outcome_observation_id=reason_observation_id,
                market_target_outcome_metric_id=reason_metric_id,
                content_sha256=canonical_json_sha256(
                    {
                        "market_target_outcome_metric_id": reason_metric_id,
                        "market_target_outcome_observation_id": (
                            reason_observation_id
                        ),
                        "market_target_outcome_source_id": reason_source_id,
                        "reason_code": reason.reason_code,
                        "reason_dimension": reason.dimension,
                    }
                ),
            )
        )
    revision = OutcomeRevisionAuthority(
        market_target_outcome_revision_id=(
            identities.market_target_outcome_revision_id
        ),
        market_target_outcome_id=identities.market_target_outcome_id,
        revision_ordinal=revision_ordinal,
        supersedes_revision_id=supersedes_revision_id,
        supersedes_revision_ordinal=(
            None if supersedes_revision_id is None else revision_ordinal - 1
        ),
        draft=draft,
        sources=tuple(sources),
        observations=observations,
        metrics=metrics,
        reference_dependencies=reference_dependencies,
        observation_dependencies=observation_dependencies,
        reasons=tuple(reasons),
        runtime=runtime,
        request_identity=request_identity,
        request_sha256=request_sha256,
        request_received_at=request_received_at,
        settled_at=settled_at,
        command_receipt_id=command_receipt_id,
        actor_type=actor_type,
        actor_id=actor_id,
        reason_code=reason_code,
    )
    return MarketTargetOutcomeAuthority(
        root=OutcomeRootAuthority(
            market_target_outcome_id=identities.market_target_outcome_id,
            commitment=commitment,
            created_at=settled_at,
        ),
        revision=revision,
        commitment=commitment,
        target=target,
    )


def _reference_from_draft(
    reference: FrozenDecisionReference,
    draft: OutcomeRevisionDraft,
) -> FrozenDecisionReference:
    if (
        reference.decision_reference_observation_id
        != draft.decision_reference_observation_id
        or reference.content_sha256 != draft.decision_reference_sha256
    ):
        raise ValueError("Outcome draft did not preserve the frozen Decision reference")
    return reference


__all__ = [
    "MarketTargetOutcomeAuthority",
    "MarketTargetOutcomeIdentityPlan",
    "OutcomeCommitmentSnapshot",
    "OutcomeMetricAuthority",
    "OutcomeObservationAuthority",
    "OutcomeObservationDependencyAuthority",
    "OutcomeReasonAuthority",
    "OutcomeReferenceDependencyAuthority",
    "OutcomeRevisionAuthority",
    "OutcomeRootAuthority",
    "OutcomeRuntimeSnapshot",
    "OutcomeSourceAuthority",
    "build_market_target_outcome_authority",
]
