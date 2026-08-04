"""Content-addressed Legacy/canonical differential verification."""

from market_regime_alpha.migration.comparison.contracts import (
    ComparisonPolicy,
    DifferenceClassification,
    ModelComparisonReport,
)
from market_regime_alpha.migration.comparison.harness import DifferentialTestHarness

__all__ = [
    "ComparisonPolicy",
    "DifferenceClassification",
    "DifferentialTestHarness",
    "ModelComparisonReport",
]
