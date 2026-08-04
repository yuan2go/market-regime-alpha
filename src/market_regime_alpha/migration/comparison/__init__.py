"""Content-addressed Legacy/canonical differential verification."""

from market_regime_alpha.migration.comparison.contracts import (
    ComparisonPolicy,
    DifferenceClassification,
    ModelComparisonReport,
)
from market_regime_alpha.migration.comparison.harness import DifferentialTestHarness
from market_regime_alpha.migration.comparison.technical_observables import (
    TechnicalObservableComparisonPolicy,
    TechnicalObservableComparisonReport,
    canonical_technical_comparison_policy,
    compare_technical_observables,
    load_verified_technical_comparison,
    publish_technical_comparison,
    replay_technical_comparison,
)

__all__ = [
    "ComparisonPolicy",
    "DifferenceClassification",
    "DifferentialTestHarness",
    "ModelComparisonReport",
    "TechnicalObservableComparisonPolicy",
    "TechnicalObservableComparisonReport",
    "canonical_technical_comparison_policy",
    "compare_technical_observables",
    "load_verified_technical_comparison",
    "publish_technical_comparison",
    "replay_technical_comparison",
]
