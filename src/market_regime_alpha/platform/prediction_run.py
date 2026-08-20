"""Immutable, protocol-bound Candidate PredictionRun evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping

from market_regime_alpha.candidates.baselines import CandidateRankingRejection
from market_regime_alpha.candidates.contracts import (
    CandidateExpiryTime,
    CandidatePrediction,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
)
from market_regime_alpha.research.cross_sectional_ranking import competition_ranks


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_sha256(label: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PredictionRun:
    """One complete immutable Candidate ranking publication.

    Predictions and rejections are the existing Candidate domain objects. This contract
    adds protocol and materialization lineage without changing their score or rank.
    """

    SCHEMA_VERSION = "candidate-prediction-run/v2"

    model_id: ModelId
    model_definition_hash: str
    target_id: TargetId
    evaluation_protocol_id: EvaluationProtocolId
    experiment_protocol_id: ExperimentId
    dataset_id: DatasetId
    universe_id: UniverseId
    decision_time: DecisionTime
    feature_definition_ids: tuple[FeatureDefinitionId, ...]
    feature_materialization_ids: tuple[FeatureMaterializationId, ...]
    code_revision: str
    configuration_hash: str
    predictions: tuple[CandidatePrediction, ...]
    rejections: tuple[CandidateRankingRejection, ...]
    population_size: int
    ranking_coverage: float
    data_eligibility: DataEligibility
    evidence_level: EvidenceLevel
    ranking_contract: str = "TIE_AWARE_COMPETITION_RANK_V2"
    content_hash: str = field(init=False)
    prediction_run_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256("model_definition_hash", self.model_definition_hash)
        _require_text("code_revision", self.code_revision)
        _require_sha256("configuration_hash", self.configuration_hash)
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("data_eligibility must be a DataEligibility")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise TypeError("evidence_level must be an EvidenceLevel")
        if self.ranking_contract != "TIE_AWARE_COMPETITION_RANK_V2":
            raise ValueError("PredictionRun requires the V2 tie-aware ranking contract")
        if not self.feature_definition_ids:
            raise ValueError("feature_definition_ids must not be empty")
        if len(self.feature_definition_ids) != len(set(self.feature_definition_ids)):
            raise ValueError("feature_definition_ids must be unique")
        if len(self.feature_materialization_ids) != len(
            set(self.feature_materialization_ids)
        ):
            raise ValueError("feature_materialization_ids must be unique")
        if len(self.feature_definition_ids) != len(self.feature_materialization_ids):
            raise ValueError(
                "feature definitions and materializations must have equal cardinality"
            )
        if isinstance(self.population_size, bool) or self.population_size < 0:
            raise ValueError("population_size must be a non-negative integer")
        if (
            isinstance(self.ranking_coverage, bool)
            or not isinstance(self.ranking_coverage, (int, float))
            or not math.isfinite(float(self.ranking_coverage))
            or not 0.0 <= float(self.ranking_coverage) <= 1.0
        ):
            raise ValueError("ranking_coverage must be finite and in [0, 1]")
        if len(self.predictions) + len(self.rejections) != self.population_size:
            raise ValueError(
                "predictions plus rejections must cover the Candidate Population"
            )
        expected_coverage = (
            len(self.predictions) / self.population_size
            if self.population_size
            else 0.0
        )
        if float(self.ranking_coverage) != expected_coverage:
            raise ValueError("ranking_coverage does not match full population accounting")
        if any(
            item.model_score is None or item.rank is None
            for item in self.predictions
        ):
            raise ValueError("ranked PredictionRun entries require score and rank")
        scores = {
            item.symbol: item.model_score
            for item in self.predictions
            if item.model_score is not None
        }
        if tuple(scores.values()) != tuple(sorted(scores.values(), reverse=True)):
            raise ValueError("PredictionRun scores must be descending")
        expected_ranks = competition_ranks(scores, higher_is_better=True)
        actual_ranks = {item.symbol: item.rank for item in self.predictions}
        if actual_ranks != expected_ranks:
            raise ValueError("PredictionRun ranks must preserve equal-score ties")
        prediction_symbols: list[str] = []
        for prediction in self.predictions:
            if (
                prediction.model_id != self.model_id
                or prediction.target_id != self.target_id
                or prediction.universe_id != self.universe_id
                or prediction.decision_time != self.decision_time
            ):
                raise ValueError("prediction scope does not match PredictionRun")
            if prediction.population_size != self.population_size:
                raise ValueError("prediction population_size does not match PredictionRun")
            prediction_symbols.append(prediction.symbol)
        if tuple(item.symbol for item in self.rejections) != tuple(
            sorted(item.symbol for item in self.rejections)
        ):
            raise ValueError("rejections must be ordered by symbol")
        if any(
            item.feature_id not in self.feature_definition_ids
            for item in self.rejections
        ):
            raise ValueError("rejection Feature is outside PredictionRun lineage")
        all_symbols = prediction_symbols + [
            rejection.symbol for rejection in self.rejections
        ]
        if len(all_symbols) != len(set(all_symbols)):
            raise ValueError(
                "PredictionRun symbols must be unique across predictions and rejections"
            )
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "prediction_run_id",
            ArtifactId(f"prediction-run-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        """Return the result-affecting canonical payload."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "model_id": str(self.model_id),
            "model_definition_hash": self.model_definition_hash,
            "target_id": str(self.target_id),
            "evaluation_protocol_id": str(self.evaluation_protocol_id),
            "experiment_protocol_id": str(self.experiment_protocol_id),
            "dataset_id": str(self.dataset_id),
            "universe_id": str(self.universe_id),
            "decision_time": self.decision_time.isoformat(),
            "feature_definition_ids": [
                str(value) for value in self.feature_definition_ids
            ],
            "feature_materialization_ids": [
                str(value) for value in self.feature_materialization_ids
            ],
            "code_revision": self.code_revision,
            "configuration_hash": self.configuration_hash,
            "predictions": [
                _prediction_payload(prediction)
                for prediction in self.predictions
            ],
            "rejections": [
                _rejection_payload(rejection) for rejection in self.rejections
            ],
            "population_size": self.population_size,
            "ranking_coverage": float(self.ranking_coverage),
            "data_eligibility": self.data_eligibility.value,
            "evidence_level": self.evidence_level.value,
            "ranking_contract": self.ranking_contract,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return the semantic payload plus computed identity fields."""

        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "prediction_run_id": str(self.prediction_run_id),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PredictionRun:
        """Reconstruct and verify one canonical PredictionRun record."""

        expected = {
            "schema_version",
            "model_id",
            "model_definition_hash",
            "target_id",
            "evaluation_protocol_id",
            "experiment_protocol_id",
            "dataset_id",
            "universe_id",
            "decision_time",
            "feature_definition_ids",
            "feature_materialization_ids",
            "code_revision",
            "configuration_hash",
            "predictions",
            "rejections",
            "population_size",
            "ranking_coverage",
            "data_eligibility",
            "evidence_level",
            "ranking_contract",
            "content_hash",
            "prediction_run_id",
        }
        if set(payload) != expected:
            raise ValueError("PredictionRun fields mismatch")
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported PredictionRun schema")
        predictions = _object_list(payload.get("predictions"), "predictions")
        rejections = _object_list(payload.get("rejections"), "rejections")
        result = cls(
            model_id=ModelId(_string(payload.get("model_id"), "model_id")),
            model_definition_hash=_string(
                payload.get("model_definition_hash"),
                "model_definition_hash",
            ),
            target_id=TargetId(_string(payload.get("target_id"), "target_id")),
            evaluation_protocol_id=EvaluationProtocolId(
                _string(
                    payload.get("evaluation_protocol_id"),
                    "evaluation_protocol_id",
                )
            ),
            experiment_protocol_id=ExperimentId(
                _string(
                    payload.get("experiment_protocol_id"),
                    "experiment_protocol_id",
                )
            ),
            dataset_id=DatasetId(_string(payload.get("dataset_id"), "dataset_id")),
            universe_id=UniverseId(
                _string(payload.get("universe_id"), "universe_id")
            ),
            decision_time=DecisionTime(
                _aware_datetime(payload.get("decision_time"), "decision_time")
            ),
            feature_definition_ids=tuple(
                FeatureDefinitionId(value)
                for value in _string_list(
                    payload.get("feature_definition_ids"),
                    "feature_definition_ids",
                )
            ),
            feature_materialization_ids=tuple(
                FeatureMaterializationId(value)
                for value in _string_list(
                    payload.get("feature_materialization_ids"),
                    "feature_materialization_ids",
                )
            ),
            code_revision=_string(payload.get("code_revision"), "code_revision"),
            configuration_hash=_string(
                payload.get("configuration_hash"),
                "configuration_hash",
            ),
            predictions=tuple(_prediction_from_payload(value) for value in predictions),
            rejections=tuple(_rejection_from_payload(value) for value in rejections),
            population_size=_integer(
                payload.get("population_size"),
                "population_size",
            ),
            ranking_coverage=_number(
                payload.get("ranking_coverage"),
                "ranking_coverage",
            ),
            data_eligibility=DataEligibility(
                _string(payload.get("data_eligibility"), "data_eligibility")
            ),
            evidence_level=EvidenceLevel(
                _string(payload.get("evidence_level"), "evidence_level")
            ),
            ranking_contract=_string(
                payload.get("ranking_contract"),
                "ranking_contract",
            ),
        )
        supplied_hash = _string(payload.get("content_hash"), "content_hash")
        if _CONTENT_HASH.fullmatch(supplied_hash) is None:
            raise ValueError("PredictionRun content hash is invalid")
        if result.content_hash != supplied_hash:
            raise ValueError("PredictionRun content hash mismatch")
        if str(result.prediction_run_id) != _string(
            payload.get("prediction_run_id"),
            "prediction_run_id",
        ):
            raise ValueError("PredictionRun identity mismatch")
        return result


def _prediction_payload(value: CandidatePrediction) -> dict[str, Any]:
    return {
        "symbol": value.symbol,
        "universe_id": str(value.universe_id),
        "model_id": str(value.model_id),
        "target_id": str(value.target_id),
        "decision_time": value.decision_time.isoformat(),
        "experiment_id": str(value.experiment_id),
        "population_size": value.population_size,
        "model_score": value.model_score,
        "rank": value.rank,
        "percentile": value.percentile,
        "calibrated_probability": value.calibrated_probability,
        "expected_return": value.expected_return,
        "expected_mfe": value.expected_mfe,
        "expected_mae": value.expected_mae,
        "uncertainty": value.uncertainty,
        "expires_at": (
            value.expires_at.isoformat() if value.expires_at is not None else None
        ),
    }


def _prediction_from_payload(payload: Mapping[str, Any]) -> CandidatePrediction:
    expected = {
        "symbol",
        "universe_id",
        "model_id",
        "target_id",
        "decision_time",
        "experiment_id",
        "population_size",
        "model_score",
        "rank",
        "percentile",
        "calibrated_probability",
        "expected_return",
        "expected_mfe",
        "expected_mae",
        "uncertainty",
        "expires_at",
    }
    if set(payload) != expected:
        raise ValueError("CandidatePrediction fields mismatch")
    expires_at = payload.get("expires_at")
    return CandidatePrediction(
        symbol=_string(payload.get("symbol"), "prediction symbol"),
        universe_id=UniverseId(
            _string(payload.get("universe_id"), "prediction universe_id")
        ),
        model_id=ModelId(
            _string(payload.get("model_id"), "prediction model_id")
        ),
        target_id=TargetId(
            _string(payload.get("target_id"), "prediction target_id")
        ),
        decision_time=DecisionTime(
            _aware_datetime(
                payload.get("decision_time"),
                "prediction decision_time",
            )
        ),
        experiment_id=ExperimentId(
            _string(payload.get("experiment_id"), "prediction experiment_id")
        ),
        population_size=_optional_integer(
            payload.get("population_size"),
            "prediction population_size",
        ),
        model_score=_optional_number(
            payload.get("model_score"),
            "prediction model_score",
        ),
        rank=_optional_integer(payload.get("rank"), "prediction rank"),
        percentile=_optional_number(
            payload.get("percentile"),
            "prediction percentile",
        ),
        calibrated_probability=_optional_number(
            payload.get("calibrated_probability"),
            "prediction calibrated_probability",
        ),
        expected_return=_optional_number(
            payload.get("expected_return"),
            "prediction expected_return",
        ),
        expected_mfe=_optional_number(
            payload.get("expected_mfe"),
            "prediction expected_mfe",
        ),
        expected_mae=_optional_number(
            payload.get("expected_mae"),
            "prediction expected_mae",
        ),
        uncertainty=_optional_number(
            payload.get("uncertainty"),
            "prediction uncertainty",
        ),
        expires_at=(
            CandidateExpiryTime(
                _aware_datetime(expires_at, "prediction expires_at")
            )
            if expires_at is not None
            else None
        ),
    )


def _rejection_payload(value: CandidateRankingRejection) -> dict[str, Any]:
    return {
        "symbol": value.symbol,
        "reason_code": value.reason_code,
        "feature_id": str(value.feature_id),
    }


def _rejection_from_payload(
    payload: Mapping[str, Any],
) -> CandidateRankingRejection:
    if set(payload) != {"symbol", "reason_code", "feature_id"}:
        raise ValueError("CandidateRankingRejection fields mismatch")
    return CandidateRankingRejection(
        symbol=_string(payload.get("symbol"), "rejection symbol"),
        reason_code=_string(payload.get("reason_code"), "rejection reason_code"),
        feature_id=FeatureDefinitionId(
            _string(payload.get("feature_id"), "rejection feature_id")
        ),
    )


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label)


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _number(value, label)


def _aware_datetime(value: object, label: str) -> datetime:
    raw = _string(value, label)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return value


def _object_list(value: object, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value
