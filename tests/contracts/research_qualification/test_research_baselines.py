from dataclasses import replace
from decimal import Decimal as D, localcontext, ROUND_UP
from uuid import UUID

import pytest

from market_regime_alpha.infrastructure.models.research_baselines import (
    ResearchBaselinePredictor, ResearchBaselineTrainer, load_baseline_artifact,
)
from market_regime_alpha.research_qualification.domain.research_models import LinearTrainingRow
from market_regime_alpha.research_qualification.ports.model_execution import (
    FrozenModelTrainingInput, FrozenModelVersionPayload, ModelPredictionBatch, ModelPredictionRow,
    ModelScalarParameter, ModelScalarType,
)


def training(kind):
    return FrozenModelTrainingInput("research_baseline", "1.0.0", "a" * 64, (UUID(int=1),),
        (ModelScalarParameter("baseline_kind", ModelScalarType.TEXT, text_value=kind),), 18,
        tuple(LinearTrainingRow(UUID(int=i), (D(x),), D(y)) for i, x, y in ((10, "0.1", "-0.2"), (11, "0.2", "0.4"), (12, "-0.3", "0.1"))))


@pytest.mark.parametrize("kind, expected", [
    ("ZERO", (D(0), D(0))), ("TRAINING_MEAN", (D(".1"), D(".1"))),
    ("FEATURE", (D(".032"), D("-.014"))), ("INVERSE_FEATURE", (D("-.032"), D(".014"))),
])
def test_controls_use_only_frozen_fit_and_preserve_raw_factor_units(kind, expected):
    t = training(kind)
    fitted = ResearchBaselineTrainer().fit(t)
    assert ResearchBaselineTrainer().fit(replace(t, rows=tuple(reversed(t.rows)))) == fitted
    model = FrozenModelVersionPayload(t.algorithm_code, t.algorithm_version, t.implementation_sha256,
        fitted.content, fitted.content_sha256, t.feature_definition_ids, t.hyperparameters, t.seed, fitted.coefficient_count)
    batch = ModelPredictionBatch((ModelPredictionRow(UUID(int=21), (D(".032"),)), ModelPredictionRow(UUID(int=22), (D("-.014"),))))
    assert tuple(x.point_estimate for x in ResearchBaselinePredictor().predict(model, batch)) == expected
    assert load_baseline_artifact(fitted.content).feature_definition_ids == t.feature_definition_ids
    with pytest.raises(ValueError, match="differs from frozen"):
        ResearchBaselinePredictor().predict(replace(model, seed=19), batch)
    with pytest.raises(ValueError, match="differs from frozen"):
        ResearchBaselinePredictor().predict(replace(model, fitted_content_sha256="b" * 64), batch)
    with pytest.raises(ValueError, match="one finite Feature"):
        ResearchBaselinePredictor().predict(model, ModelPredictionBatch((ModelPredictionRow(UUID(int=23), (D("NaN"),)),)))


def test_mean_has_frozen_training_roster_and_changes_only_when_training_labels_change():
    t = training("TRAINING_MEAN")
    changed = replace(t, rows=(replace(t.rows[0], target=D(".7")), *t.rows[1:]))
    a = load_baseline_artifact(ResearchBaselineTrainer().fit(t).content)
    b = load_baseline_artifact(ResearchBaselineTrainer().fit(changed).content)
    assert (a.intercept, b.intercept) == (D(".1"), D(".4"))
    assert a.sample_roster_sha256 != b.sample_roster_sha256


def test_controls_reject_ambiguous_artifact_and_bad_training():
    t = training("FEATURE")
    content = ResearchBaselineTrainer().fit(t).content
    with pytest.raises(ValueError, match="canonical"):
        load_baseline_artifact(content.replace(b'"seed":18', b'"seed":18,"seed":18'))
    with pytest.raises(ValueError, match="formula"):
        load_baseline_artifact(content.replace(b'"coefficient":"1"', b'"coefficient":"0"'))
    for rows in ((t.rows[0],), (t.rows[0], t.rows[0]), (t.rows[0], replace(t.rows[1], target=D("Infinity")))):
        with pytest.raises(ValueError, match="FIT roster"):
            ResearchBaselineTrainer().fit(replace(t, rows=rows))
    with pytest.raises(ValueError, match="baseline_kind"):
        ResearchBaselineTrainer().fit(replace(t, hyperparameters=()))


def test_baseline_rounding_is_independent_of_caller_decimal_context():
    original = training("TRAINING_MEAN")
    t = replace(original, rows=tuple(replace(row, target=value) for row, value in zip(original.rows, (D(0), D(0), D(1)), strict=True)))
    expected = ResearchBaselineTrainer().fit(t)
    with localcontext() as context:
        context.rounding = ROUND_UP
        assert ResearchBaselineTrainer().fit(t) == expected


def test_fit_rejects_values_that_cannot_round_trip_through_prediction_precision():
    t = training("FEATURE")
    t = replace(t, rows=(replace(t.rows[0], features=(D("1e100"),)), *t.rows[1:]))
    with pytest.raises(ValueError, match="output precision"):
        ResearchBaselineTrainer().fit(t)


@pytest.mark.parametrize("labels,expected", [
    ((".01", ".02", ".30"), D(".02")),
    ((".01", ".02", ".03", "1"), D(".025")),
    (("-.03", "-.03", ".5"), D("-.03")),
])
def test_versioned_fit_median_round_trip_uses_only_training_labels(labels, expected):
    t = replace(training("TRAINING_MEDIAN"), algorithm_version="2.0.0", rows=tuple(
        LinearTrainingRow(UUID(int=n+10), (D(1),), D(label)) for n, label in enumerate(labels)))
    fitted = ResearchBaselineTrainer().fit(t)
    artifact = load_baseline_artifact(fitted.content)
    assert artifact.intercept == expected and artifact.format_version == 2
    assert ResearchBaselineTrainer().fit(replace(t, rows=tuple(reversed(t.rows)))) == fitted
    model = FrozenModelVersionPayload(t.algorithm_code, t.algorithm_version, t.implementation_sha256,
        fitted.content, fitted.content_sha256, t.feature_definition_ids, t.hyperparameters, t.seed, fitted.coefficient_count)
    batch = ModelPredictionBatch((ModelPredictionRow(UUID(int=21), (D(1),)),))
    assert ResearchBaselinePredictor().predict(model, batch)[0].point_estimate == expected
    with pytest.raises(ValueError, match="baseline_kind"):
        ResearchBaselineTrainer().fit(replace(t, algorithm_version="1.0.0"))
    with pytest.raises(ValueError, match="schema or kind"):
        load_baseline_artifact(fitted.content.replace(b"mra-research-baseline-v2", b"mra-research-baseline-v1"))
    with pytest.raises(ValueError, match="differs from frozen"):
        ResearchBaselinePredictor().predict(replace(model, algorithm_version="1.0.0"), batch)
