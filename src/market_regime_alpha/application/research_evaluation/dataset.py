"""Immutable evaluation input assembled only from frozen owner Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    ProspectiveShadowOutcome,
    ShadowOutcomeObservation,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowDecision
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)


DATASET_SCHEMA = "frozen-research-evaluation-dataset/v1"
DECISION_SLICE_SCHEMA = "evaluation-decision-slice/v1"
SAMPLE_SCHEMA = "frozen-candidate-evaluation-sample/v1"


class EvaluationSampleDisposition(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    MISSING_OUTCOME = "MISSING_OUTCOME"


@dataclass(frozen=True, slots=True)
class FrozenCandidateEvaluationSample:
    sample_id: ArtifactId
    sample_hash: str
    shadow_decision: RuntimeArtifactReference
    symbol: str
    candidate_rank: int
    candidate_score: Decimal | None
    candidate_status: str
    market_state: str
    theme_state: str
    capital_state: str
    candidate_reason_codes: tuple[str, ...]
    outcome_observation: RuntimeArtifactReference | None
    open_return: Decimal | None
    return_1000: Decimal | None
    return_1030: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    disposition: EvaluationSampleDisposition
    reason_codes: tuple[str, ...]
    schema_version: str = SAMPLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SAMPLE_SCHEMA:
            raise ValueError("unsupported Evaluation sample schema")
        require_sha256("sample_hash", self.sample_hash)
        require_text("symbol", self.symbol)
        if self.candidate_rank <= 0 or isinstance(self.candidate_rank, bool):
            raise ValueError("Evaluation Candidate rank must be positive")
        if self.candidate_score is not None and not Decimal("0") <= self.candidate_score <= Decimal("1"):
            raise ValueError("Evaluation Candidate score must be within [0, 1]")
        if self.disposition is EvaluationSampleDisposition.INCLUDED:
            if self.outcome_observation is None or self.return_1030 is None:
                raise ValueError("included Evaluation sample requires settled Outcome")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Evaluation sample reasons must be unique and sorted")
        if self.candidate_reason_codes != tuple(sorted(set(self.candidate_reason_codes))):
            raise ValueError("Candidate reasons must be unique and sorted")
        if canonical_hash(self.semantic_payload()) != self.sample_hash:
            raise ValueError("Evaluation sample hash mismatch")
        if self.sample_id != _content_id("evaluation-sample", self.sample_hash):
            raise ValueError("Evaluation sample identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        decision: ShadowDecision,
        candidate: CandidateRecord,
        outcome: ShadowOutcomeObservation | None,
    ) -> FrozenCandidateEvaluationSample:
        if candidate.rank is None:
            raise ValueError("Evaluation sample requires a ranked Candidate")
        if candidate.selection_status is not CandidateSelectionStatus.SELECTED:
            raise ValueError("Evaluation sample requires a selected Candidate")
        if outcome is None:
            disposition = EvaluationSampleDisposition.MISSING_OUTCOME
            reasons = ("SETTLED_OUTCOME_MISSING",)
        elif outcome.availability_status is OutcomeAvailabilityStatus.COMPLETE:
            disposition = EvaluationSampleDisposition.INCLUDED
            reasons = ("FROZEN_DECISION_AND_SETTLED_OUTCOME",)
        else:
            disposition = EvaluationSampleDisposition.EXCLUDED
            reasons = tuple(sorted({*outcome.reason_codes, "OUTCOME_NOT_COMPLETE"}))
        values: dict[str, Any] = {
            "shadow_decision": RuntimeArtifactReference(
                "SHADOW_DECISION", decision.decision_id, decision.decision_hash
            ),
            "symbol": candidate.symbol,
            "candidate_rank": candidate.rank,
            "candidate_score": _optional_decimal_from_float(
                candidate.candidate_discovery_score
            ),
            "candidate_status": candidate.selection_status.value,
            "market_state": candidate.market_regime_status.value,
            "theme_state": candidate.theme_rotation_state.value,
            "capital_state": candidate.capital_evolution_state.value,
            "candidate_reason_codes": tuple(sorted(set(candidate.reason_codes))),
            "outcome_observation": (
                None
                if outcome is None
                else RuntimeArtifactReference(
                    "SHADOW_OUTCOME_OBSERVATION",
                    outcome.observation_id,
                    outcome.content_hash,
                )
            ),
            "open_return": None if outcome is None else outcome.open_return,
            "return_1000": None if outcome is None else outcome.return_1000,
            "return_1030": None if outcome is None else outcome.return_1030,
            "mfe": None if outcome is None else outcome.mfe,
            "mae": None if outcome is None else outcome.mae,
            "disposition": disposition,
            "reason_codes": reasons,
        }
        digest = canonical_hash(_sample_payload(**values))
        return cls(
            sample_id=_content_id("evaluation-sample", digest),
            sample_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _sample_payload(
            shadow_decision=self.shadow_decision,
            symbol=self.symbol,
            candidate_rank=self.candidate_rank,
            candidate_score=self.candidate_score,
            candidate_status=self.candidate_status,
            market_state=self.market_state,
            theme_state=self.theme_state,
            capital_state=self.capital_state,
            candidate_reason_codes=self.candidate_reason_codes,
            outcome_observation=self.outcome_observation,
            open_return=self.open_return,
            return_1000=self.return_1000,
            return_1030=self.return_1030,
            mfe=self.mfe,
            mae=self.mae,
            disposition=self.disposition,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "sample_id": str(self.sample_id),
            "sample_hash": self.sample_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FrozenCandidateEvaluationSample:
        return cls(
            sample_id=ArtifactId(_text(payload["sample_id"])),
            sample_hash=_text(payload["sample_hash"]),
            shadow_decision=_reference(payload["shadow_decision"]),
            symbol=_text(payload["symbol"]),
            candidate_rank=int(payload["candidate_rank"]),
            candidate_score=_optional_decimal(payload["candidate_score"]),
            candidate_status=_text(payload["candidate_status"]),
            market_state=_text(payload["market_state"]),
            theme_state=_text(payload["theme_state"]),
            capital_state=_text(payload["capital_state"]),
            candidate_reason_codes=_strings(payload["candidate_reason_codes"]),
            outcome_observation=_optional_reference(payload["outcome_observation"]),
            open_return=_optional_decimal(payload["open_return"]),
            return_1000=_optional_decimal(payload["return_1000"]),
            return_1030=_optional_decimal(payload["return_1030"]),
            mfe=_optional_decimal(payload["mfe"]),
            mae=_optional_decimal(payload["mae"]),
            disposition=EvaluationSampleDisposition(_text(payload["disposition"])),
            reason_codes=_strings(payload["reason_codes"]),
            schema_version=_text(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class EvaluationDecisionSlice:
    slice_id: ArtifactId
    slice_hash: str
    trading_date: date
    run_id: ArtifactId
    tick_id: ArtifactId
    shadow_decision: RuntimeArtifactReference
    summary: RuntimeArtifactReference
    source_manifest: RuntimeArtifactReference
    dataset: RuntimeArtifactReference
    feature_bundle: RuntimeArtifactReference
    market_state: RuntimeArtifactReference
    etf_state: RuntimeArtifactReference
    theme_state: RuntimeArtifactReference
    capital_state: RuntimeArtifactReference
    dynamic_pool: RuntimeArtifactReference | None
    candidate_set: RuntimeArtifactReference | None
    signal: RuntimeArtifactReference | None
    forecast: RuntimeArtifactReference | None
    model_selection_receipts: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]
    provider_source_references: tuple[RuntimeArtifactReference, ...]
    outcome: RuntimeArtifactReference
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    samples: tuple[FrozenCandidateEvaluationSample, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = DECISION_SLICE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_SLICE_SCHEMA:
            raise ValueError("unsupported Evaluation decision slice schema")
        require_sha256("slice_hash", self.slice_hash)
        if self.samples != tuple(sorted(self.samples, key=lambda item: item.symbol)):
            raise ValueError("Evaluation samples must be symbol-sorted")
        if len({item.symbol for item in self.samples}) != len(self.samples):
            raise ValueError("Evaluation samples must be symbol-unique")
        for references in (
            self.model_selection_receipts,
            self.configuration_references,
            self.provider_source_references,
        ):
            if references != _sorted_references(references):
                raise ValueError("Evaluation lineage must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Evaluation slice reasons must be unique and sorted")
        if canonical_hash(self.semantic_payload()) != self.slice_hash:
            raise ValueError("Evaluation slice hash mismatch")
        if self.slice_id != _content_id("evaluation-slice", self.slice_hash):
            raise ValueError("Evaluation slice identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return _slice_payload(self)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "slice_id": str(self.slice_id),
            "slice_hash": self.slice_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> EvaluationDecisionSlice:
        values: dict[str, Any] = {
            "trading_date": date.fromisoformat(_text(payload["trading_date"])),
            "run_id": ArtifactId(_text(payload["run_id"])),
            "tick_id": ArtifactId(_text(payload["tick_id"])),
            "shadow_decision": _reference(payload["shadow_decision"]),
            "summary": _reference(payload["summary"]),
            "source_manifest": _reference(payload["source_manifest"]),
            "dataset": _reference(payload["dataset"]),
            "feature_bundle": _reference(payload["feature_bundle"]),
            "market_state": _reference(payload["market_state"]),
            "etf_state": _reference(payload["etf_state"]),
            "theme_state": _reference(payload["theme_state"]),
            "capital_state": _reference(payload["capital_state"]),
            "dynamic_pool": _optional_reference(payload["dynamic_pool"]),
            "candidate_set": _optional_reference(payload["candidate_set"]),
            "signal": _optional_reference(payload["signal"]),
            "forecast": _optional_reference(payload["forecast"]),
            "model_selection_receipts": _references(payload["model_selection_receipts"]),
            "configuration_references": _references(payload["configuration_references"]),
            "provider_source_references": _references(payload["provider_source_references"]),
            "outcome": _reference(payload["outcome"]),
            "data_eligibility": DataEligibility(_text(payload["data_eligibility"])),
            "evidence_ceiling": PITSourceEvidenceLevel(_text(payload["evidence_ceiling"])),
            "samples": tuple(
                FrozenCandidateEvaluationSample.from_canonical_dict(_mapping(item))
                for item in _array(payload["samples"])
            ),
            "reason_codes": _strings(payload["reason_codes"]),
            "schema_version": _text(payload["schema_version"]),
        }
        return cls(
            slice_id=ArtifactId(_text(payload["slice_id"])),
            slice_hash=_text(payload["slice_hash"]),
            **values,
        )


def build_evaluation_decision_slice(
    *,
    decision: ShadowDecision,
    outcome: ProspectiveShadowOutcome,
    candidate_set: CandidateSet,
) -> EvaluationDecisionSlice:
    expected_candidate = RuntimeArtifactReference(
        "STATE_CONSTRAINED_CANDIDATE_SET",
        candidate_set.envelope.artifact_id,
        candidate_set.envelope.content_hash,
    )
    if decision.candidate_set != expected_candidate:
        raise ValueError("Evaluation CandidateSet does not match frozen Decision")
    if (
        outcome.shadow_decision.artifact_id != decision.decision_id
        or outcome.shadow_decision.content_hash != decision.decision_hash
    ):
        raise ValueError("Evaluation Outcome does not match frozen Decision")
    by_symbol = {item.symbol: item for item in outcome.observations}
    selected = candidate_set.selected
    samples = tuple(
        sorted(
            (
                FrozenCandidateEvaluationSample.create(
                    decision=decision,
                    candidate=item,
                    outcome=by_symbol.get(item.symbol),
                )
                for item in selected
            ),
            key=lambda item: item.symbol,
        )
    )
    reasons = {
        "CONTENT_ADDRESSED_EVALUATION_INPUT",
        "DECISION_FROZEN_BEFORE_OUTCOME",
        "EXPLORATORY_EVALUATION_ONLY",
    }
    if not samples:
        reasons.add("NO_SELECTED_CANDIDATES")
    if any(item.disposition is not EvaluationSampleDisposition.INCLUDED for item in samples):
        reasons.add("INCOMPLETE_SAMPLE_COVERAGE")
    values: dict[str, Any] = {
        "trading_date": decision.trading_date,
        "run_id": decision.run_id,
        "tick_id": decision.tick_id,
        "shadow_decision": RuntimeArtifactReference(
            "SHADOW_DECISION", decision.decision_id, decision.decision_hash
        ),
        "summary": decision.summary,
        "source_manifest": decision.source_manifest,
        "dataset": decision.dataset,
        "feature_bundle": decision.feature_bundle,
        "market_state": decision.market_state,
        "etf_state": decision.etf_state,
        "theme_state": decision.theme_state,
        "capital_state": decision.capital_state,
        "dynamic_pool": decision.dynamic_pool,
        "candidate_set": decision.candidate_set,
        "signal": decision.signal,
        "forecast": decision.forecast,
        "model_selection_receipts": decision.model_selection_receipts,
        "configuration_references": decision.configuration_references,
        "provider_source_references": decision.provider_source_references,
        "outcome": RuntimeArtifactReference(
            "PROSPECTIVE_SHADOW_OUTCOME",
            outcome.settlement_id,
            outcome.settlement_hash,
        ),
        "data_eligibility": decision.data_eligibility,
        "evidence_ceiling": decision.evidence_ceiling,
        "samples": samples,
        "reason_codes": tuple(sorted(reasons)),
    }
    digest = canonical_hash(_slice_values_payload(**values))
    return EvaluationDecisionSlice(
        slice_id=_content_id("evaluation-slice", digest),
        slice_hash=digest,
        **values,
    )


@dataclass(frozen=True, slots=True)
class FrozenResearchEvaluationDataset:
    dataset_id: ArtifactId
    dataset_hash: str
    protocol_id: str
    protocol_hash: str
    slices: tuple[EvaluationDecisionSlice, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = DATASET_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DATASET_SCHEMA:
            raise ValueError("unsupported Evaluation Dataset schema")
        require_sha256("dataset_hash", self.dataset_hash)
        require_sha256("protocol_hash", self.protocol_hash)
        require_text("protocol_id", self.protocol_id)
        _aware("created_at", self.created_at)
        keys = tuple((item.trading_date, str(item.run_id)) for item in self.slices)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("Evaluation slices must be unique and sorted")
        required = {
            "EXPLORATORY_ONLY",
            "NOT_FORMAL_OOS",
            "NOT_MODEL_QUALIFICATION",
            "OUTCOME_CANNOT_REWRITE_DECISION",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Evaluation Dataset authority ceiling is incomplete")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Evaluation limitations must be unique and sorted")
        if canonical_hash(self.semantic_payload()) != self.dataset_hash:
            raise ValueError("Evaluation Dataset hash mismatch")
        if self.dataset_id != _content_id("research-evaluation-dataset", self.dataset_hash):
            raise ValueError("Evaluation Dataset identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol_id: str,
        protocol_hash: str,
        slices: tuple[EvaluationDecisionSlice, ...],
        created_at: datetime,
    ) -> FrozenResearchEvaluationDataset:
        ordered = tuple(sorted(slices, key=lambda item: (item.trading_date, str(item.run_id))))
        limitations = (
            "EXPLORATORY_ONLY",
            "NOT_FORMAL_OOS",
            "NOT_MODEL_QUALIFICATION",
            "OUTCOME_CANNOT_REWRITE_DECISION",
        )
        values = {
            "protocol_id": protocol_id,
            "protocol_hash": protocol_hash,
            "slices": ordered,
            "created_at": created_at,
            "limitations": tuple(sorted(limitations)),
        }
        digest = canonical_hash(_dataset_payload(**values))
        return cls(
            dataset_id=_content_id("research-evaluation-dataset", digest),
            dataset_hash=digest,
            **values,
        )

    @property
    def observation_count(self) -> int:
        return sum(len(item.samples) for item in self.slices)

    @property
    def included_count(self) -> int:
        return sum(
            item.disposition is EvaluationSampleDisposition.INCLUDED
            for value in self.slices
            for item in value.samples
        )

    @property
    def excluded_count(self) -> int:
        return sum(
            item.disposition is EvaluationSampleDisposition.EXCLUDED
            for value in self.slices
            for item in value.samples
        )

    @property
    def missing_count(self) -> int:
        return sum(
            item.disposition is EvaluationSampleDisposition.MISSING_OUTCOME
            for value in self.slices
            for item in value.samples
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _dataset_payload(
            protocol_id=self.protocol_id,
            protocol_hash=self.protocol_hash,
            slices=self.slices,
            created_at=self.created_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": str(self.dataset_id),
            "dataset_hash": self.dataset_hash,
            **self.semantic_payload(),
            "counts": {
                "observations": self.observation_count,
                "included": self.included_count,
                "excluded": self.excluded_count,
                "missing": self.missing_count,
            },
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FrozenResearchEvaluationDataset:
        value = cls(
            dataset_id=ArtifactId(_text(payload["dataset_id"])),
            dataset_hash=_text(payload["dataset_hash"]),
            protocol_id=_text(payload["protocol_id"]),
            protocol_hash=_text(payload["protocol_hash"]),
            slices=tuple(
                EvaluationDecisionSlice.from_canonical_dict(_mapping(item))
                for item in _array(payload["slices"])
            ),
            created_at=_instant(payload["created_at"]),
            limitations=_strings(payload["limitations"]),
            schema_version=_text(payload["schema_version"]),
        )
        counts = _mapping(payload["counts"])
        if counts != {
            "observations": value.observation_count,
            "included": value.included_count,
            "excluded": value.excluded_count,
            "missing": value.missing_count,
        }:
            raise ValueError("Evaluation Dataset counts mismatch")
        return value


def publish_research_evaluation_dataset(
    *, root: Path, dataset: FrozenResearchEvaluationDataset
) -> Path:
    path = root / f"{dataset.dataset_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(dataset.to_canonical_dict()) + "\n",
        collision_message="Evaluation Dataset identity conflict",
    )
    if load_research_evaluation_dataset(path) != dataset:
        raise ValueError("published Evaluation Dataset semantic mismatch")
    return path


def load_research_evaluation_dataset(path: Path) -> FrozenResearchEvaluationDataset:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evaluation Dataset payload must be an object")
    return FrozenResearchEvaluationDataset.from_canonical_dict(payload)


def _sample_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": SAMPLE_SCHEMA,
        "shadow_decision": values["shadow_decision"].to_canonical_dict(),
        "symbol": values["symbol"],
        "candidate_rank": values["candidate_rank"],
        "candidate_score": _decimal_text(values["candidate_score"]),
        "candidate_status": values["candidate_status"],
        "market_state": values["market_state"],
        "theme_state": values["theme_state"],
        "capital_state": values["capital_state"],
        "candidate_reason_codes": list(values["candidate_reason_codes"]),
        "outcome_observation": _reference_dict(values["outcome_observation"]),
        "open_return": _decimal_text(values["open_return"]),
        "return_1000": _decimal_text(values["return_1000"]),
        "return_1030": _decimal_text(values["return_1030"]),
        "mfe": _decimal_text(values["mfe"]),
        "mae": _decimal_text(values["mae"]),
        "disposition": values["disposition"].value,
        "reason_codes": list(values["reason_codes"]),
    }


def _slice_values_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": DECISION_SLICE_SCHEMA,
        "trading_date": values["trading_date"].isoformat(),
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "shadow_decision": values["shadow_decision"].to_canonical_dict(),
        "summary": values["summary"].to_canonical_dict(),
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "dataset": values["dataset"].to_canonical_dict(),
        "feature_bundle": values["feature_bundle"].to_canonical_dict(),
        "market_state": values["market_state"].to_canonical_dict(),
        "etf_state": values["etf_state"].to_canonical_dict(),
        "theme_state": values["theme_state"].to_canonical_dict(),
        "capital_state": values["capital_state"].to_canonical_dict(),
        "dynamic_pool": _reference_dict(values["dynamic_pool"]),
        "candidate_set": _reference_dict(values["candidate_set"]),
        "signal": _reference_dict(values["signal"]),
        "forecast": _reference_dict(values["forecast"]),
        "model_selection_receipts": [
            item.to_canonical_dict() for item in values["model_selection_receipts"]
        ],
        "configuration_references": [
            item.to_canonical_dict() for item in values["configuration_references"]
        ],
        "provider_source_references": [
            item.to_canonical_dict() for item in values["provider_source_references"]
        ],
        "outcome": values["outcome"].to_canonical_dict(),
        "data_eligibility": values["data_eligibility"].value,
        "evidence_ceiling": values["evidence_ceiling"].value,
        "samples": [item.to_canonical_dict() for item in values["samples"]],
        "reason_codes": list(values["reason_codes"]),
    }


def _slice_payload(value: EvaluationDecisionSlice) -> dict[str, Any]:
    return _slice_values_payload(
        trading_date=value.trading_date,
        run_id=value.run_id,
        tick_id=value.tick_id,
        shadow_decision=value.shadow_decision,
        summary=value.summary,
        source_manifest=value.source_manifest,
        dataset=value.dataset,
        feature_bundle=value.feature_bundle,
        market_state=value.market_state,
        etf_state=value.etf_state,
        theme_state=value.theme_state,
        capital_state=value.capital_state,
        dynamic_pool=value.dynamic_pool,
        candidate_set=value.candidate_set,
        signal=value.signal,
        forecast=value.forecast,
        model_selection_receipts=value.model_selection_receipts,
        configuration_references=value.configuration_references,
        provider_source_references=value.provider_source_references,
        outcome=value.outcome,
        data_eligibility=value.data_eligibility,
        evidence_ceiling=value.evidence_ceiling,
        samples=value.samples,
        reason_codes=value.reason_codes,
    )


def _dataset_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": DATASET_SCHEMA,
        "protocol_id": values["protocol_id"],
        "protocol_hash": values["protocol_hash"],
        "slices": [item.to_canonical_dict() for item in values["slices"]],
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _sorted_references(
    values: tuple[RuntimeArtifactReference, ...]
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _reference_dict(value: RuntimeArtifactReference | None) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _reference(value: object) -> RuntimeArtifactReference:
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _optional_reference(value: object) -> RuntimeArtifactReference | None:
    return None if value is None else _reference(value)


def _references(value: object) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(_reference(item) for item in _array(value))


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Evaluation decimal must be encoded as text")
    return Decimal(value)


def _optional_decimal_from_float(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    _aware("instant", parsed)
    return parsed


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Evaluation value must be non-empty text")
    return value


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Evaluation value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Evaluation value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    items = _array(value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError("Evaluation value must be a string array")
    return tuple(str(item) for item in items)


__all__ = [
    "EvaluationDecisionSlice",
    "EvaluationSampleDisposition",
    "FrozenCandidateEvaluationSample",
    "FrozenResearchEvaluationDataset",
    "build_evaluation_decision_slice",
    "load_research_evaluation_dataset",
    "publish_research_evaluation_dataset",
]
