"""Exploratory multi-target model training and Shadow inference contracts.

This owner is intentionally below the Formal evidence floor.  It may produce a
real, replayable Research/Challenger model, but it cannot qualify PIT, consume
locked OOS evidence, calibrate a score, or authorize Production use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import exp, log1p
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
    ResearchExperimentDefinition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.forecasting.regularized_linear import (
    RegularizedMultiTargetModel,
    TrainingMatrix,
    fit_regularized_multi_target,
)


RESEARCH_MODEL_IMPLEMENTATION = "deterministic-regularized-linear/v1"
RESEARCH_MODEL_LIMITATIONS = (
    "CALIBRATED_FALSE",
    "FORMAL_MODEL_QUALIFIED_FALSE",
    "FORMAL_OOS_FALSE",
    "FORMAL_PIT_FALSE",
    "FREE_DATA_EXPLORATORY",
    "NO_PRODUCTION_AUTHORITY",
    "RAW_BARRIER_LOGITS_NOT_PROBABILITIES",
    "UNQUALIFIED",
)


class ResearchModelStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class ResearchForecastStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class ResearchModelHeadKind(str, Enum):
    CONTINUOUS_EXPECTATION = "CONTINUOUS_EXPECTATION"
    LOGISTIC_RAW_LOGIT = "LOGISTIC_RAW_LOGIT"


@dataclass(frozen=True, slots=True)
class ResearchMeasureBinding:
    """Frozen mapping from a mathematical head to one Target V2 measure."""

    training_target_name: str
    target_reference: ValidationArtifactReference
    measure_kind: ForecastMeasureKind
    head_kind: ResearchModelHeadKind
    barrier_id: str | None = None

    def __post_init__(self) -> None:
        require_text("Research binding target name", self.training_target_name)
        if self.target_reference.artifact_kind != "OUTCOME_TARGET":
            raise ValueError("Research binding requires an Outcome Target owner")
        if self.measure_kind is ForecastMeasureKind.BARRIER_RAW_LOGIT:
            if not self.barrier_id or not self.barrier_id.strip():
                raise ValueError("Barrier raw-logit binding requires barrier_id")
        elif self.barrier_id is not None:
            raise ValueError("Only barrier-specific head may bind barrier_id")
        continuous = {
            ForecastMeasureKind.RANKING_SCORE,
            ForecastMeasureKind.EXPECTED_RETURN,
            ForecastMeasureKind.EXPECTED_DOWNSIDE,
            ForecastMeasureKind.EXPECTED_MFE,
            ForecastMeasureKind.EXPECTED_MAE,
        }
        raw_logits = {
            ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT,
            ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT,
            ForecastMeasureKind.BARRIER_RAW_LOGIT,
        }
        if self.head_kind is ResearchModelHeadKind.CONTINUOUS_EXPECTATION:
            if self.measure_kind not in continuous:
                raise ValueError("Continuous head cannot claim a score/probability measure")
        elif self.measure_kind not in raw_logits:
            raise ValueError("Logistic head may emit only an explicitly raw logit")

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            str(self.target_reference.artifact_id),
            self.measure_kind.value,
            self.barrier_id or "",
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "training_target_name": self.training_target_name,
            "target_reference": self.target_reference.to_canonical_dict(),
            "measure_kind": self.measure_kind.value,
            "head_kind": self.head_kind.value,
            "barrier_id": self.barrier_id,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchMeasureBinding:
        return cls(
            training_target_name=str(payload["training_target_name"]),
            target_reference=_reference(payload["target_reference"]),
            measure_kind=ForecastMeasureKind(str(payload["measure_kind"])),
            head_kind=ResearchModelHeadKind(str(payload["head_kind"])),
            barrier_id=(
                None if payload["barrier_id"] is None else str(payload["barrier_id"])
            ),
        )


@dataclass(frozen=True, slots=True)
class TimedResearchFeature:
    name: str
    value: Decimal | None
    effective_at: datetime
    available_at: datetime
    source_reference: ValidationArtifactReference
    source_value_path: str

    def __post_init__(self) -> None:
        require_text("Research feature name", self.name)
        require_text("Research feature value path", self.source_value_path)
        _aware("Research feature effective_at", self.effective_at)
        _aware("Research feature available_at", self.available_at)
        if self.value is not None and not self.value.is_finite():
            raise ValueError("Research feature value must be finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": None if self.value is None else str(self.value),
            "effective_at": timestamp(self.effective_at),
            "available_at": timestamp(self.available_at),
            "source_reference": self.source_reference.to_canonical_dict(),
            "source_value_path": self.source_value_path,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TimedResearchFeature:
        return cls(
            name=str(payload["name"]),
            value=(
                None
                if payload["value"] is None
                else Decimal(str(payload["value"]))
            ),
            effective_at=_instant(payload["effective_at"]),
            available_at=_instant(payload["available_at"]),
            source_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["source_reference"])
            ),
            source_value_path=str(payload["source_value_path"]),
        )


@dataclass(frozen=True, slots=True)
class TimedResearchTarget:
    name: str
    value: Decimal | bool
    available_at: datetime
    source_reference: ValidationArtifactReference
    source_value_path: str

    def __post_init__(self) -> None:
        require_text("Research target name", self.name)
        require_text("Research target value path", self.source_value_path)
        _aware("Research target available_at", self.available_at)
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("Research target value must be finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value if isinstance(self.value, bool) else str(self.value),
            "available_at": timestamp(self.available_at),
            "source_reference": self.source_reference.to_canonical_dict(),
            "source_value_path": self.source_value_path,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TimedResearchTarget:
        raw_value = payload["value"]
        value: Decimal | bool = (
            raw_value if isinstance(raw_value, bool) else Decimal(str(raw_value))
        )
        return cls(
            name=str(payload["name"]),
            value=value,
            available_at=_instant(payload["available_at"]),
            source_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["source_reference"])
            ),
            source_value_path=str(payload["source_value_path"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchTrainingSample:
    sample_id: ArtifactId
    sample_hash: str
    symbol: str
    trading_date: date
    decision_time: datetime
    features: tuple[TimedResearchFeature, ...]
    targets: tuple[TimedResearchTarget, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    schema_version: str = "research-training-sample/v1"

    def __post_init__(self) -> None:
        require_sha256("Research sample hash", self.sample_hash)
        require_text("Research sample symbol", self.symbol)
        _aware("Research sample DecisionTime", self.decision_time)
        if self.features != tuple(sorted(self.features, key=lambda item: item.name)):
            raise ValueError("Research sample features must be sorted")
        if self.targets != tuple(sorted(self.targets, key=lambda item: item.name)):
            raise ValueError("Research sample targets must be sorted")
        if len({item.name for item in self.features}) != len(self.features):
            raise ValueError("Research sample features must be unique")
        if len({item.name for item in self.targets}) != len(self.targets):
            raise ValueError("Research sample targets must be unique")
        if {item.name for item in self.features}.intersection(
            item.name for item in self.targets
        ):
            raise ValueError("Target-bearing values cannot enter the feature set")
        expected_sources = _references(
            tuple(
                item.source_reference for item in (*self.features, *self.targets)
            )
        )
        if self.source_references != expected_sources:
            raise ValueError("Research sample owner bindings diverged")
        if canonical_hash(self.identity_payload()) != self.sample_hash:
            raise ValueError("Research sample hash mismatch")
        if self.sample_id != ArtifactId(f"research-training-sample:{self.sample_hash[7:]}"):
            raise ValueError("Research sample identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchTrainingSample:
        normalized = dict(values)
        normalized["features"] = tuple(
            sorted(values["features"], key=lambda item: item.name)
        )
        normalized["targets"] = tuple(
            sorted(values["targets"], key=lambda item: item.name)
        )
        normalized["source_references"] = _references(
            tuple(
                item.source_reference
                for item in (*normalized["features"], *normalized["targets"])
            )
        )
        payload = _sample_payload(**normalized)
        sample_id, digest = content_identity("research-training-sample", payload)
        return cls(sample_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _sample_payload(
            symbol=self.symbol,
            trading_date=self.trading_date,
            decision_time=self.decision_time,
            features=self.features,
            targets=self.targets,
            source_references=self.source_references,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "sample_id": str(self.sample_id),
            "sample_hash": self.sample_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchTrainingSample:
        return cls(
            sample_id=ArtifactId(str(payload["sample_id"])),
            sample_hash=str(payload["sample_hash"]),
            symbol=str(payload["symbol"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            decision_time=_instant(payload["decision_time"]),
            features=tuple(
                TimedResearchFeature.from_canonical_dict(_mapping(item))
                for item in _array(payload["features"])
            ),
            targets=tuple(
                TimedResearchTarget.from_canonical_dict(_mapping(item))
                for item in _array(payload["targets"])
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _array(payload["source_references"])
            ),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_name: str
    train_sample_ids: tuple[ArtifactId, ...]
    validation_sample_ids: tuple[ArtifactId, ...]
    purge_sessions: int
    embargo_sessions: int

    def __post_init__(self) -> None:
        require_text("Walk-forward fold name", self.fold_name)
        if not self.train_sample_ids or not self.validation_sample_ids:
            raise ValueError("Walk-forward fold requires train and validation samples")
        if self.train_sample_ids != tuple(sorted(set(self.train_sample_ids), key=str)):
            raise ValueError("Walk-forward train samples must be unique and sorted")
        if self.validation_sample_ids != tuple(
            sorted(set(self.validation_sample_ids), key=str)
        ):
            raise ValueError("Walk-forward validation samples must be unique and sorted")
        if set(self.train_sample_ids).intersection(self.validation_sample_ids):
            raise ValueError("Walk-forward train/validation overlap")
        if self.purge_sessions < 0 or self.embargo_sessions < 0:
            raise ValueError("Walk-forward purge/embargo cannot be negative")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "fold_name": self.fold_name,
            "train_sample_ids": [str(item) for item in self.train_sample_ids],
            "validation_sample_ids": [
                str(item) for item in self.validation_sample_ids
            ],
            "purge_sessions": self.purge_sessions,
            "embargo_sessions": self.embargo_sessions,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> WalkForwardFold:
        return cls(
            fold_name=str(payload["fold_name"]),
            train_sample_ids=tuple(
                ArtifactId(str(item)) for item in _array(payload["train_sample_ids"])
            ),
            validation_sample_ids=tuple(
                ArtifactId(str(item))
                for item in _array(payload["validation_sample_ids"])
            ),
            purge_sessions=int(payload["purge_sessions"]),
            embargo_sessions=int(payload["embargo_sessions"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchModelTrainingRequest:
    request_id: ArtifactId
    request_hash: str
    model_definition_reference: ValidationArtifactReference
    configuration_reference: ValidationArtifactReference
    feature_catalog_reference: ValidationArtifactReference
    target_protocol_reference: ValidationArtifactReference
    dataset_references: tuple[ValidationArtifactReference, ...]
    locked_oos_reference: ValidationArtifactReference
    locked_oos_sample_ids: tuple[ArtifactId, ...]
    oos_start_date: date
    session_sequence: tuple[date, ...]
    samples: tuple[ResearchTrainingSample, ...]
    folds: tuple[WalkForwardFold, ...]
    feature_names: tuple[str, ...]
    continuous_target_names: tuple[str, ...]
    barrier_target_names: tuple[str, ...]
    penalty_candidates: tuple[Decimal, ...]
    fold_seed: int
    code_revision: str
    code_hash: str
    requested_at: datetime
    experiment_definition: ResearchExperimentDefinition | None = None
    measure_bindings: tuple[ResearchMeasureBinding, ...] = ()
    limitations: tuple[str, ...] = RESEARCH_MODEL_LIMITATIONS
    schema_version: str = "research-model-training-request/v1"

    def __post_init__(self) -> None:
        require_sha256("Research Model request hash", self.request_hash)
        require_sha256("Research Model code hash", self.code_hash)
        require_text("Research Model code revision", self.code_revision)
        _aware("Research Model requested_at", self.requested_at)
        if self.dataset_references != _references(self.dataset_references):
            raise ValueError("Research Model datasets must be unique and sorted")
        if self.locked_oos_reference.artifact_kind not in {
            "LOCKED_OOS_PARTITION",
            "FORMAL_LOCKED_OOS_ROSTER",
        }:
            raise ValueError("Research Model must bind one locked OOS owner")
        if self.locked_oos_sample_ids != tuple(
            sorted(set(self.locked_oos_sample_ids), key=str)
        ):
            raise ValueError("Locked OOS identities must be unique and sorted")
        if self.session_sequence != tuple(sorted(set(self.session_sequence))):
            raise ValueError("Research Model session sequence must be unique and sorted")
        if self.samples != tuple(
            sorted(self.samples, key=lambda item: (item.trading_date, item.symbol, str(item.sample_id)))
        ):
            raise ValueError("Research Model samples must be time ordered")
        if len({item.sample_id for item in self.samples}) != len(self.samples):
            raise ValueError("Research Model samples must be unique")
        if set(item.sample_id for item in self.samples).intersection(
            self.locked_oos_sample_ids
        ):
            raise ValueError("Locked OOS samples cannot enter model selection")
        for names, label in (
            (self.feature_names, "features"),
            (self.continuous_target_names, "continuous targets"),
            (self.barrier_target_names, "barrier targets"),
        ):
            if not names or names != tuple(sorted(set(names))):
                raise ValueError(f"Research Model {label} must be non-empty, unique and sorted")
        if set(self.continuous_target_names).intersection(self.barrier_target_names):
            raise ValueError("Research Model target heads overlap")
        if self.penalty_candidates != tuple(sorted(set(self.penalty_candidates))):
            raise ValueError("Research Model penalties must be unique and sorted")
        if not self.penalty_candidates or any(
            not item.is_finite() or item <= 0 for item in self.penalty_candidates
        ):
            raise ValueError("Research Model penalties must be positive and finite")
        if not self.folds or tuple(item.fold_name for item in self.folds) != tuple(
            sorted(set(item.fold_name for item in self.folds))
        ):
            raise ValueError("Research Model folds must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Research Model limitations must be unique and sorted")
        if not set(RESEARCH_MODEL_LIMITATIONS).issubset(self.limitations):
            raise ValueError("Research Model authority ceiling is incomplete")
        if self.schema_version not in {
            "research-model-training-request/v1",
            "research-model-training-request/v2",
        }:
            raise ValueError("unsupported Research Model request schema")
        if self.schema_version.endswith("/v2"):
            self._validate_experiment_bindings()
        elif self.experiment_definition is not None or self.measure_bindings:
            raise ValueError("V1 Research Model request cannot carry V2 bindings")
        self._validate_samples_and_partitions()
        if canonical_hash(self.identity_payload()) != self.request_hash:
            raise ValueError("Research Model request hash mismatch")
        if self.request_id != ArtifactId(f"research-model-request:{self.request_hash[7:]}"):
            raise ValueError("Research Model request identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchModelTrainingRequest:
        normalized = dict(values)
        normalized["dataset_references"] = _references(values["dataset_references"])
        normalized["locked_oos_sample_ids"] = tuple(
            sorted(set(values["locked_oos_sample_ids"]), key=str)
        )
        normalized["session_sequence"] = tuple(sorted(set(values["session_sequence"])))
        normalized["samples"] = tuple(
            sorted(
                values["samples"],
                key=lambda item: (item.trading_date, item.symbol, str(item.sample_id)),
            )
        )
        normalized["folds"] = tuple(
            sorted(values["folds"], key=lambda item: item.fold_name)
        )
        for name in (
            "feature_names",
            "continuous_target_names",
            "barrier_target_names",
        ):
            normalized[name] = tuple(sorted(set(values[name])))
        normalized["penalty_candidates"] = tuple(
            sorted(set(values["penalty_candidates"]))
        )
        normalized["measure_bindings"] = tuple(
            sorted(set(values.get("measure_bindings", ())), key=lambda item: item.key)
        )
        normalized["schema_version"] = (
            "research-model-training-request/v2"
            if values.get("experiment_definition") is not None
            else "research-model-training-request/v1"
        )
        normalized["limitations"] = tuple(
            sorted(set(values.get("limitations", RESEARCH_MODEL_LIMITATIONS)))
        )
        payload = _request_payload(**normalized)
        request_id, digest = content_identity("research-model-request", payload)
        return cls(request_id, digest, **normalized)

    def _validate_experiment_bindings(self) -> None:
        experiment = self.experiment_definition
        if experiment is None or not self.measure_bindings:
            raise ValueError("V2 Research Model requires frozen Experiment measure bindings")
        if self.feature_catalog_reference != experiment.feature_reference:
            raise ValueError("Research Model feature owner diverged from Experiment")
        if RESEARCH_MODEL_IMPLEMENTATION not in experiment.allowed_model_families:
            raise ValueError("Research Model implementation is outside frozen model family")
        if self.fold_seed not in experiment.random_seeds:
            raise ValueError("Research Model seed is outside frozen randomness policy")
        if len(self.penalty_candidates) * len(self.folds) + 1 > experiment.search_budget.max_model_fits:
            raise ValueError("Research Model search exceeds frozen model-fit budget")
        penalty_domain = next(
            (
                item
                for item in experiment.hyperparameter_space
                if item.parameter_name == "ridge_penalty"
            ),
            None,
        )
        if penalty_domain is None or not {
            str(item) for item in self.penalty_candidates
        }.issubset(penalty_domain.allowed_values):
            raise ValueError("Research Model penalties exceed frozen hyperparameter space")
        if self.measure_bindings != tuple(
            sorted(self.measure_bindings, key=lambda item: item.key)
        ) or len({item.key for item in self.measure_bindings}) != len(self.measure_bindings):
            raise ValueError("Research Model measure bindings must be unique and sorted")
        if len({item.training_target_name for item in self.measure_bindings}) != len(
            self.measure_bindings
        ):
            raise ValueError("One training head cannot map to multiple measures")
        if any(
            item.target_reference not in experiment.target_references
            for item in self.measure_bindings
        ):
            raise ValueError("Research Model measure target is outside frozen Experiment")
        continuous = {
            item.training_target_name
            for item in self.measure_bindings
            if item.head_kind is ResearchModelHeadKind.CONTINUOUS_EXPECTATION
        }
        logits = {
            item.training_target_name
            for item in self.measure_bindings
            if item.head_kind is ResearchModelHeadKind.LOGISTIC_RAW_LOGIT
        }
        if continuous != set(self.continuous_target_names) or logits != set(
            self.barrier_target_names
        ):
            raise ValueError("Research Model head projection diverged from measure bindings")

    def _validate_samples_and_partitions(self) -> None:
        samples = {item.sample_id: item for item in self.samples}
        session_index = {item: index for index, item in enumerate(self.session_sequence)}
        expected_targets = set(self.continuous_target_names) | set(
            self.barrier_target_names
        )
        for sample in self.samples:
            if sample.trading_date not in session_index:
                raise ValueError("Research sample date is outside the frozen sessions")
            if sample.trading_date >= self.oos_start_date:
                raise ValueError("Research sample crosses into locked OOS time")
            if tuple(item.name for item in sample.features) != self.feature_names:
                raise ValueError("Research sample feature projection mismatch")
            if {item.name for item in sample.targets} != expected_targets:
                raise ValueError("Research sample target projection mismatch")
            for feature in sample.features:
                if (
                    feature.effective_at > sample.decision_time
                    or feature.available_at > sample.decision_time
                ):
                    raise ValueError("Future feature rejected at DecisionTime")
            for target in sample.targets:
                if target.available_at > self.requested_at:
                    raise ValueError("Unavailable target rejected at training time")
                if target.name in self.continuous_target_names and isinstance(
                    target.value, bool
                ):
                    raise ValueError("Continuous target must be numeric")
                if target.name in self.barrier_target_names and not isinstance(
                    target.value, bool
                ):
                    raise ValueError("Barrier target must be boolean")
        if self.oos_start_date not in session_index:
            raise ValueError("OOS start must exist in the frozen session sequence")
        all_selection_ids: set[ArtifactId] = set()
        for fold in self.folds:
            train = tuple(samples.get(item) for item in fold.train_sample_ids)
            validation = tuple(samples.get(item) for item in fold.validation_sample_ids)
            if any(item is None for item in (*train, *validation)):
                raise ValueError("Walk-forward fold references an unknown sample")
            typed_train = tuple(item for item in train if item is not None)
            typed_validation = tuple(item for item in validation if item is not None)
            train_end = max(session_index[item.trading_date] for item in typed_train)
            validation_start = min(
                session_index[item.trading_date] for item in typed_validation
            )
            if train_end >= validation_start:
                raise ValueError("Walk-forward training must precede validation")
            if validation_start - train_end - 1 < fold.purge_sessions:
                raise ValueError("Walk-forward purge window is violated")
            validation_end = max(
                session_index[item.trading_date] for item in typed_validation
            )
            oos_start = session_index[self.oos_start_date]
            if oos_start - validation_end - 1 < fold.embargo_sessions:
                raise ValueError("Walk-forward OOS embargo window is violated")
            all_selection_ids.update(fold.train_sample_ids)
            all_selection_ids.update(fold.validation_sample_ids)
        if all_selection_ids != set(samples):
            raise ValueError("Every selection sample must be assigned to a fold")

    def identity_payload(self) -> dict[str, Any]:
        return _request_payload(**{
            name: getattr(self, name)
            for name in _request_value_names()
        })

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "request_hash": self.request_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchModelTrainingRequest:
        return cls(
            request_id=ArtifactId(str(payload["request_id"])),
            request_hash=str(payload["request_hash"]),
            model_definition_reference=_reference(payload["model_definition_reference"]),
            configuration_reference=_reference(payload["configuration_reference"]),
            feature_catalog_reference=_reference(payload["feature_catalog_reference"]),
            target_protocol_reference=_reference(payload["target_protocol_reference"]),
            dataset_references=tuple(_reference(item) for item in _array(payload["dataset_references"])),
            locked_oos_reference=_reference(payload["locked_oos_reference"]),
            locked_oos_sample_ids=tuple(ArtifactId(str(item)) for item in _array(payload["locked_oos_sample_ids"])),
            oos_start_date=date.fromisoformat(str(payload["oos_start_date"])),
            session_sequence=tuple(date.fromisoformat(str(item)) for item in _array(payload["session_sequence"])),
            samples=tuple(ResearchTrainingSample.from_canonical_dict(_mapping(item)) for item in _array(payload["samples"])),
            folds=tuple(WalkForwardFold.from_canonical_dict(_mapping(item)) for item in _array(payload["folds"])),
            feature_names=tuple(str(item) for item in _array(payload["feature_names"])),
            continuous_target_names=tuple(str(item) for item in _array(payload["continuous_target_names"])),
            barrier_target_names=tuple(str(item) for item in _array(payload["barrier_target_names"])),
            penalty_candidates=tuple(Decimal(str(item)) for item in _array(payload["penalty_candidates"])),
            fold_seed=int(payload["fold_seed"]),
            code_revision=str(payload["code_revision"]),
            code_hash=str(payload["code_hash"]),
            requested_at=_instant(payload["requested_at"]),
            experiment_definition=(
                None
                if payload.get("experiment_definition") is None
                else ResearchExperimentDefinition.from_canonical_dict(
                    _mapping(payload["experiment_definition"])
                )
            ),
            measure_bindings=tuple(
                ResearchMeasureBinding.from_canonical_dict(_mapping(item))
                for item in _array(payload.get("measure_bindings", []))
            ),
            limitations=tuple(str(item) for item in _array(payload["limitations"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchModelCandidateDiagnostic:
    penalty: Decimal
    fold_losses: tuple[tuple[str, Decimal], ...]
    aggregate_loss: Decimal | None
    status: ResearchModelStatus
    reason_codes: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "penalty": str(self.penalty),
            "fold_losses": [
                {"fold_name": name, "loss": str(loss)}
                for name, loss in self.fold_losses
            ],
            "aggregate_loss": (
                None if self.aggregate_loss is None else str(self.aggregate_loss)
            ),
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchModelCandidateDiagnostic:
        return cls(
            penalty=Decimal(str(payload["penalty"])),
            fold_losses=tuple(
                (str(_mapping(item)["fold_name"]), Decimal(str(_mapping(item)["loss"])))
                for item in _array(payload["fold_losses"])
            ),
            aggregate_loss=(
                None
                if payload["aggregate_loss"] is None
                else Decimal(str(payload["aggregate_loss"]))
            ),
            status=ResearchModelStatus(str(payload["status"])),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
        )


@dataclass(frozen=True, slots=True)
class ResearchModelArtifact:
    artifact_id: ArtifactId
    artifact_hash: str
    request_reference: ValidationArtifactReference
    status: ResearchModelStatus
    selected_penalty: Decimal | None
    diagnostics: tuple[ResearchModelCandidateDiagnostic, ...]
    model: RegularizedMultiTargetModel | None
    model_parameter_hash: str | None
    trained_at: datetime
    reason_codes: tuple[str, ...]
    research_model_available: bool
    runtime_role: str = "RESEARCH_CHALLENGER"
    formal_model_qualified: bool = False
    formal_oos: bool = False
    calibrated: bool = False
    production_authorized: bool = False
    limitations: tuple[str, ...] = RESEARCH_MODEL_LIMITATIONS
    schema_version: str = "research-model-artifact/v2"

    def __post_init__(self) -> None:
        require_sha256("Research Model artifact hash", self.artifact_hash)
        _aware("Research Model trained_at", self.trained_at)
        if (self.status is ResearchModelStatus.AVAILABLE) != (self.model is not None):
            raise ValueError("Research Model status/model mismatch")
        if self.research_model_available != (self.model is not None):
            raise ValueError("Research Model availability flag mismatch")
        if self.runtime_role != "RESEARCH_CHALLENGER":
            raise ValueError("Research Model runtime role must remain Challenger-only")
        if self.model is not None and self.model.penalty != self.selected_penalty:
            raise ValueError("Research Model selected penalty mismatch")
        if (self.model is None) != (self.model_parameter_hash is None):
            raise ValueError("Research Model parameter hash/model mismatch")
        if self.model_parameter_hash is not None:
            require_sha256("Research Model parameter hash", self.model_parameter_hash)
        if self.schema_version not in {
            "research-model-artifact/v1",
            "research-model-artifact/v2",
        }:
            raise ValueError("unsupported Research Model artifact schema")
        if self.formal_model_qualified or self.formal_oos or self.calibrated or self.production_authorized:
            raise ValueError("Exploratory Research Model cannot claim Formal authority")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Research Model reasons must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Research Model limitations must be unique and sorted")
        if not set(RESEARCH_MODEL_LIMITATIONS).issubset(self.limitations):
            raise ValueError("Research Model authority ceiling is incomplete")
        if canonical_hash(self.identity_payload()) != self.artifact_hash:
            raise ValueError("Research Model artifact hash mismatch")
        if self.artifact_id != ArtifactId(f"research-model:{self.artifact_hash[7:]}"):
            raise ValueError("Research Model artifact identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchModelArtifact:
        normalized = dict(values)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["limitations"] = tuple(sorted(set(values.get("limitations", RESEARCH_MODEL_LIMITATIONS))))
        payload = _artifact_payload(**normalized)
        artifact_id, digest = content_identity("research-model", payload)
        return cls(artifact_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _artifact_payload(**{
            name: getattr(self, name)
            for name in _artifact_value_names()
        })

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "artifact_hash": self.artifact_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchModelArtifact:
        raw_model = payload["model"]
        return cls(
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            artifact_hash=str(payload["artifact_hash"]),
            request_reference=_reference(payload["request_reference"]),
            status=ResearchModelStatus(str(payload["status"])),
            selected_penalty=None if payload["selected_penalty"] is None else Decimal(str(payload["selected_penalty"])),
            diagnostics=tuple(ResearchModelCandidateDiagnostic.from_canonical_dict(_mapping(item)) for item in _array(payload["diagnostics"])),
            model=None if raw_model is None else RegularizedMultiTargetModel.from_canonical_dict(_mapping(raw_model)),
            model_parameter_hash=(
                None
                if payload.get("model_parameter_hash") is None
                else str(payload["model_parameter_hash"])
            ),
            trained_at=_instant(payload["trained_at"]),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
            research_model_available=_boolean(payload["research_model_available"]),
            runtime_role=str(payload["runtime_role"]),
            formal_model_qualified=_boolean(payload["formal_model_qualified"]),
            formal_oos=_boolean(payload["formal_oos"]),
            calibrated=_boolean(payload["calibrated"]),
            production_authorized=_boolean(payload["production_authorized"]),
            limitations=tuple(str(item) for item in _array(payload["limitations"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchInferenceRequest:
    symbol: str
    decision_time: datetime
    features: tuple[TimedResearchFeature, ...]
    model_definition_hash: str
    configuration_hash: str
    code_revision: str
    code_hash: str

    def __post_init__(self) -> None:
        require_text("Research inference symbol", self.symbol)
        _aware("Research inference DecisionTime", self.decision_time)
        require_sha256("Research inference Model Definition hash", self.model_definition_hash)
        require_sha256("Research inference Configuration hash", self.configuration_hash)
        require_sha256("Research inference code hash", self.code_hash)
        require_text("Research inference code revision", self.code_revision)
        if self.features != tuple(sorted(self.features, key=lambda item: item.name)):
            raise ValueError("Research inference features must be sorted")
        if len({item.name for item in self.features}) != len(self.features):
            raise ValueError("Research inference features must be unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision_time": timestamp(self.decision_time),
            "features": [item.to_canonical_dict() for item in self.features],
            "model_definition_hash": self.model_definition_hash,
            "configuration_hash": self.configuration_hash,
            "code_revision": self.code_revision,
            "code_hash": self.code_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchInferenceRequest:
        return cls(
            symbol=str(payload["symbol"]),
            decision_time=_instant(payload["decision_time"]),
            features=tuple(
                TimedResearchFeature.from_canonical_dict(_mapping(item))
                for item in _array(payload["features"])
            ),
            model_definition_hash=str(payload["model_definition_hash"]),
            configuration_hash=str(payload["configuration_hash"]),
            code_revision=str(payload["code_revision"]),
            code_hash=str(payload["code_hash"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchForecastResult:
    status: ResearchForecastStatus
    symbol: str
    decision_time: datetime
    continuous_estimates: tuple[tuple[str, Decimal], ...]
    raw_barrier_logits: tuple[tuple[str, Decimal], ...]
    reason_codes: tuple[str, ...]
    research_model_available: bool
    formal_model_qualified: bool = False
    formal_oos: bool = False
    calibrated: bool = False
    barrier_scores_are_probabilities: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "symbol": self.symbol,
            "decision_time": timestamp(self.decision_time),
            "continuous_estimates": {name: str(value) for name, value in self.continuous_estimates},
            "raw_barrier_logits": {name: str(value) for name, value in self.raw_barrier_logits},
            "reason_codes": list(self.reason_codes),
            "research_model_available": self.research_model_available,
            "formal_model_qualified": self.formal_model_qualified,
            "formal_oos": self.formal_oos,
            "calibrated": self.calibrated,
            "barrier_scores_are_probabilities": self.barrier_scores_are_probabilities,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchForecastResult:
        continuous = _mapping(payload["continuous_estimates"])
        barriers = _mapping(payload["raw_barrier_logits"])
        return cls(
            status=ResearchForecastStatus(str(payload["status"])),
            symbol=str(payload["symbol"]),
            decision_time=_instant(payload["decision_time"]),
            continuous_estimates=tuple(
                sorted((str(name), Decimal(str(value))) for name, value in continuous.items())
            ),
            raw_barrier_logits=tuple(
                sorted((str(name), Decimal(str(value))) for name, value in barriers.items())
            ),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
            research_model_available=_boolean(payload["research_model_available"]),
            formal_model_qualified=_boolean(payload["formal_model_qualified"]),
            formal_oos=_boolean(payload["formal_oos"]),
            calibrated=_boolean(payload["calibrated"]),
            barrier_scores_are_probabilities=_boolean(payload["barrier_scores_are_probabilities"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchModelInferenceReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    model_reference: ValidationArtifactReference
    request: ResearchInferenceRequest
    result: ResearchForecastResult
    source_references: tuple[ValidationArtifactReference, ...]
    executed_at: datetime
    formal_model_qualified: bool = False
    formal_oos: bool = False
    calibrated: bool = False
    production_authorized: bool = False
    schema_version: str = "research-model-inference-receipt/v1"

    def __post_init__(self) -> None:
        require_sha256("Research inference receipt hash", self.receipt_hash)
        _aware("Research inference executed_at", self.executed_at)
        if self.model_reference.artifact_kind != "RESEARCH_MODEL_ARTIFACT":
            raise ValueError("Research inference must bind a Research Model owner")
        expected_sources = _references(
            (self.model_reference, *(item.source_reference for item in self.request.features))
        )
        if self.source_references != expected_sources:
            raise ValueError("Research inference source bindings diverged")
        if self.result.symbol != self.request.symbol or self.result.decision_time != self.request.decision_time:
            raise ValueError("Research inference result/request mismatch")
        if self.formal_model_qualified or self.formal_oos or self.calibrated or self.production_authorized:
            raise ValueError("Research inference cannot claim Formal authority")
        if canonical_hash(self.identity_payload()) != self.receipt_hash:
            raise ValueError("Research inference receipt hash mismatch")
        if self.receipt_id != ArtifactId(f"research-model-inference:{self.receipt_hash[7:]}"):
            raise ValueError("Research inference receipt identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchModelInferenceReceipt:
        normalized = dict(values)
        normalized["source_references"] = _references(
            (values["model_reference"], *(item.source_reference for item in values["request"].features))
        )
        payload = _inference_receipt_payload(**normalized)
        receipt_id, digest = content_identity("research-model-inference", payload)
        return cls(receipt_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _inference_receipt_payload(
            model_reference=self.model_reference,
            request=self.request,
            result=self.result,
            source_references=self.source_references,
            executed_at=self.executed_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchModelInferenceReceipt:
        return cls(
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            receipt_hash=str(payload["receipt_hash"]),
            model_reference=_reference(payload["model_reference"]),
            request=ResearchInferenceRequest.from_canonical_dict(_mapping(payload["request"])),
            result=ResearchForecastResult.from_canonical_dict(_mapping(payload["result"])),
            source_references=tuple(_reference(item) for item in _array(payload["source_references"])),
            executed_at=_instant(payload["executed_at"]),
            formal_model_qualified=_boolean(payload["formal_model_qualified"]),
            formal_oos=_boolean(payload["formal_oos"]),
            calibrated=_boolean(payload["calibrated"]),
            production_authorized=_boolean(payload["production_authorized"]),
            schema_version=str(payload["schema_version"]),
        )


class RegularizedLinearForecastExecutor:
    """Execute only the exact exploratory artifact and frozen code lineage."""

    def __init__(
        self,
        *,
        artifact: ResearchModelArtifact,
        request: ResearchModelTrainingRequest,
    ) -> None:
        if artifact.request_reference != ValidationArtifactReference(
            "RESEARCH_MODEL_TRAINING_REQUEST", request.request_id, request.request_hash
        ):
            raise ValueError("Research Model artifact/request binding mismatch")
        self._artifact = artifact
        self._request = request

    @property
    def executor_identity(self) -> str:
        return RESEARCH_MODEL_IMPLEMENTATION

    def execute(self, request: ResearchInferenceRequest) -> ResearchForecastResult:
        reasons: set[str] = set()
        model = self._artifact.model
        if model is None or self._artifact.status is not ResearchModelStatus.AVAILABLE:
            reasons.add("RESEARCH_MODEL_NOT_AVAILABLE")
        if model is not None and model.implementation != RESEARCH_MODEL_IMPLEMENTATION:
            reasons.add("RESEARCH_MODEL_IMPLEMENTATION_UNSUPPORTED")
        if request.model_definition_hash != self._request.model_definition_reference.content_hash:
            reasons.add("MODEL_DEFINITION_HASH_MISMATCH")
        if request.configuration_hash != self._request.configuration_reference.content_hash:
            reasons.add("MODEL_CONFIGURATION_HASH_MISMATCH")
        if request.code_revision != self._request.code_revision or request.code_hash != self._request.code_hash:
            reasons.add("MODEL_CODE_IDENTITY_MISMATCH")
        features = {item.name: item for item in request.features}
        if tuple(sorted(features)) != self._request.feature_names:
            reasons.add("INFERENCE_FEATURE_SET_INCOMPLETE")
        for feature in request.features:
            if feature.effective_at > request.decision_time or feature.available_at > request.decision_time:
                reasons.add(f"FUTURE_FEATURE_REJECTED:{feature.name}")
        if reasons or model is None:
            return ResearchForecastResult(
                ResearchForecastStatus.NOT_ESTIMABLE,
                request.symbol,
                request.decision_time,
                (),
                (),
                tuple(sorted(reasons)),
                self._artifact.research_model_available,
            )
        prediction = model.predict({name: features[name].value for name in model.feature_names})
        return ResearchForecastResult(
            ResearchForecastStatus.AVAILABLE,
            request.symbol,
            request.decision_time,
            tuple(sorted(prediction.continuous.items())),
            tuple(sorted(prediction.raw_barrier_logits.items())),
            ("EXPLORATORY_RESEARCH_FORECAST_AVAILABLE",),
            True,
        )


def train_research_model(
    request: ResearchModelTrainingRequest,
    *,
    trained_at: datetime,
) -> ResearchModelArtifact:
    _aware("Research Model trained_at", trained_at)
    required_at = max(
        request.requested_at,
        *(feature.available_at for sample in request.samples for feature in sample.features),
        *(target.available_at for sample in request.samples for target in sample.targets),
    )
    if trained_at < required_at:
        raise ValueError("Research Model trained_at cannot predate required input availability")
    diagnostics = []
    samples = {item.sample_id: item for item in request.samples}
    for penalty in request.penalty_candidates:
        fold_losses: list[tuple[str, Decimal]] = []
        reasons: set[str] = set()
        for fold in request.folds:
            train = tuple(samples[item] for item in fold.train_sample_ids)
            validation = tuple(samples[item] for item in fold.validation_sample_ids)
            try:
                model = fit_regularized_multi_target(
                    _matrix(request, train), penalty=penalty
                )
                fold_losses.append((fold.fold_name, _loss(model, request, validation)))
            except ValueError as error:
                reasons.add(f"FOLD_NOT_ESTIMABLE:{fold.fold_name}:{error}")
        aggregate = (
            None
            if reasons or not fold_losses
            else sum((item[1] for item in fold_losses), Decimal("0"))
            / Decimal(len(fold_losses))
        )
        diagnostics.append(
            ResearchModelCandidateDiagnostic(
                penalty=penalty,
                fold_losses=tuple(fold_losses),
                aggregate_loss=aggregate,
                status=(
                    ResearchModelStatus.AVAILABLE
                    if aggregate is not None
                    else ResearchModelStatus.NOT_ESTIMABLE
                ),
                reason_codes=tuple(sorted(reasons)),
            )
        )
    viable = tuple(item for item in diagnostics if item.aggregate_loss is not None)
    request_reference = ValidationArtifactReference(
        "RESEARCH_MODEL_TRAINING_REQUEST", request.request_id, request.request_hash
    )
    if not viable:
        return ResearchModelArtifact.create(
            request_reference=request_reference,
            status=ResearchModelStatus.NOT_ESTIMABLE,
            selected_penalty=None,
            diagnostics=tuple(diagnostics),
            model=None,
            model_parameter_hash=None,
            trained_at=trained_at,
            reason_codes=("NO_ESTIMABLE_HYPERPARAMETER_CANDIDATE",),
            research_model_available=False,
        )
    selected = min(viable, key=lambda item: (item.aggregate_loss, item.penalty))
    try:
        final_model = fit_regularized_multi_target(
            _matrix(request, request.samples), penalty=selected.penalty
        )
    except ValueError as error:
        return ResearchModelArtifact.create(
            request_reference=request_reference,
            status=ResearchModelStatus.NOT_ESTIMABLE,
            selected_penalty=selected.penalty,
            diagnostics=tuple(diagnostics),
            model=None,
            model_parameter_hash=None,
            trained_at=trained_at,
            reason_codes=(f"FINAL_FIT_NOT_ESTIMABLE:{error}",),
            research_model_available=False,
        )
    return ResearchModelArtifact.create(
        request_reference=request_reference,
        status=ResearchModelStatus.AVAILABLE,
        selected_penalty=selected.penalty,
        diagnostics=tuple(diagnostics),
        model=final_model,
        model_parameter_hash=research_model_parameter_hash(request, final_model),
        trained_at=trained_at,
        reason_codes=("RESEARCH_MODEL_AVAILABLE", "WALK_FORWARD_SELECTION_COMPLETE"),
        research_model_available=True,
    )


def _matrix(
    request: ResearchModelTrainingRequest,
    samples: tuple[ResearchTrainingSample, ...],
) -> TrainingMatrix:
    rows = []
    continuous = {name: [] for name in request.continuous_target_names}
    barriers = {name: [] for name in request.barrier_target_names}
    for sample in samples:
        rows.append({item.name: item.value for item in sample.features})
        targets = {item.name: item.value for item in sample.targets}
        for name in continuous:
            value = targets[name]
            if isinstance(value, bool):
                raise ValueError("continuous target is boolean")
            continuous[name].append(value)
        for name in barriers:
            value = targets[name]
            if not isinstance(value, bool):
                raise ValueError("barrier target is not boolean")
            barriers[name].append(value)
    return TrainingMatrix.create(
        feature_names=request.feature_names,
        rows=tuple(rows),
        continuous_targets={name: tuple(values) for name, values in continuous.items()},
        barrier_targets={name: tuple(values) for name, values in barriers.items()},
    )


def research_model_parameter_hash(
    request: ResearchModelTrainingRequest,
    model: RegularizedMultiTargetModel,
) -> str:
    """Bind executable parameters to their explicit Target/measure projection."""

    return canonical_hash(
        {
            "schema_version": "research-model-parameter/v1",
            "implementation": RESEARCH_MODEL_IMPLEMENTATION,
            "model": model.to_canonical_dict(),
            "measure_bindings": [
                item.to_canonical_dict() for item in request.measure_bindings
            ],
        }
    )


def _loss(
    model: RegularizedMultiTargetModel,
    request: ResearchModelTrainingRequest,
    samples: tuple[ResearchTrainingSample, ...],
) -> Decimal:
    terms: list[Decimal] = []
    for sample in samples:
        prediction = model.predict({item.name: item.value for item in sample.features})
        targets = {item.name: item.value for item in sample.targets}
        for name in request.continuous_target_names:
            actual = targets[name]
            if isinstance(actual, bool):
                raise ValueError("continuous validation target is boolean")
            terms.append((prediction.continuous[name] - actual) ** 2)
        for name in request.barrier_target_names:
            actual = targets[name]
            if not isinstance(actual, bool):
                raise ValueError("barrier validation target is not boolean")
            logit = float(prediction.raw_barrier_logits[name])
            binary = 1.0 if actual else 0.0
            logistic_loss = max(logit, 0.0) - binary * logit + log1p(exp(-abs(logit)))
            terms.append(Decimal(str(logistic_loss)))
    if not terms:
        raise ValueError("validation loss has no observations")
    return sum(terms, Decimal("0")) / Decimal(len(terms))


def _sample_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "research-training-sample/v1",
        "symbol": values["symbol"],
        "trading_date": values["trading_date"].isoformat(),
        "decision_time": timestamp(values["decision_time"]),
        "features": [item.to_canonical_dict() for item in values["features"]],
        "targets": [item.to_canonical_dict() for item in values["targets"]],
        "source_references": [item.to_canonical_dict() for item in values["source_references"]],
    }


def _request_value_names() -> tuple[str, ...]:
    return (
        "model_definition_reference", "configuration_reference",
        "feature_catalog_reference", "target_protocol_reference",
        "dataset_references", "locked_oos_reference", "locked_oos_sample_ids",
        "oos_start_date", "session_sequence", "samples", "folds", "feature_names",
        "continuous_target_names", "barrier_target_names", "penalty_candidates",
        "fold_seed", "code_revision", "code_hash", "requested_at",
        "experiment_definition", "measure_bindings", "limitations", "schema_version",
    )


def _request_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values.get(
            "schema_version", "research-model-training-request/v1"
        ),
        "model_definition_reference": values["model_definition_reference"].to_canonical_dict(),
        "configuration_reference": values["configuration_reference"].to_canonical_dict(),
        "feature_catalog_reference": values["feature_catalog_reference"].to_canonical_dict(),
        "target_protocol_reference": values["target_protocol_reference"].to_canonical_dict(),
        "dataset_references": [item.to_canonical_dict() for item in values["dataset_references"]],
        "locked_oos_reference": values["locked_oos_reference"].to_canonical_dict(),
        "locked_oos_sample_ids": [str(item) for item in values["locked_oos_sample_ids"]],
        "oos_start_date": values["oos_start_date"].isoformat(),
        "session_sequence": [item.isoformat() for item in values["session_sequence"]],
        "samples": [item.to_canonical_dict() for item in values["samples"]],
        "folds": [item.to_canonical_dict() for item in values["folds"]],
        "feature_names": list(values["feature_names"]),
        "continuous_target_names": list(values["continuous_target_names"]),
        "barrier_target_names": list(values["barrier_target_names"]),
        "penalty_candidates": [str(item) for item in values["penalty_candidates"]],
        "fold_seed": values["fold_seed"],
        "code_revision": values["code_revision"],
        "code_hash": values["code_hash"],
        "requested_at": timestamp(values["requested_at"]),
        **(
            {
                "experiment_definition": values[
                    "experiment_definition"
                ].to_canonical_dict(),
                "measure_bindings": [
                    item.to_canonical_dict() for item in values["measure_bindings"]
                ],
            }
            if values.get("schema_version") == "research-model-training-request/v2"
            else {}
        ),
        "limitations": list(values["limitations"]),
    }


def _artifact_value_names() -> tuple[str, ...]:
    return (
        "request_reference", "status", "selected_penalty", "diagnostics", "model",
        "model_parameter_hash",
        "trained_at", "reason_codes", "research_model_available",
        "runtime_role",
        "formal_model_qualified", "formal_oos", "calibrated",
        "production_authorized", "limitations",
    )


def _artifact_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values.get("schema_version", "research-model-artifact/v2"),
        "request_reference": values["request_reference"].to_canonical_dict(),
        "status": values["status"].value,
        "selected_penalty": None if values["selected_penalty"] is None else str(values["selected_penalty"]),
        "diagnostics": [item.to_canonical_dict() for item in values["diagnostics"]],
        "model": None if values["model"] is None else values["model"].to_canonical_dict(),
        "model_parameter_hash": values["model_parameter_hash"],
        "trained_at": timestamp(values["trained_at"]),
        "reason_codes": list(values["reason_codes"]),
        "research_model_available": values["research_model_available"],
        "runtime_role": values.get("runtime_role", "RESEARCH_CHALLENGER"),
        "formal_model_qualified": values.get("formal_model_qualified", False),
        "formal_oos": values.get("formal_oos", False),
        "calibrated": values.get("calibrated", False),
        "production_authorized": values.get("production_authorized", False),
        "limitations": list(values["limitations"]),
    }


def _inference_receipt_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "research-model-inference-receipt/v1",
        "model_reference": values["model_reference"].to_canonical_dict(),
        "request": values["request"].to_canonical_dict(),
        "result": values["result"].to_canonical_dict(),
        "source_references": [item.to_canonical_dict() for item in values["source_references"]],
        "executed_at": timestamp(values["executed_at"]),
        "formal_model_qualified": False,
        "formal_oos": False,
        "calibrated": False,
        "production_authorized": False,
    }


def _references(values: tuple[ValidationArtifactReference, ...]) -> tuple[ValidationArtifactReference, ...]:
    return tuple(sorted(set(values), key=lambda item: (item.artifact_kind, str(item.artifact_id), item.content_hash)))


def _reference(value: object) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    _aware("timestamp", parsed)
    return parsed


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


__all__ = [
    "RESEARCH_MODEL_IMPLEMENTATION",
    "RegularizedLinearForecastExecutor",
    "ResearchForecastResult",
    "ResearchForecastStatus",
    "ResearchInferenceRequest",
    "ResearchMeasureBinding",
    "ResearchModelHeadKind",
    "ResearchModelArtifact",
    "ResearchModelCandidateDiagnostic",
    "ResearchModelInferenceReceipt",
    "ResearchModelStatus",
    "ResearchModelTrainingRequest",
    "ResearchTrainingSample",
    "TimedResearchFeature",
    "TimedResearchTarget",
    "WalkForwardFold",
    "train_research_model",
    "research_model_parameter_hash",
]
