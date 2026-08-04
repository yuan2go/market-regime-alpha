"""Deterministic, policy-driven differential execution and classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.features.model_contracts import FeatureArtifact, FeatureComputer
from market_regime_alpha.migration.comparison.contracts import (
    CanonicalInvariant,
    ComparisonObservation,
    ComparisonPolicy,
    DifferenceClassification,
    FieldDifference,
    ModelComparisonOutput,
    ModelComparisonReport,
    NumericDifference,
    SemanticDifference,
    bind_model_comparison_report,
)
from market_regime_alpha.migration.legacy.normalization.market_data import (
    LegacyFeatureResult,
    LegacyFeatureResultState,
    NormalizedFeatureDataset,
)


class LegacyFeatureAdapter(Protocol):
    legacy_model_id: ModelId
    legacy_model_version: str

    def compute(self, dataset: object) -> LegacyFeatureResult: ...


@dataclass(frozen=True, slots=True)
class _ComparisonFacts:
    fields: tuple[FieldDifference, ...]
    numbers: tuple[NumericDifference, ...]

    @property
    def difference_paths(self) -> frozenset[str]:
        return frozenset(
            (*[item.path for item in self.fields], *[item.path for item in self.numbers])
        )


class DifferentialTestHarness:
    """Run both implementations over one exact dataset and classify evidence."""

    def compare(
        self,
        *,
        dataset: NormalizedFeatureDataset,
        legacy_adapter: LegacyFeatureAdapter,
        canonical_model: FeatureComputer,
        policy: ComparisonPolicy,
        created_at: datetime,
    ) -> ModelComparisonReport:
        if not isinstance(dataset, NormalizedFeatureDataset):
            raise TypeError("dataset must be a NormalizedFeatureDataset")
        if not isinstance(policy, ComparisonPolicy):
            raise TypeError("policy must be a ComparisonPolicy")

        legacy_result = legacy_adapter.compute(dataset)
        legacy_output = _legacy_output(legacy_result)
        canonical_output = _run_canonical(
            model=canonical_model,
            dataset=dataset,
            created_at=created_at,
        )
        facts = _compare_outputs(
            legacy=legacy_output,
            canonical=canonical_output,
            policy=policy,
        )
        classification, semantic, expected, unexpected = _classify(
            legacy=legacy_output,
            canonical=canonical_output,
            facts=facts,
            policy=policy,
        )
        unbound = ModelComparisonReport(
            comparison_id=ArtifactId("model-comparison-unbound"),
            report_hash="sha256:" + "0" * 64,
            policy_id=policy.policy_id,
            policy_hash=policy.policy_hash,
            legacy_model_id=legacy_output.model_id,
            legacy_model_version=legacy_output.model_version,
            canonical_model_id=canonical_output.model_id,
            canonical_model_version=canonical_output.model_version,
            dataset_id=dataset.dataset_id,
            as_of_time=dataset.as_of_time,
            input_hash=dataset.content_hash,
            legacy_output=legacy_output,
            canonical_output=canonical_output,
            field_differences=facts.fields,
            numeric_differences=facts.numbers,
            semantic_differences=semantic,
            difference_classification=classification,
            expected_difference=expected,
            unexpected_difference=unexpected,
            created_at=created_at,
        )
        return bind_model_comparison_report(unbound)


def _legacy_output(result: LegacyFeatureResult) -> ModelComparisonOutput:
    if not isinstance(result, LegacyFeatureResult):
        raise TypeError("Legacy adapter must return LegacyFeatureResult")
    return ModelComparisonOutput(
        model_id=result.model_id,
        model_version=result.model_version,
        state=result.state.value,
        score=result.score,
        observations=tuple(
            ComparisonObservation(
                key=item.key,
                value=item.value,
                missing_reason=item.missing_reason,
            )
            for item in result.observations
        ),
        reason_codes=result.reason_codes,
        limitations=result.limitations,
        exception_type=result.exception_type,
        exception_message=result.exception_message,
    )


def _run_canonical(
    *,
    model: FeatureComputer,
    dataset: NormalizedFeatureDataset,
    created_at: datetime,
) -> ModelComparisonOutput:
    model_id = getattr(model, "model_id", ModelId(str(model.feature_id)))
    if not isinstance(model_id, ModelId):
        raise TypeError("canonical model_id must be a ModelId")
    try:
        artifact = model.compute(dataset.to_feature_request(created_at=created_at))
        return _canonical_output(artifact)
    except Exception as exc:
        return ModelComparisonOutput(
            model_id=model_id,
            model_version=model.model_version,
            state="COMPUTATION_FAILED",
            score=None,
            observations=(),
            reason_codes=("CANONICAL_COMPUTATION_FAILED",),
            limitations=("NO_TRADING_AUTHORITY", "RESEARCH_ONLY"),
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )


def _canonical_output(artifact: FeatureArtifact) -> ModelComparisonOutput:
    observations: list[ComparisonObservation] = []
    for item in artifact.observations:
        market_date = getattr(item, "market_date", None)
        value = getattr(item, "value", None)
        missing_reason = getattr(item, "missing_reason", None)
        if market_date is None or not hasattr(market_date, "isoformat"):
            raise TypeError("canonical observation lacks market_date")
        if value is not None and not isinstance(value, Decimal):
            raise TypeError("canonical observation value must be Decimal or None")
        if missing_reason is not None and not isinstance(missing_reason, str):
            raise TypeError("canonical observation missing_reason must be text or None")
        observations.append(
            ComparisonObservation(
                key=str(market_date.isoformat()),
                value=value,
                missing_reason=missing_reason,
            )
        )
    return ModelComparisonOutput(
        model_id=artifact.model_id,
        model_version=artifact.model_version,
        state=artifact.state,
        score=artifact.score,
        observations=tuple(observations),
        reason_codes=artifact.reason_codes,
        limitations=artifact.limitations,
    )


def _compare_outputs(
    *,
    legacy: ModelComparisonOutput,
    canonical: ModelComparisonOutput,
    policy: ComparisonPolicy,
) -> _ComparisonFacts:
    fields: list[FieldDifference] = []
    numbers: list[NumericDifference] = []
    tolerance_by_path = {
        item.path: item.absolute_tolerance for item in policy.numeric_tolerances
    }

    _compare_scalar("state", legacy.state, canonical.state, fields, numbers, tolerance_by_path)
    _compare_scalar("score", legacy.score, canonical.score, fields, numbers, tolerance_by_path)
    legacy_by_key = {item.key: item for item in legacy.observations}
    canonical_by_key = {item.key: item for item in canonical.observations}
    for key in sorted(set(legacy_by_key) | set(canonical_by_key)):
        legacy_item = legacy_by_key.get(key)
        canonical_item = canonical_by_key.get(key)
        if legacy_item is None or canonical_item is None:
            fields.append(
                FieldDifference(
                    path=f"observations[{key}]",
                    legacy_value="PRESENT" if legacy_item is not None else None,
                    canonical_value="PRESENT" if canonical_item is not None else None,
                )
            )
            continue
        _compare_scalar(
            f"observations[{key}].value",
            legacy_item.value,
            canonical_item.value,
            fields,
            numbers,
            tolerance_by_path,
        )
        _compare_scalar(
            f"observations[{key}].missing_reason",
            legacy_item.missing_reason,
            canonical_item.missing_reason,
            fields,
            numbers,
            tolerance_by_path,
        )
    return _ComparisonFacts(
        fields=tuple(sorted(fields, key=lambda item: item.path)),
        numbers=tuple(sorted(numbers, key=lambda item: item.path)),
    )


def _compare_scalar(
    path: str,
    legacy: str | Decimal | None,
    canonical: str | Decimal | None,
    fields: list[FieldDifference],
    numbers: list[NumericDifference],
    tolerance_by_path: dict[str, Decimal],
) -> None:
    if isinstance(legacy, Decimal) and isinstance(canonical, Decimal):
        if legacy == canonical:
            return
        absolute = abs(legacy - canonical)
        tolerance = tolerance_by_path.get(path)
        numbers.append(
            NumericDifference(
                path=path,
                legacy_value=legacy,
                canonical_value=canonical,
                absolute_difference=absolute,
                tolerance=tolerance,
                within_tolerance=tolerance is not None and absolute <= tolerance,
            )
        )
        return
    if legacy != canonical:
        fields.append(
            FieldDifference(
                path=path,
                legacy_value=_scalar_text(legacy),
                canonical_value=_scalar_text(canonical),
            )
        )


def _classify(
    *,
    legacy: ModelComparisonOutput,
    canonical: ModelComparisonOutput,
    facts: _ComparisonFacts,
    policy: ComparisonPolicy,
) -> tuple[
    DifferenceClassification,
    tuple[SemanticDifference, ...],
    bool,
    bool,
]:
    if (
        legacy.exception_type is not None
        or legacy.state == LegacyFeatureResultState.DATA_INSUFFICIENT.value
    ):
        expected = bool(legacy.reason_codes) and set(legacy.reason_codes).issubset(
            policy.expected_insufficient_reason_codes
        )
        return DifferenceClassification.INSUFFICIENT_DATA, (), expected, not expected

    if legacy.state == LegacyFeatureResultState.NOT_COMPARABLE.value:
        expected = bool(legacy.reason_codes) and set(legacy.reason_codes).issubset(
            policy.expected_not_comparable_reason_codes
        )
        return DifferenceClassification.NOT_COMPARABLE, (), expected, not expected

    invariant_failures = tuple(
        _invariant_failure(item, canonical)
        for item in policy.canonical_invariants
        if _output_value(canonical, item.path) != item.independently_expected_value
    )
    if invariant_failures:
        return (
            DifferenceClassification.CANONICAL_REGRESSION,
            tuple(sorted(invariant_failures, key=lambda item: (item.path, item.rule_id))),
            False,
            True,
        )

    if facts.difference_paths.intersection(policy.exact_fields):
        return DifferenceClassification.NOT_COMPARABLE, (), False, True

    if not facts.fields and not facts.numbers:
        return DifferenceClassification.EXACT_MATCH, (), False, False

    defect_semantic = _matched_defects(legacy, canonical, policy)
    if defect_semantic and facts.difference_paths == frozenset(
        item.path for item in defect_semantic
    ):
        return (
            DifferenceClassification.LEGACY_DEFECT_FIXED,
            defect_semantic,
            True,
            False,
        )

    expected_semantic = _matched_semantic_changes(legacy, canonical, policy)
    if expected_semantic and facts.difference_paths == frozenset(
        item.path for item in expected_semantic
    ):
        return (
            DifferenceClassification.EXPECTED_SEMANTIC_CHANGE,
            expected_semantic,
            True,
            False,
        )

    if not facts.fields and facts.numbers and all(
        item.within_tolerance for item in facts.numbers
    ):
        return DifferenceClassification.NUMERIC_TOLERANCE, (), True, False

    return DifferenceClassification.NOT_COMPARABLE, (), False, True


def _invariant_failure(
    invariant: CanonicalInvariant,
    canonical: ModelComparisonOutput,
) -> SemanticDifference:
    return SemanticDifference(
        rule_id=invariant.invariant_id,
        difference_kind="CANONICAL_INVARIANT_VIOLATION",
        path=invariant.path,
        legacy_value=invariant.independently_expected_value,
        canonical_value=_output_value(canonical, invariant.path),
    )


def _matched_defects(
    legacy: ModelComparisonOutput,
    canonical: ModelComparisonOutput,
    policy: ComparisonPolicy,
) -> tuple[SemanticDifference, ...]:
    matches = []
    for rule in policy.legacy_defect_expectations:
        legacy_value = _output_value(legacy, rule.path)
        canonical_value = _output_value(canonical, rule.path)
        if (
            legacy_value == rule.legacy_value
            and canonical_value == rule.independently_expected_canonical_value
            and legacy_value != canonical_value
        ):
            matches.append(
                SemanticDifference(
                    rule_id=rule.defect_id,
                    difference_kind="LEGACY_DEFECT_FIXED",
                    path=rule.path,
                    legacy_value=legacy_value,
                    canonical_value=canonical_value,
                )
            )
    return tuple(sorted(matches, key=lambda item: (item.path, item.rule_id)))


def _matched_semantic_changes(
    legacy: ModelComparisonOutput,
    canonical: ModelComparisonOutput,
    policy: ComparisonPolicy,
) -> tuple[SemanticDifference, ...]:
    matches = []
    for rule in policy.expected_semantic_changes:
        legacy_value = _output_value(legacy, rule.path)
        canonical_value = _output_value(canonical, rule.path)
        if legacy_value == rule.legacy_value and canonical_value == rule.canonical_value:
            matches.append(
                SemanticDifference(
                    rule_id=rule.rule_id,
                    difference_kind="EXPECTED_SEMANTIC_CHANGE",
                    path=rule.path,
                    legacy_value=legacy_value,
                    canonical_value=canonical_value,
                )
            )
    return tuple(sorted(matches, key=lambda item: (item.path, item.rule_id)))


def _output_value(output: ModelComparisonOutput, path: str) -> str | None:
    if path == "state":
        return output.state
    if path == "score":
        return _scalar_text(output.score)
    if path == "exception_type":
        return output.exception_type
    if path == "exception_message":
        return output.exception_message
    if path.startswith("observations[") and "]." in path:
        key, field = path[len("observations[") :].split("].", 1)
        observation = next((item for item in output.observations if item.key == key), None)
        if observation is None:
            return None
        if field == "value":
            return _scalar_text(observation.value)
        if field == "missing_reason":
            return observation.missing_reason
    raise ValueError(f"unsupported comparison path: {path}")


def _scalar_text(value: str | Decimal | None) -> str | None:
    return str(value) if value is not None else None


__all__ = ["DifferentialTestHarness", "LegacyFeatureAdapter"]
