from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.migration.comparison.contracts import (
    DifferenceClassification,
)
from market_regime_alpha.migration.comparison.technical_observables import (
    canonical_technical_comparison_policy,
    compare_technical_observables,
    load_verified_technical_comparison,
    publish_technical_comparison,
    replay_technical_comparison,
)
from market_regime_alpha.migration.legacy.adapters.technical_observables import (
    LegacyTechnicalFamily,
)
from tests.features.test_materialization_runner_v2 import _run


def _inputs(tmp_path: Path):
    dataset, _, receipt = _run(tmp_path)
    bundle = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    return dataset, bundle


def test_all_migrated_families_have_independent_policy_and_classification(
    tmp_path: Path,
) -> None:
    dataset, bundle = _inputs(tmp_path)
    policy = canonical_technical_comparison_policy()
    report = compare_technical_observables(
        verified_dataset=dataset,
        feature_bundle=bundle,
        symbol="600000.SH",
        policy=policy,
    )

    by_family = {item.family: item for item in report.items}
    assert set(by_family) == set(LegacyTechnicalFamily)
    assert by_family[LegacyTechnicalFamily.MOVING_AVERAGE].classification in {
        DifferenceClassification.EXACT_MATCH,
        DifferenceClassification.NUMERIC_TOLERANCE,
    }
    assert by_family[LegacyTechnicalFamily.EMA].classification in {
        DifferenceClassification.EXACT_MATCH,
        DifferenceClassification.NUMERIC_TOLERANCE,
    }
    assert by_family[LegacyTechnicalFamily.MACD].classification in {
        DifferenceClassification.EXACT_MATCH,
        DifferenceClassification.NUMERIC_TOLERANCE,
        DifferenceClassification.EXPECTED_SEMANTIC_CHANGE,
    }
    assert (
        by_family[LegacyTechnicalFamily.VOLUME_RATIO].classification
        is DifferenceClassification.EXPECTED_SEMANTIC_CHANGE
    )
    assert (
        by_family[LegacyTechnicalFamily.AMOUNT_STRUCTURE].classification
        is DifferenceClassification.NOT_COMPARABLE
    )
    assert report.unexpected_difference is False
    assert report.canonical_regression is False


def test_comparison_package_round_trip_tamper_and_full_replay(tmp_path: Path) -> None:
    dataset, bundle = _inputs(tmp_path)
    policy = canonical_technical_comparison_policy()
    report = compare_technical_observables(
        verified_dataset=dataset,
        feature_bundle=bundle,
        symbol="600000.SH",
        policy=policy,
    )
    package = publish_technical_comparison(
        root=tmp_path / "comparisons", report=report, policy=policy
    )

    assert load_verified_technical_comparison(package).report == report
    assert replay_technical_comparison(
        package,
        verified_dataset=dataset,
        feature_bundle=bundle,
    ).report == report

    artifact_path = package / "artifact.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["symbol"] = "000001.SZ"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_technical_comparison(package)


def test_policy_is_content_addressed_and_family_specific() -> None:
    policy = canonical_technical_comparison_policy()
    restored = type(policy).from_canonical_dict(policy.to_canonical_dict())

    assert restored == policy
    assert len(policy.family_policies) == len(LegacyTechnicalFamily)
    assert len({item.numeric_tolerance for item in policy.family_policies}) > 1
