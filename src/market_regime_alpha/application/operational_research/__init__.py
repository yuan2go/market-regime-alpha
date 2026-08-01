"""Operational bridge from verified DailyLoop evidence to Platform V2 research."""

from market_regime_alpha.application.operational_research.bridge import (
    OperationalResearchRunner,
    adapt_operational_research_inputs,
)
from market_regime_alpha.application.operational_research.contracts import (
    SupplementalResearchEvidenceBundle,
)

__all__ = [
    "OperationalResearchRunner",
    "SupplementalResearchEvidenceBundle",
    "adapt_operational_research_inputs",
]
