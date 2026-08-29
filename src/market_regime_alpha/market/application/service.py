"""Behavior-preserving Market/PIT command facade."""

from market_regime_alpha.market.application.capture import _CaptureCommands
from market_regime_alpha.market.application.normalization import _NormalizationCommands
from market_regime_alpha.market.application.registration import _RegistrationCommands


class MarketApplication(
    _RegistrationCommands,
    _CaptureCommands,
    _NormalizationCommands,
):
    """Provider and Artifact I/O outside; canonical mutation inside one short UoW."""
