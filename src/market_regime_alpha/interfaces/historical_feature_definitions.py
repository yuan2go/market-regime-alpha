"""Exact owner definitions for the bounded daily research factor kernel."""

from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain.historical_features import FACTORS, PEER_FACTOR_CODES
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding, FeatureDefinition
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureAvailabilityRule, FeatureIntervalUnit, FeatureMissingnessPolicy, FeatureSourceRequirement, FeatureValueType,
)


def historical_feature_definitions(identity: UUID, code: ArtifactBinding, config: ArtifactBinding) -> tuple[FeatureDefinition, ...]:
    definitions = []
    for factor in FACTORS:
        sources = {FeatureSourceRequirement.MARKET_BAR_REVISION, FeatureSourceRequirement.TRADING_SESSION}
        if factor.algorithm_code in PEER_FACTOR_CODES:
            sources.update((FeatureSourceRequirement.UNIVERSE_MEMBER, FeatureSourceRequirement.ELIGIBILITY_ASSESSMENT))
        definitions.append(FeatureDefinition(uuid5(identity, factor.name), factor.algorithm_code, 1, FeatureValueType.DECIMAL,
            "RATIO", 1, FeatureIntervalUnit.TRADING_SESSION, factor.lookback + 1, FeatureIntervalUnit.TRADING_SESSION,
            factor.lookback, FeatureIntervalUnit.TRADING_SESSION, tuple(sorted(sources,key=lambda s:s.value)),
            FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE, FeatureMissingnessPolicy.EXPLICIT_STATUS,
            factor.algorithm_code, "1", factor.algorithm_sha256, code, config))
    return tuple(sorted(definitions, key=lambda d:str(d.feature_definition_id)))
