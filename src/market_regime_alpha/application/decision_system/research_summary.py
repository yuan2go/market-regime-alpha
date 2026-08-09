"""Account-neutral immutable endpoint for Research and Shadow runtime ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.state_system.runtime import (
    STATE_RESEARCH_STAGE_ORDER,
    StateResearchStage,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


RESEARCH_STAGE_EVIDENCE_SCHEMA = "research-stage-evidence/v1"
RESEARCH_DAILY_SUMMARY_SCHEMA = "research-daily-summary/v1"


class ResearchStageStatus(str, Enum):
    COMPLETED = "COMPLETED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MODEL_NOT_QUALIFIED_FOR_MODE = "MODEL_NOT_QUALIFIED_FOR_MODE"


class ResearchDailySummaryOutcome(str, Enum):
    NO_ACTION = "NO_ACTION"
    WATCH = "WATCH"
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MODEL_NOT_QUALIFIED_FOR_MODE = "MODEL_NOT_QUALIFIED_FOR_MODE"


@dataclass(frozen=True, slots=True)
class ProviderContractLineage:
    provider_id: str
    product: str
    contract_version: str

    def __post_init__(self) -> None:
        require_text("provider_id", self.provider_id)
        require_text("product", self.product)
        require_text("contract_version", self.contract_version)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "product": self.product,
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ProviderContractLineage:
        _fields(
            payload,
            {"provider_id", "product", "contract_version"},
            "ProviderContractLineage",
        )
        return cls(
            provider_id=_text(payload["provider_id"]),
            product=_text(payload["product"]),
            contract_version=_text(payload["contract_version"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchStageEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    stage: StateResearchStage
    status: ResearchStageStatus
    output_reference: RuntimeArtifactReference | None
    selection_receipt: RuntimeArtifactReference | None
    available_at: datetime
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    missing_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = field(
        default=RESEARCH_STAGE_EVIDENCE_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        _aware("available_at", self.available_at)
        _ordered_text("missing_evidence", self.missing_evidence)
        _ordered_text("reason_codes", self.reason_codes, required=True)
        if (
            self.status is ResearchStageStatus.COMPLETED
            and self.output_reference is None
        ):
            raise ValueError("completed Research Stage requires an output")
        # A DATA_INSUFFICIENT Artifact is still a real, immutable Stage output.
        # Its status and missing-evidence fields prevent it from claiming a
        # successful computation; retaining the reference is essential for
        # replay and prospective Shadow outcome joins.
        if (
            self.status is ResearchStageStatus.DATA_INSUFFICIENT
            and not self.missing_evidence
        ):
            raise ValueError("DATA_INSUFFICIENT requires missing evidence")
        if (
            self.status is ResearchStageStatus.MODEL_NOT_QUALIFIED_FOR_MODE
            and self.selection_receipt is None
        ):
            raise ValueError("model rejection requires a Selection Receipt")
        if canonical_hash(self.semantic_payload()) != self.evidence_hash:
            raise ValueError("Research Stage evidence hash mismatch")
        if self.evidence_id != _content_id("research-stage-evidence", self.evidence_hash):
            raise ValueError("Research Stage evidence identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchStageEvidence:
        normalized = dict(values)
        normalized["missing_evidence"] = tuple(
            sorted(set(values["missing_evidence"]))
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_stage_payload(**normalized))
        return cls(
            evidence_id=_content_id("research-stage-evidence", digest),
            evidence_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _stage_payload(
            stage=self.stage,
            status=self.status,
            output_reference=self.output_reference,
            selection_receipt=self.selection_receipt,
            available_at=self.available_at,
            data_eligibility=self.data_eligibility,
            evidence_ceiling=self.evidence_ceiling,
            missing_evidence=self.missing_evidence,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "evidence_hash": self.evidence_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchStageEvidence:
        _fields(
            payload,
            {
                "schema_version",
                "evidence_id",
                "evidence_hash",
                "stage",
                "status",
                "output_reference",
                "selection_receipt",
                "available_at",
                "data_eligibility",
                "evidence_ceiling",
                "missing_evidence",
                "reason_codes",
            },
            "ResearchStageEvidence",
        )
        if payload["schema_version"] != RESEARCH_STAGE_EVIDENCE_SCHEMA:
            raise ValueError("unsupported Research Stage evidence schema")
        return cls(
            evidence_id=ArtifactId(_text(payload["evidence_id"])),
            evidence_hash=_text(payload["evidence_hash"]),
            stage=StateResearchStage(_text(payload["stage"])),
            status=ResearchStageStatus(_text(payload["status"])),
            output_reference=_optional_reference(payload["output_reference"]),
            selection_receipt=_optional_reference(payload["selection_receipt"]),
            available_at=_instant(payload["available_at"]),
            data_eligibility=DataEligibility(_text(payload["data_eligibility"])),
            evidence_ceiling=PITSourceEvidenceLevel(
                _text(payload["evidence_ceiling"])
            ),
            missing_evidence=_strings(payload["missing_evidence"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchDailySummary:
    summary_id: ArtifactId
    content_hash: str
    runtime_mode: RuntimeAuthorityMode
    run_id: ArtifactId
    tick_id: ArtifactId
    trading_date: date
    decision_time: datetime
    provider_profile_id: str
    provider_contracts: tuple[ProviderContractLineage, ...]
    source_manifest: RuntimeArtifactReference
    dataset: RuntimeArtifactReference
    feature_bundle: RuntimeArtifactReference
    stages: tuple[ResearchStageEvidence, ...]
    model_selection_receipts: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    outcome: ResearchDailySummaryOutcome
    missing_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    revision: int
    previous_summary_id: ArtifactId | None
    correction_of_summary_id: ArtifactId | None
    idempotency_key: str
    created_at: datetime
    schema_version: str = field(
        default=RESEARCH_DAILY_SUMMARY_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        require_sha256("content_hash", self.content_hash)
        if self.runtime_mode is RuntimeAuthorityMode.PRODUCTION:
            raise ValueError("Research Summary supports Research/Shadow modes only")
        _aware("decision_time", self.decision_time)
        _aware("created_at", self.created_at)
        if self.created_at < self.decision_time:
            raise ValueError("Research Summary cannot predate DecisionTime")
        require_text("provider_profile_id", self.provider_profile_id)
        require_text("idempotency_key", self.idempotency_key)
        _ordered_provider_contracts(self.provider_contracts)
        if tuple(item.stage for item in self.stages) != STATE_RESEARCH_STAGE_ORDER:
            raise ValueError("Research Summary requires every ordered State stage")
        if any(item.available_at > self.decision_time for item in self.stages):
            raise ValueError("Research Summary cannot consume future stage evidence")
        _ordered_references(
            "model_selection_receipts", self.model_selection_receipts
        )
        _ordered_references(
            "configuration_references", self.configuration_references
        )
        stage_receipts = tuple(
            item.selection_receipt
            for item in self.stages
            if item.selection_receipt is not None
        )
        if self.model_selection_receipts != _sort_references(stage_receipts):
            raise ValueError("Summary Selection Receipts do not match stage evidence")
        if self.evidence_ceiling != _minimum_ceiling(self.stages):
            raise ValueError("Evidence ceiling cannot increase downstream")
        if self.data_eligibility != _minimum_eligibility(self.stages):
            raise ValueError("DataEligibility cannot increase downstream")
        _ordered_text("missing_evidence", self.missing_evidence)
        _ordered_text("reason_codes", self.reason_codes, required=True)
        if self.outcome is not _derive_outcome(self.stages):
            raise ValueError("Research Summary outcome does not match stage evidence")
        if self.revision < 1 or isinstance(self.revision, bool):
            raise ValueError("Research Summary revision must be positive")
        if self.revision == 1:
            if self.previous_summary_id is not None or self.correction_of_summary_id is not None:
                raise ValueError("original Research Summary cannot be a correction")
        elif self.previous_summary_id is None or self.correction_of_summary_id is None:
            raise ValueError("Research Summary correction requires previous and original IDs")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Research Summary hash mismatch")
        if self.summary_id != _content_id("research-daily-summary", self.content_hash):
            raise ValueError("Research Summary identity mismatch")

    @property
    def no_order(self) -> bool:
        return True

    @property
    def no_fill(self) -> bool:
        return True

    @property
    def no_broker(self) -> bool:
        return True

    @property
    def no_position_mutation_from_shadow(self) -> bool:
        return True

    @classmethod
    def create(cls, **values: Any) -> ResearchDailySummary:
        normalized = dict(values)
        normalized["provider_contracts"] = tuple(
            sorted(
                set(values["provider_contracts"]),
                key=_provider_contract_key,
            )
        )
        normalized["model_selection_receipts"] = _sort_references(
            values["model_selection_receipts"]
        )
        normalized["configuration_references"] = _sort_references(
            values["configuration_references"]
        )
        normalized["outcome"] = _derive_outcome(values["stages"])
        normalized["missing_evidence"] = tuple(
            sorted(
                {
                    reason
                    for stage in values["stages"]
                    for reason in stage.missing_evidence
                }
            )
        )
        normalized["reason_codes"] = tuple(
            sorted(
                {
                    "ENTRY_BLOCKED",
                    "NO_BROKER",
                    "NO_FILL",
                    "NO_ORDER",
                    "NO_POSITION_MUTATION_FROM_SHADOW",
                    f"RUNTIME_MODE_{values['runtime_mode'].value}",
                    *(
                        reason
                        for stage in values["stages"]
                        for reason in stage.reason_codes
                    ),
                }
            )
        )
        digest = canonical_hash(_summary_payload(**normalized))
        return cls(
            summary_id=_content_id("research-daily-summary", digest),
            content_hash=digest,
            **normalized,
        )

    def creation_values(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.runtime_mode,
            "run_id": self.run_id,
            "tick_id": self.tick_id,
            "trading_date": self.trading_date,
            "decision_time": self.decision_time,
            "provider_profile_id": self.provider_profile_id,
            "provider_contracts": self.provider_contracts,
            "source_manifest": self.source_manifest,
            "dataset": self.dataset,
            "feature_bundle": self.feature_bundle,
            "stages": self.stages,
            "model_selection_receipts": self.model_selection_receipts,
            "configuration_references": self.configuration_references,
            "data_eligibility": self.data_eligibility,
            "evidence_ceiling": self.evidence_ceiling,
            "revision": self.revision,
            "previous_summary_id": self.previous_summary_id,
            "correction_of_summary_id": self.correction_of_summary_id,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    def semantic_payload(self) -> dict[str, Any]:
        return _summary_payload(
            **self.creation_values(),
            outcome=self.outcome,
            missing_evidence=self.missing_evidence,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "summary_id": str(self.summary_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
            "safety": {
                "no_order": True,
                "no_fill": True,
                "no_broker": True,
                "no_position_mutation_from_shadow": True,
            },
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchDailySummary:
        expected = {
            "schema_version",
            "summary_id",
            "content_hash",
            "runtime_mode",
            "run_id",
            "tick_id",
            "trading_date",
            "decision_time",
            "provider_profile_id",
            "provider_contracts",
            "source_manifest",
            "dataset",
            "feature_bundle",
            "stages",
            "model_selection_receipts",
            "configuration_references",
            "data_eligibility",
            "evidence_ceiling",
            "outcome",
            "missing_evidence",
            "reason_codes",
            "revision",
            "previous_summary_id",
            "correction_of_summary_id",
            "idempotency_key",
            "created_at",
            "safety",
        }
        _fields(payload, expected, "ResearchDailySummary")
        if payload["schema_version"] != RESEARCH_DAILY_SUMMARY_SCHEMA:
            raise ValueError("unsupported Research Summary schema")
        safety = _mapping(payload["safety"])
        if safety != {
            "no_order": True,
            "no_fill": True,
            "no_broker": True,
            "no_position_mutation_from_shadow": True,
        }:
            raise ValueError("Research Summary safety declarations mismatch")
        return cls(
            summary_id=ArtifactId(_text(payload["summary_id"])),
            content_hash=_text(payload["content_hash"]),
            runtime_mode=RuntimeAuthorityMode(_text(payload["runtime_mode"])),
            run_id=ArtifactId(_text(payload["run_id"])),
            tick_id=ArtifactId(_text(payload["tick_id"])),
            trading_date=date.fromisoformat(_text(payload["trading_date"])),
            decision_time=_instant(payload["decision_time"]),
            provider_profile_id=_text(payload["provider_profile_id"]),
            provider_contracts=tuple(
                ProviderContractLineage.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["provider_contracts"])
            ),
            source_manifest=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["source_manifest"])
            ),
            dataset=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["dataset"])
            ),
            feature_bundle=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["feature_bundle"])
            ),
            stages=tuple(
                ResearchStageEvidence.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["stages"])
            ),
            model_selection_receipts=tuple(
                RuntimeArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["model_selection_receipts"])
            ),
            configuration_references=tuple(
                RuntimeArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["configuration_references"])
            ),
            data_eligibility=DataEligibility(_text(payload["data_eligibility"])),
            evidence_ceiling=PITSourceEvidenceLevel(
                _text(payload["evidence_ceiling"])
            ),
            outcome=ResearchDailySummaryOutcome(_text(payload["outcome"])),
            missing_evidence=_strings(payload["missing_evidence"]),
            reason_codes=_strings(payload["reason_codes"]),
            revision=_integer(payload["revision"]),
            previous_summary_id=_optional_id(payload["previous_summary_id"]),
            correction_of_summary_id=_optional_id(
                payload["correction_of_summary_id"]
            ),
            idempotency_key=_text(payload["idempotency_key"]),
            created_at=_instant(payload["created_at"]),
        )


def _stage_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_STAGE_EVIDENCE_SCHEMA,
        "stage": values["stage"].value,
        "status": values["status"].value,
        "output_reference": (
            None
            if values["output_reference"] is None
            else values["output_reference"].to_canonical_dict()
        ),
        "selection_receipt": (
            None
            if values["selection_receipt"] is None
            else values["selection_receipt"].to_canonical_dict()
        ),
        "available_at": canonical_datetime(values["available_at"]),
        "data_eligibility": values["data_eligibility"].value,
        "evidence_ceiling": values["evidence_ceiling"].value,
        "missing_evidence": list(values["missing_evidence"]),
        "reason_codes": list(values["reason_codes"]),
    }


def _summary_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_DAILY_SUMMARY_SCHEMA,
        "runtime_mode": values["runtime_mode"].value,
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "trading_date": values["trading_date"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "provider_profile_id": values["provider_profile_id"],
        "provider_contracts": [
            item.to_canonical_dict() for item in values["provider_contracts"]
        ],
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "dataset": values["dataset"].to_canonical_dict(),
        "feature_bundle": values["feature_bundle"].to_canonical_dict(),
        "stages": [item.to_canonical_dict() for item in values["stages"]],
        "model_selection_receipts": [
            item.to_canonical_dict()
            for item in values["model_selection_receipts"]
        ],
        "configuration_references": [
            item.to_canonical_dict()
            for item in values["configuration_references"]
        ],
        "data_eligibility": values["data_eligibility"].value,
        "evidence_ceiling": values["evidence_ceiling"].value,
        "outcome": values["outcome"].value,
        "missing_evidence": list(values["missing_evidence"]),
        "reason_codes": list(values["reason_codes"]),
        "revision": values["revision"],
        "previous_summary_id": (
            None
            if values["previous_summary_id"] is None
            else str(values["previous_summary_id"])
        ),
        "correction_of_summary_id": (
            None
            if values["correction_of_summary_id"] is None
            else str(values["correction_of_summary_id"])
        ),
        "idempotency_key": values["idempotency_key"],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _derive_outcome(
    stages: tuple[ResearchStageEvidence, ...],
) -> ResearchDailySummaryOutcome:
    if any(
        item.status is ResearchStageStatus.MODEL_NOT_QUALIFIED_FOR_MODE
        for item in stages
    ):
        return ResearchDailySummaryOutcome.MODEL_NOT_QUALIFIED_FOR_MODE
    if any(item.status is ResearchStageStatus.DATA_INSUFFICIENT for item in stages):
        return ResearchDailySummaryOutcome.DATA_INSUFFICIENT
    reasons = {reason for item in stages for reason in item.reason_codes}
    if "RESEARCH_CANDIDATE" in reasons:
        return ResearchDailySummaryOutcome.RESEARCH_CANDIDATE
    if "WATCH" in reasons:
        return ResearchDailySummaryOutcome.WATCH
    return ResearchDailySummaryOutcome.NO_ACTION


_CEILING_RANK = {
    PITSourceEvidenceLevel.FIXTURE: 0,
    PITSourceEvidenceLevel.REPLAY: 1,
    PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY: 2,
    PITSourceEvidenceLevel.PIT_INCOMPLETE: 3,
    PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE: 4,
    PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER: 5,
}

_ELIGIBILITY_RANK = {
    DataEligibility.UNQUALIFIED: 0,
    DataEligibility.EXPLORATORY: 1,
    DataEligibility.REHEARSAL: 2,
    DataEligibility.FORMAL_RESEARCH: 3,
}


def _minimum_ceiling(
    stages: tuple[ResearchStageEvidence, ...],
) -> PITSourceEvidenceLevel:
    return min((item.evidence_ceiling for item in stages), key=_CEILING_RANK.__getitem__)


def _minimum_eligibility(
    stages: tuple[ResearchStageEvidence, ...],
) -> DataEligibility:
    return min((item.data_eligibility for item in stages), key=_ELIGIBILITY_RANK.__getitem__)


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}:{digest.removeprefix('sha256:')}")


def _reference_key(item: RuntimeArtifactReference) -> tuple[str, str, str]:
    return item.reference_kind, str(item.artifact_id), item.content_hash


def _sort_references(
    values: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(sorted(set(values), key=_reference_key))


def _ordered_references(
    label: str, values: tuple[RuntimeArtifactReference, ...]
) -> None:
    if values != _sort_references(values):
        raise ValueError(f"{label} must be unique and sorted")


def _provider_contract_key(item: ProviderContractLineage) -> tuple[str, str, str]:
    return item.provider_id, item.product, item.contract_version


def _ordered_provider_contracts(
    values: tuple[ProviderContractLineage, ...],
) -> None:
    if not values or values != tuple(sorted(set(values), key=_provider_contract_key)):
        raise ValueError("provider_contracts must be non-empty, unique and sorted")


def _ordered_text(label: str, values: tuple[str, ...], *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    if values != tuple(sorted(set(values))) or any(
        not value or value != value.strip() for value in values
    ):
        raise ValueError(f"{label} must be unique, sorted, and trimmed")


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("value must be text")
    return value


def _instant(value: object) -> datetime:
    result = datetime.fromisoformat(_text(value))
    _aware("timestamp", result)
    return result


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("value must be an array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    return tuple(_text(item) for item in _sequence(value))


def _optional_reference(value: object) -> RuntimeArtifactReference | None:
    if value is None:
        return None
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(_text(value))


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("value must be an integer")
    return value


__all__ = [
    "ProviderContractLineage",
    "RESEARCH_DAILY_SUMMARY_SCHEMA",
    "RESEARCH_STAGE_EVIDENCE_SCHEMA",
    "ResearchDailySummary",
    "ResearchDailySummaryOutcome",
    "ResearchStageEvidence",
    "ResearchStageStatus",
]
