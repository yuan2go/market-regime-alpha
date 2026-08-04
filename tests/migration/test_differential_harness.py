from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.features.technical.moving_average import (
    SimpleMovingAverageComputer,
)
from market_regime_alpha.migration.comparison.contracts import (
    CanonicalInvariant,
    ComparisonPolicy,
    DifferenceClassification,
    ExpectedSemanticChange,
    LegacyDefectExpectation,
    NumericTolerance,
)
from market_regime_alpha.migration.comparison.harness import DifferentialTestHarness
from market_regime_alpha.migration.legacy.adapters.moving_average import (
    LegacyMovingAverageAdapter,
)
from market_regime_alpha.migration.legacy.normalization.market_data import (
    LegacyFeatureResult,
    LegacyFeatureResultState,
)

from .test_legacy_moving_average_adapter import dataset


CREATED_AT = datetime(2026, 8, 4, 7, 1, tzinfo=timezone.utc)


def policy(**kwargs: object) -> ComparisonPolicy:
    return ComparisonPolicy.create(policy_version="1.0.0", **kwargs)


def test_exact_match_classification() -> None:
    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=LegacyMovingAverageAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=policy(),
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.EXACT_MATCH
    assert report.field_differences == ()
    assert report.numeric_differences == ()
    assert report.expected_difference is False
    assert report.unexpected_difference is False


def test_field_specific_numeric_tolerance_is_explicit() -> None:
    class NearLegacyAdapter(LegacyMovingAverageAdapter):
        def compute(self, request: object) -> LegacyFeatureResult:
            original = super().compute(request)
            final = original.observations[-1]
            changed = replace(final, value=final.value + Decimal("0.0001"))
            return replace(
                original,
                score=original.score + Decimal("0.0001"),
                observations=(*original.observations[:-1], changed),
            )

    comparison_policy = policy(
        numeric_tolerances=(
            NumericTolerance(path="score", absolute_tolerance=Decimal("0.0001")),
            NumericTolerance(
                path="observations[2026-08-03].value",
                absolute_tolerance=Decimal("0.0001"),
            ),
        )
    )
    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=NearLegacyAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=comparison_policy,
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.NUMERIC_TOLERANCE
    assert len(report.numeric_differences) == 2
    assert all(item.within_tolerance for item in report.numeric_differences)
    assert report.expected_difference is True
    assert report.unexpected_difference is False


def test_expected_semantic_change_requires_an_exact_policy_rule() -> None:
    class DifferentMissingReasonAdapter(LegacyMovingAverageAdapter):
        def compute(self, request: object) -> LegacyFeatureResult:
            original = super().compute(request)
            first = replace(original.observations[0], missing_reason="LEGACY_WARMUP")
            return replace(original, observations=(first, *original.observations[1:]))

    path = "observations[2026-07-30].missing_reason"
    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=DifferentMissingReasonAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=policy(
            expected_semantic_changes=(
                ExpectedSemanticChange(
                    rule_id="MA-WARMUP-NORMALIZATION",
                    path=path,
                    legacy_value="LEGACY_WARMUP",
                    canonical_value="WINDOW_NOT_READY",
                ),
            )
        ),
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.EXPECTED_SEMANTIC_CHANGE
    assert report.semantic_differences[0].rule_id == "MA-WARMUP-NORMALIZATION"
    assert report.expected_difference is True
    assert report.unexpected_difference is False


def test_legacy_defect_fixed_requires_defect_id_and_independent_expected_value() -> None:
    class DefectiveLegacyAdapter(LegacyMovingAverageAdapter):
        def compute(self, request: object) -> LegacyFeatureResult:
            original = super().compute(request)
            changed = replace(original.observations[-1], value=Decimal("99"))
            return replace(
                original,
                score=Decimal("99"),
                observations=(*original.observations[:-1], changed),
            )

    comparison_policy = policy(
        legacy_defect_expectations=(
            LegacyDefectExpectation(
                defect_id="LEGACY-MA-001",
                path="score",
                legacy_value="99",
                independently_expected_canonical_value="12",
            ),
            LegacyDefectExpectation(
                defect_id="LEGACY-MA-001",
                path="observations[2026-08-03].value",
                legacy_value="99",
                independently_expected_canonical_value="12",
            ),
        )
    )
    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=DefectiveLegacyAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=comparison_policy,
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.LEGACY_DEFECT_FIXED
    assert {item.rule_id for item in report.semantic_differences} == {"LEGACY-MA-001"}

    with pytest.raises(ValueError, match="defect_id"):
        LegacyDefectExpectation(
            defect_id="",
            path="score",
            legacy_value="99",
            independently_expected_canonical_value="12",
        )


def test_canonical_regression_requires_an_independent_invariant() -> None:
    class BrokenCanonical(SimpleMovingAverageComputer):
        def compute(self, request: object) -> object:
            return replace(super().compute(request), score=Decimal("13"))

    without_oracle = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=LegacyMovingAverageAdapter(),
        canonical_model=BrokenCanonical(),
        policy=policy(),
        created_at=CREATED_AT,
    )
    assert without_oracle.difference_classification is DifferenceClassification.NOT_COMPARABLE

    with_oracle = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=LegacyMovingAverageAdapter(),
        canonical_model=BrokenCanonical(),
        policy=policy(
            canonical_invariants=(
                CanonicalInvariant(
                    invariant_id="INDEPENDENT-MA-ORACLE",
                    path="score",
                    independently_expected_value="12",
                ),
            )
        ),
        created_at=CREATED_AT,
    )
    assert with_oracle.difference_classification is DifferenceClassification.CANONICAL_REGRESSION
    assert with_oracle.unexpected_difference is True


def test_legacy_exception_is_insufficient_data() -> None:
    class FailingLegacyAdapter(LegacyMovingAverageAdapter):
        def compute(self, request: object) -> LegacyFeatureResult:
            return LegacyFeatureResult.failed(
                model_id=self.legacy_model_id,
                model_version=self.legacy_model_version,
                exception=ArithmeticError("failed"),
            )

    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=FailingLegacyAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=policy(),
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.INSUFFICIENT_DATA
    assert report.legacy_output.state == LegacyFeatureResultState.COMPUTATION_FAILED.value


def test_unsupported_legacy_window_is_not_comparable() -> None:
    report = DifferentialTestHarness().compare(
        dataset=dataset(window=3),
        legacy_adapter=LegacyMovingAverageAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=policy(expected_not_comparable_reason_codes=("LEGACY_WINDOW_NOT_SUPPORTED",)),
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.NOT_COMPARABLE
    assert report.expected_difference is True
    assert report.unexpected_difference is False


def test_policy_rejects_global_or_wildcard_tolerance() -> None:
    with pytest.raises(ValueError, match="field-specific"):
        NumericTolerance(path="*", absolute_tolerance=Decimal("1"))
    with pytest.raises(ValueError, match="finite and non-negative"):
        NumericTolerance(path="score", absolute_tolerance=Decimal("NaN"))


def test_exact_field_mismatch_is_unexpected_and_cannot_be_tolerated() -> None:
    class NearLegacyAdapter(LegacyMovingAverageAdapter):
        def compute(self, request: object) -> LegacyFeatureResult:
            original = super().compute(request)
            changed = replace(original.observations[-1], value=Decimal("12.0001"))
            return replace(
                original,
                score=Decimal("12.0001"),
                observations=(*original.observations[:-1], changed),
            )

    report = DifferentialTestHarness().compare(
        dataset=dataset(),
        legacy_adapter=NearLegacyAdapter(),
        canonical_model=SimpleMovingAverageComputer(),
        policy=policy(exact_fields=("score",)),
        created_at=CREATED_AT,
    )

    assert report.difference_classification is DifferenceClassification.NOT_COMPARABLE
    assert report.expected_difference is False
    assert report.unexpected_difference is True

    with pytest.raises(ValueError, match="exact_fields cannot overlap"):
        policy(
            exact_fields=("score",),
            numeric_tolerances=(
                NumericTolerance(
                    path="score", absolute_tolerance=Decimal("0.001")
                ),
            ),
        )


def test_exact_field_cannot_be_declared_an_expected_semantic_or_defect_change() -> None:
    with pytest.raises(ValueError, match="exact_fields cannot overlap"):
        policy(
            exact_fields=("state",),
            expected_semantic_changes=(
                ExpectedSemanticChange(
                    rule_id="STATE-CHANGE",
                    path="state",
                    legacy_value="LEGACY_STATE",
                    canonical_value="AVAILABLE",
                ),
            ),
        )

    with pytest.raises(ValueError, match="exact_fields cannot overlap"):
        policy(
            exact_fields=("score",),
            legacy_defect_expectations=(
                LegacyDefectExpectation(
                    defect_id="LEGACY-MA-EXACT",
                    path="score",
                    legacy_value="99",
                    independently_expected_canonical_value="12",
                ),
            ),
        )


def test_exact_field_may_overlap_an_independent_canonical_invariant() -> None:
    comparison_policy = policy(
        exact_fields=("score",),
        canonical_invariants=(
            CanonicalInvariant(
                invariant_id="INDEPENDENT-SCORE-ORACLE",
                path="score",
                independently_expected_value="12",
            ),
        ),
    )

    assert comparison_policy.exact_fields == ("score",)


def test_semantic_report_hash_excludes_only_created_at() -> None:
    harness = DifferentialTestHarness()
    kwargs = {
        "dataset": dataset(),
        "legacy_adapter": LegacyMovingAverageAdapter(),
        "canonical_model": SimpleMovingAverageComputer(),
        "policy": policy(),
    }
    first = harness.compare(created_at=CREATED_AT, **kwargs)
    second = harness.compare(
        created_at=datetime(2026, 8, 4, 8, 1, tzinfo=timezone.utc), **kwargs
    )

    assert first.report_hash == second.report_hash
    assert first.comparison_id == second.comparison_id
    assert first.created_at != second.created_at
    assert first.to_canonical_dict() != second.to_canonical_dict()
