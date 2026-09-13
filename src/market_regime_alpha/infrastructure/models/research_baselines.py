"""Transparent controls executed by the same FIT/Model/Forecast owners as Ridge.

The four controls deliberately share no fitted preprocessing. TRAINING_MEAN
estimates its sole constant from the frozen FIT roster; FEATURE and its inverse
use exactly one raw Feature value. None consumes evaluation labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DecimalException, Context, localcontext, ROUND_HALF_EVEN
import json
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestModelTrainingRecipe, BacktestModelTrainingRequirement, BacktestSpecification,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFitEvaluationExecution
from market_regime_alpha.research_qualification.ports.model_execution import (
    FittedModelPayload, FrozenModelTrainingInput, FrozenModelVersionPayload,
    ModelPrediction, ModelPredictionBatch, ModelScalarParameter, ModelScalarType,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest, ReproducibleModelTrainingRunRequest,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes


_COEFFICIENTS = {"ZERO": 0, "TRAINING_MEAN": 0, "FEATURE": 1, "INVERSE_FEATURE": -1}
KINDS = frozenset(_COEFFICIENTS)
_V2_COEFFICIENTS = {**_COEFFICIENTS, "TRAINING_MEDIAN": 0}
_VERSIONS = {"1.0.0": 1, "2.0.0": 2}
_QUANTUM = Decimal("0.000000000001")


def _bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _kind(parameters: tuple[ModelScalarParameter, ...], version: int) -> str:
    kinds = KINDS if version == 1 else _V2_COEFFICIENTS.keys()
    if (len(parameters) != 1 or parameters[0].parameter_code != "baseline_kind"
            or parameters[0].value_type is not ModelScalarType.TEXT or parameters[0].text_value not in kinds):
        raise ValueError("research baseline requires exactly one supported baseline_kind")
    assert parameters[0].text_value is not None
    return parameters[0].text_value


@dataclass(frozen=True, slots=True)
class BaselineArtifact:
    feature_definition_ids: tuple[UUID, ...]
    kind: str
    intercept: Decimal
    coefficient: Decimal
    seed: int
    sample_roster_sha256: str
    format_version: int = 1

    def payload(self) -> dict[str, object]:
        return {"schema": f"mra-research-baseline-v{self.format_version}", "kind": self.kind,
                "feature_definition_ids": [str(x) for x in self.feature_definition_ids],
                "intercept": str(self.intercept), "coefficient": str(self.coefficient),
                "seed": self.seed, "sample_roster_sha256": self.sample_roster_sha256}


def load_baseline_artifact(content: bytes) -> BaselineArtifact:
    try:
        p = json.loads(content)
        if not isinstance(p, dict) or set(p) != {"schema", "kind", "feature_definition_ids", "intercept", "coefficient", "seed", "sample_roster_sha256"}:
            raise ValueError("baseline Artifact requires exact fields")
        version = {"mra-research-baseline-v1": 1, "mra-research-baseline-v2": 2}.get(p["schema"])
        if version is None or p["kind"] not in (KINDS if version == 1 else _V2_COEFFICIENTS):
            raise ValueError("baseline Artifact schema or kind is unsupported")
        if not isinstance(p["feature_definition_ids"], list) or len(p["feature_definition_ids"]) != 1:
            raise ValueError("baseline Artifact requires exactly one Feature")
        if not isinstance(p["intercept"], str) or not isinstance(p["coefficient"], str):
            raise ValueError("baseline coefficients must be decimal strings")
        result = BaselineArtifact(tuple(UUID(x) for x in p["feature_definition_ids"]), p["kind"],
                                  Decimal(p["intercept"]), Decimal(p["coefficient"]), p["seed"], p["sample_roster_sha256"], version)
        if (type(result.seed) is not int or result.seed < 0
                or not result.intercept.is_finite() or not result.coefficient.is_finite()
                or result.coefficient != _V2_COEFFICIENTS[result.kind]
                or (result.kind not in {"TRAINING_MEAN", "TRAINING_MEDIAN"} and result.intercept != 0)):
            raise ValueError("baseline Artifact parameters violate its formula")
        from market_regime_alpha.shared.identity import ContentHash
        ContentHash(result.sample_roster_sha256)
        if _bytes(result.payload()) != content:
            raise ValueError("baseline Artifact is not canonical or contains duplicate fields")
        return result
    except (KeyError, TypeError, ArithmeticError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("baseline Artifact is invalid") from exc


class ResearchBaselineTrainer:
    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return algorithm_code == "research_baseline" and algorithm_version in _VERSIONS

    def fit(self, training: FrozenModelTrainingInput) -> FittedModelPayload:
        if not self.supports(training.algorithm_code, training.algorithm_version):
            raise ValueError("baseline adapter cannot execute this algorithm")
        version = _VERSIONS[training.algorithm_version]
        kind = _kind(training.hyperparameters, version)
        rows = tuple(sorted(training.rows, key=lambda r: str(r.model_training_sample_id)))
        if (len(training.feature_definition_ids) != 1 or len(rows) < 2
                or len({r.model_training_sample_id for r in rows}) != len(rows)
                or any(len(r.features) != 1 or not all(x.is_finite() for x in (*r.features, r.target)) for r in rows)):
            raise ValueError("baseline requires a finite, unique, single-Feature FIT roster")
        with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
            intercept = (sum((r.target for r in rows), Decimal(0)) / len(rows)).quantize(_QUANTUM) if kind == "TRAINING_MEAN" else Decimal(0)
            if kind == "TRAINING_MEDIAN":
                labels = sorted(row.target for row in rows)
                middle = len(labels) // 2
                intercept = (labels[middle] if len(labels) % 2 else (labels[middle-1] + labels[middle]) / 2).quantize(_QUANTUM)
        artifact = BaselineArtifact(training.feature_definition_ids, kind, intercept,
                                    Decimal(_V2_COEFFICIENTS[kind]),
                                    training.seed, canonical_json_sha256(tuple(
                                        {"model_training_sample_id": r.model_training_sample_id, "features": r.features, "target": r.target} for r in rows)), version)
        content = _bytes(artifact.payload())
        if load_baseline_artifact(content) != artifact:
            raise ValueError("baseline Artifact round trip differs")
        for row in rows:
            _point(artifact, row.features[0])
        return FittedModelPayload(content, sha256_bytes(content), 2)


class ResearchBaselinePredictor:
    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return ResearchBaselineTrainer().supports(algorithm_code, algorithm_version)

    def predict(self, model: FrozenModelVersionPayload, batch: ModelPredictionBatch) -> tuple[ModelPrediction, ...]:
        if not self.supports(model.algorithm_code, model.algorithm_version):
            raise ValueError("baseline adapter cannot execute this algorithm")
        artifact = load_baseline_artifact(model.fitted_content)
        if (sha256_bytes(model.fitted_content) != str(model.fitted_content_sha256)
                or artifact.format_version != _VERSIONS[model.algorithm_version]
                or artifact.kind != _kind(model.hyperparameters, artifact.format_version) or artifact.seed != model.seed
                or artifact.feature_definition_ids != model.feature_definition_ids or model.coefficient_count != 2):
            raise ValueError("baseline Artifact differs from frozen ModelVersion")
        if any(len(row.features) != 1 or not row.features[0].is_finite() for row in batch.rows):
            raise ValueError("baseline prediction requires one finite Feature")
        return tuple(ModelPrediction(row.row_id, _point(artifact, row.features[0])) for row in batch.rows)


def _point(artifact: BaselineArtifact, feature: Decimal) -> Decimal:
    try:
        with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
            value = (artifact.intercept + artifact.coefficient * feature).quantize(_QUANTUM)
            if not value.is_finite():
                raise ValueError("baseline prediction must be finite")
            return value
    except DecimalException as exc:
        raise ValueError("baseline prediction exceeds supported output precision") from exc


class ResearchBaselineBacktestAdapter:
    def supports(self, recipe: BacktestModelTrainingRecipe) -> bool:
        return ResearchBaselineTrainer().supports(recipe.algorithm_code, recipe.algorithm_version)

    def training_request(self, *, specification: BacktestSpecification,
                         requirement: BacktestModelTrainingRequirement,
                         fit_evaluation: BacktestFitEvaluationExecution,
                         model_training_run_id: UUID) -> ReproducibleModelTrainingRunRequest:
        recipe = requirement.recipe
        if recipe is None or not self.supports(recipe) or requirement.training_metric is None:
            raise ValueError("baseline Backtest requires a supported recipe and FIT metric")
        return ReproducibleModelTrainingRunRequest(
            OpenModelTrainingRunRequest(model_training_run_id, requirement.model_definition.authority_id,
                fit_evaluation.evaluation_run_id, requirement.training_metric.authority_id,
                specification.exploratory_backtest_run_id, requirement.model_arm_id, requirement.fit_fold_id,
                recipe.algorithm_code, recipe.algorithm_version, recipe.implementation_sha256, None,
                specification.random_seed, specification.code_artifact, specification.config_artifact, specification.provenance_sha256),
            recipe.environment, recipe.hyperparameters)
