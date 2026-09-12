"""An intercept input is one for an evidenced instrument, independent of prices.

Unit: dimensionless; window: current decision; warmup: zero. The source is the
exact visible archived listing fact. Missing/ambiguous identity fails closed.
This is a control input, not a new predictive economic factor.
"""

from hashlib import sha256
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding, FeatureDefinition
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureAvailabilityRule, FeatureIntervalUnit, FeatureMissingnessPolicy, FeatureSourceRequirement, FeatureValueType,
)


INTERCEPT_CODE = "research_intercept_v1"
INTERCEPT_SHA256 = sha256(b"research_intercept_v1:1:dimensionless:exact_archived_listing_fact:zero_warmup:no_price_dependency").hexdigest()


def intercept_feature_definition(identity: UUID, code: ArtifactBinding, config: ArtifactBinding) -> FeatureDefinition:
    return FeatureDefinition(identity, INTERCEPT_CODE, 1, FeatureValueType.DECIMAL, "RATIO",
        1, FeatureIntervalUnit.TRADING_SESSION, 1, FeatureIntervalUnit.TRADING_SESSION, 0, FeatureIntervalUnit.TRADING_SESSION,
        (FeatureSourceRequirement.INSTRUMENT_FACT_REVISION, FeatureSourceRequirement.TRADING_SESSION),
        FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE, FeatureMissingnessPolicy.EXPLICIT_STATUS,
        INTERCEPT_CODE, "1", INTERCEPT_SHA256, code, config)
