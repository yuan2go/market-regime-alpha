"""Owner-controlled Formal Forecast computation contracts.

The request deliberately has no value or timestamp fields. PostgreSQL resolves
all inputs, assigns materialization time and persists the immutable receipt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetForecastEstimate,
    not_estimable_target_forecast,
)
from market_regime_alpha.application.research_validation.forecast_measure_kernel import (
    compute_regularized_measure_forecast,
)
from market_regime_alpha.application.research_validation.research_model import (
    RESEARCH_MODEL_IMPLEMENTATION,
    ResearchModelArtifact,
    ResearchModelTrainingRequest,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    PITFactKind,
    PITFactRevision,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.platform.runtime_governance import ModelVersionLineage


@dataclass(frozen=True, slots=True)
class FormalForecastComputationRequest:
    request_hash: str
    formal_protocol_id: ArtifactId
    formal_pit_evidence_id: ArtifactId
    symbol: str
    idempotency_key: str
    schema_version: str = "formal-forecast-computation-request/v1"

    def __post_init__(self) -> None:
        require_sha256("Formal Forecast request hash", self.request_hash)
        require_text("Formal Forecast symbol", self.symbol)
        require_text("Formal Forecast idempotency key", self.idempotency_key)
        if self.schema_version != "formal-forecast-computation-request/v1":
            raise ValueError("unsupported Formal Forecast computation request schema")
        if canonical_hash(self.identity_payload()) != self.request_hash:
            raise ValueError("Formal Forecast computation request hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        formal_protocol_id: ArtifactId,
        formal_pit_evidence_id: ArtifactId,
        symbol: str,
        idempotency_key: str,
    ) -> FormalForecastComputationRequest:
        payload = _request_payload(
            formal_protocol_id=formal_protocol_id,
            formal_pit_evidence_id=formal_pit_evidence_id,
            symbol=symbol,
            idempotency_key=idempotency_key,
        )
        return cls(
            canonical_hash(payload),
            formal_protocol_id,
            formal_pit_evidence_id,
            symbol,
            idempotency_key,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _request_payload(
            formal_protocol_id=self.formal_protocol_id,
            formal_pit_evidence_id=self.formal_pit_evidence_id,
            symbol=self.symbol,
            idempotency_key=self.idempotency_key,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"request_hash": self.request_hash, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalForecastComputationRequest:
        expected = {
            "schema_version",
            "request_hash",
            "formal_protocol_id",
            "formal_pit_evidence_id",
            "symbol",
            "idempotency_key",
        }
        if set(value) != expected:
            raise ValueError("Formal Forecast computation request fields mismatch")
        return cls(
            request_hash=str(value["request_hash"]),
            formal_protocol_id=ArtifactId(str(value["formal_protocol_id"])),
            formal_pit_evidence_id=ArtifactId(
                str(value["formal_pit_evidence_id"])
            ),
            symbol=str(value["symbol"]),
            idempotency_key=str(value["idempotency_key"]),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ResolvedFormalForecastContext:
    protocol: FormalResearchProtocol
    target_protocol: OutcomeTargetProtocol
    formal_pit_evidence: FormalPITEvidenceArtifact
    model_lineage: ModelVersionLineage
    model_definition_payload: Mapping[str, Any]
    configuration_reference: ValidationArtifactReference
    component_owner_payloads: tuple[tuple[str, Mapping[str, Any]], ...]
    selected_fact_references: tuple[ValidationArtifactReference, ...]
    selected_fact_payloads: tuple[Mapping[str, Any], ...]
    research_model_artifact: ResearchModelArtifact | None
    research_model_training_request: ResearchModelTrainingRequest | None
    symbol: str
    decision_time: datetime
    materialized_at: datetime

    def __post_init__(self) -> None:
        if self.decision_time.tzinfo is None or self.decision_time.utcoffset() is None:
            raise ValueError("Formal Forecast DecisionTime must be timezone-aware")
        if self.materialized_at.tzinfo is None or self.materialized_at.utcoffset() is None:
            raise ValueError("Formal Forecast materialization time must be timezone-aware")
        if self.materialized_at < self.decision_time:
            raise ValueError("Formal Forecast cannot materialize before DecisionTime")
        if self.selected_fact_references != tuple(
            sorted(set(self.selected_fact_references), key=_reference_key)
        ):
            raise ValueError("Formal Forecast selected Facts must be unique and sorted")
        if tuple(role for role, _payload in self.component_owner_payloads) != tuple(
            sorted({role for role, _payload in self.component_owner_payloads})
        ):
            raise ValueError("Formal Forecast component owner payloads must be unique and sorted")
        if len(self.selected_fact_payloads) != len(self.selected_fact_references):
            raise ValueError("Formal Forecast PIT Fact payload/reference cardinality mismatch")
        if (self.research_model_artifact is None) != (
            self.research_model_training_request is None
        ):
            raise ValueError("Formal Forecast model artifact/request pairing mismatch")


class FormalForecastExecutor(Protocol):
    """One installed, versioned computation implementation.

    Implementations belong to reviewed application composition. There is no
    per-request injection, dynamic import or caller-selected plugin name.
    """

    @property
    def executor_identity(self) -> str: ...

    @property
    def implementation_ref(self) -> str: ...

    def supports(self, context: ResolvedFormalForecastContext) -> bool: ...

    def compute(
        self, context: ResolvedFormalForecastContext
    ) -> tuple[OutcomeTargetForecastEstimate, ...]: ...


@dataclass(frozen=True, slots=True)
class FormalForecastExecutorSet:
    executors: tuple[FormalForecastExecutor, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.executor_identity for item in self.executors)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("Formal Forecast executors must be unique and sorted")

    def compute(
        self, context: ResolvedFormalForecastContext
    ) -> tuple[str, tuple[OutcomeTargetForecastEstimate, ...]]:
        supported = tuple(
            item
            for item in self.executors
            if _executor_matches_frozen_lineage(item, context) and item.supports(context)
        )
        if len(supported) > 1:
            raise ValueError("Formal Forecast executor selection is ambiguous")
        if not supported:
            return (
                "formal-forecast-executor:unsupported/v1",
                not_estimable_estimates(
                    context.target_protocol,
                    reason_codes=("FORMAL_FORECAST_EXECUTOR_UNSUPPORTED",),
                ),
            )
        executor = supported[0]
        estimates = executor.compute(context)
        expected = tuple(
            (item.target_id, item.target_hash) for item in context.target_protocol.targets
        )
        actual = tuple((item.target_id, item.target_hash) for item in estimates)
        if actual != expected:
            raise ValueError("Formal Forecast executor returned a non-frozen Target set")
        return executor.executor_identity, estimates


@dataclass(frozen=True, slots=True)
class RegularizedFormalForecastExecutor:
    """Owner-resolved adapter around the qualification-independent math kernel."""

    executor_identity: str = "formal-forecast:deterministic-regularized-linear/v1"
    implementation_ref: str = RESEARCH_MODEL_IMPLEMENTATION

    def supports(self, context: ResolvedFormalForecastContext) -> bool:
        artifact = context.research_model_artifact
        training = context.research_model_training_request
        experiment = context.protocol.experiment_definition
        return bool(
            artifact is not None
            and training is not None
            and artifact.model is not None
            and artifact.model_parameter_hash == context.model_lineage.model_parameter_hash
            and training.schema_version == "research-model-training-request/v2"
            and training.experiment_definition is not None
            and experiment is not None
            and training.experiment_definition.definition_id == experiment.definition_id
            and training.experiment_definition.definition_hash == experiment.definition_hash
            and training.feature_catalog_reference == context.protocol.feature_reference
            and training.target_protocol_reference.artifact_id
            == context.target_protocol.protocol_id
            and training.target_protocol_reference.content_hash
            == context.target_protocol.protocol_hash
            and training.model_definition_reference.content_hash
            == context.model_lineage.definition_hash
            and training.configuration_reference == context.configuration_reference
            and training.code_revision == context.model_lineage.code_revision
            and training.code_hash == context.model_lineage.code_hash
        )

    def compute(
        self, context: ResolvedFormalForecastContext
    ) -> tuple[OutcomeTargetForecastEstimate, ...]:
        artifact = context.research_model_artifact
        training = context.research_model_training_request
        if artifact is None or artifact.model is None or training is None:
            return not_estimable_estimates(
                context.target_protocol,
                reason_codes=("EXECUTABLE_MODEL_PARAMETER_OWNER_MISSING",),
            )
        values, reasons = _formal_feature_values(
            context,
            expected_names=artifact.model.feature_names,
        )
        if reasons:
            return not_estimable_estimates(
                context.target_protocol,
                reason_codes=reasons,
            )
        return compute_regularized_measure_forecast(
            model=artifact.model,
            bindings=training.measure_bindings,
            target_protocol=context.target_protocol,
            feature_values=values,
        )


# Installed executors are code-owned runtime composition, not a request argument.
_INSTALLED_FORMAL_FORECAST_EXECUTORS = FormalForecastExecutorSet(
    (RegularizedFormalForecastExecutor(),)
)


def installed_formal_forecast_executors() -> FormalForecastExecutorSet:
    return _INSTALLED_FORMAL_FORECAST_EXECUTORS


def _executor_matches_frozen_lineage(
    executor: FormalForecastExecutor,
    context: ResolvedFormalForecastContext,
) -> bool:
    return executor.implementation_ref == context.model_lineage.implementation_ref


def _formal_feature_values(
    context: ResolvedFormalForecastContext,
    *,
    expected_names: tuple[str, ...],
) -> tuple[dict[str, Decimal | None], tuple[str, ...]]:
    vectors: list[Mapping[str, Any]] = []
    reasons: set[str] = set()
    for payload in context.selected_fact_payloads:
        try:
            fact = PITFactRevision.from_canonical_dict(payload)
        except (KeyError, TypeError, ValueError):
            reasons.add("PIT_FACT_REPLAY_FAILED")
            continue
        if fact.fact_kind is not PITFactKind.FEATURE_MATERIALIZATION:
            continue
        try:
            value = json.loads(fact.value_json)
        except json.JSONDecodeError:
            reasons.add("FEATURE_VALUE_JSON_INVALID")
            continue
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "symbol",
            "decision_time",
            "features",
        }:
            reasons.add("FEATURE_VECTOR_CONTRACT_MISMATCH")
            continue
        if (
            value["schema_version"] != "forecast-feature-vector/v1"
            or value["symbol"] != context.symbol
            or value["decision_time"] != context.decision_time.isoformat()
            or not isinstance(value["features"], dict)
        ):
            reasons.add("FEATURE_VECTOR_IDENTITY_MISMATCH")
            continue
        vectors.append(value["features"])
    if len(vectors) != 1:
        reasons.add("EXACTLY_ONE_FEATURE_VECTOR_REQUIRED")
    if reasons:
        return {}, tuple(sorted(reasons))
    raw = vectors[0]
    if tuple(sorted(str(name) for name in raw)) != expected_names:
        return {}, ("FROZEN_FEATURE_SET_MISMATCH",)
    values: dict[str, Decimal | None] = {}
    try:
        for name in expected_names:
            item = raw[name]
            values[name] = None if item is None else Decimal(str(item))
            if values[name] is not None and not values[name].is_finite():
                raise ValueError("non-finite")
    except (KeyError, TypeError, ValueError):
        return {}, ("FEATURE_VALUE_NOT_FINITE_DECIMAL",)
    return values, ()


def not_estimable_estimates(
    target_protocol: OutcomeTargetProtocol,
    *,
    reason_codes: tuple[str, ...],
) -> tuple[OutcomeTargetForecastEstimate, ...]:
    reasons = tuple(sorted(set(reason_codes)))
    if not reasons:
        raise ValueError("NOT_ESTIMABLE Formal Forecast requires reason codes")
    return tuple(
        not_estimable_target_forecast(
            target_id=target.target_id,
            target_hash=target.target_hash,
            barrier_ids=tuple(barrier.barrier_id for barrier in target.barriers),
            reason_codes=reasons,
        )
        for target in target_protocol.targets
    )


@dataclass(frozen=True, slots=True)
class FormalForecastComputationReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    request: FormalForecastComputationRequest
    formal_protocol_reference: ValidationArtifactReference
    formal_pit_evidence_reference: ValidationArtifactReference
    forecast_reference: ValidationArtifactReference
    model_reference: ValidationArtifactReference
    configuration_reference: ValidationArtifactReference
    selected_fact_references: tuple[ValidationArtifactReference, ...]
    executor_identity: str
    decision_time: datetime
    materialized_at: datetime
    production_authorized: bool = False
    schema_version: str = "formal-forecast-computation-receipt/v1"

    def __post_init__(self) -> None:
        require_sha256("Formal Forecast receipt hash", self.receipt_hash)
        require_text("Formal Forecast executor identity", self.executor_identity)
        expected_kinds = (
            (self.formal_protocol_reference, "FORMAL_RESEARCH_PROTOCOL"),
            (self.formal_pit_evidence_reference, "FORMAL_PIT_EVIDENCE"),
            (self.forecast_reference, "OUTCOME_TARGET_BOUND_FORECAST"),
            (self.model_reference, "MODEL_VERSION_LINEAGE"),
        )
        if any(item.artifact_kind != kind for item, kind in expected_kinds):
            raise ValueError("Formal Forecast receipt owner kind mismatch")
        if self.production_authorized:
            raise ValueError("Formal Forecast computation cannot grant Production")
        if self.selected_fact_references != tuple(
            sorted(set(self.selected_fact_references), key=_reference_key)
        ):
            raise ValueError("Formal Forecast receipt Facts must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.receipt_hash:
            raise ValueError("Formal Forecast computation receipt hash mismatch")
        if self.receipt_id != ArtifactId(
            f"formal-forecast-computation:{self.receipt_hash[7:]}"
        ):
            raise ValueError("Formal Forecast computation receipt identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> FormalForecastComputationReceipt:
        normalized = dict(values)
        normalized["selected_fact_references"] = tuple(
            sorted(set(values["selected_fact_references"]), key=_reference_key)
        )
        payload = _receipt_payload(**normalized)
        receipt_id, digest = content_identity("formal-forecast-computation", payload)
        return cls(receipt_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _receipt_payload(
            request=self.request,
            formal_protocol_reference=self.formal_protocol_reference,
            formal_pit_evidence_reference=self.formal_pit_evidence_reference,
            forecast_reference=self.forecast_reference,
            model_reference=self.model_reference,
            configuration_reference=self.configuration_reference,
            selected_fact_references=self.selected_fact_references,
            executor_identity=self.executor_identity,
            decision_time=self.decision_time,
            materialized_at=self.materialized_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalForecastComputationReceipt:
        facts = value["selected_fact_references"]
        if not isinstance(facts, list):
            raise ValueError("Formal Forecast receipt Facts must be an array")
        return cls(
            receipt_id=ArtifactId(str(value["receipt_id"])),
            receipt_hash=str(value["receipt_hash"]),
            request=FormalForecastComputationRequest.from_canonical_dict(
                _mapping(value["request"])
            ),
            formal_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_protocol_reference"])
            ),
            formal_pit_evidence_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_pit_evidence_reference"])
            ),
            forecast_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["forecast_reference"])
            ),
            model_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["model_reference"])
            ),
            configuration_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["configuration_reference"])
            ),
            selected_fact_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in facts
            ),
            executor_identity=str(value["executor_identity"]),
            decision_time=datetime.fromisoformat(str(value["decision_time"])),
            materialized_at=datetime.fromisoformat(str(value["materialized_at"])),
            production_authorized=bool(value["production_authorized"]),
            schema_version=str(value["schema_version"]),
        )


def _request_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-forecast-computation-request/v1",
        "formal_protocol_id": str(values["formal_protocol_id"]),
        "formal_pit_evidence_id": str(values["formal_pit_evidence_id"]),
        "symbol": values["symbol"],
        "idempotency_key": values["idempotency_key"],
    }


def _receipt_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-forecast-computation-receipt/v1",
        "request": values["request"].to_canonical_dict(),
        "formal_protocol_reference": values[
            "formal_protocol_reference"
        ].to_canonical_dict(),
        "formal_pit_evidence_reference": values[
            "formal_pit_evidence_reference"
        ].to_canonical_dict(),
        "forecast_reference": values["forecast_reference"].to_canonical_dict(),
        "model_reference": values["model_reference"].to_canonical_dict(),
        "configuration_reference": values[
            "configuration_reference"
        ].to_canonical_dict(),
        "selected_fact_references": [
            item.to_canonical_dict() for item in values["selected_fact_references"]
        ],
        "executor_identity": values["executor_identity"],
        "decision_time": timestamp(values["decision_time"]),
        "materialized_at": timestamp(values["materialized_at"]),
        "production_authorized": False,
    }


def _reference_key(item: ValidationArtifactReference) -> tuple[str, str, str]:
    return item.artifact_kind, str(item.artifact_id), item.content_hash


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Formal Forecast computation value must be an object")
    return value


__all__ = [
    "FormalForecastComputationReceipt",
    "FormalForecastComputationRequest",
    "FormalForecastExecutor",
    "FormalForecastExecutorSet",
    "ResolvedFormalForecastContext",
    "RegularizedFormalForecastExecutor",
    "installed_formal_forecast_executors",
    "not_estimable_estimates",
]
