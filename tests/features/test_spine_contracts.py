from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureDefinitionV2,
    FeatureOutputDefinition,
    FeatureParameter,
    FeatureParameterType,
    FeatureSetConfiguration,
    FeatureValidationStatus,
    MissingnessPolicy,
    RequiredFeatureCoveragePolicy,
    TimeframePolicy,
    ValueType,
)
from market_regime_alpha.market_data import Timeframe


EFFECTIVE_FROM = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _definition(
    *,
    feature_id: str = "technical.moving_average.v1",
    timeframes: tuple[Timeframe, ...] = (Timeframe.DAILY,),
) -> FeatureDefinitionV2:
    return FeatureDefinitionV2.create(
        feature_id=feature_id,
        feature_version="1.0.0",
        model_id=ModelId(f"model-{feature_id}"),
        model_version="1.0.0",
        required_fields=("close",),
        supported_timeframes=timeframes,
        minimum_history=60,
        warmup_policy="STRICT_TRAILING_WINDOW",
        missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
        output_schema=(
            FeatureOutputDefinition("sma_5", ValueType.DECIMAL),
            FeatureOutputDefinition("ma_alignment", ValueType.TEXT),
        ),
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=("NOT_EMPIRICALLY_VALIDATED", "RESEARCH_ONLY"),
    )


def _configuration(
    *,
    feature_id: str = "technical.moving_average.v1",
    ema_seed: str = "FIRST_OBSERVATION_RECURSIVE",
) -> FeatureConfiguration:
    return FeatureConfiguration.create(
        configuration_version="1.0.0",
        feature_id=feature_id,
        effective_from=EFFECTIVE_FROM,
        parameters=(
            FeatureParameter(
                name="ema_periods",
                parameter_type=FeatureParameterType.INTEGER_LIST,
                value="5,10,12,20,26,60",
            ),
            FeatureParameter(
                name="ema_seed",
                parameter_type=FeatureParameterType.TEXT,
                value=ema_seed,
            ),
            FeatureParameter(
                name="histogram_multiplier",
                parameter_type=FeatureParameterType.DECIMAL,
                value="2",
            ),
        ),
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
    )


def test_definition_configuration_and_set_are_content_addressed() -> None:
    definition = _definition()
    configuration = _configuration()
    feature_set = FeatureSetConfiguration.create(
        feature_set_version="1.0.0",
        definitions=(definition,),
        configurations=(configuration,),
        required_feature_ids=(definition.feature_id,),
        optional_feature_ids=(),
        timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
        coverage_policy=RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING,
        minimum_required_coverage=Decimal("1"),
        missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=("NOT_EMPIRICALLY_VALIDATED", "RESEARCH_ONLY"),
    )

    assert FeatureDefinitionV2.from_canonical_dict(
        definition.to_canonical_dict()
    ) == definition
    assert FeatureConfiguration.from_canonical_dict(
        configuration.to_canonical_dict()
    ) == configuration
    assert FeatureSetConfiguration.from_canonical_dict(
        feature_set.to_canonical_dict()
    ) == feature_set
    assert str(feature_set.feature_set_id).startswith("feature-set-")


def test_parameter_types_are_strict_and_canonical() -> None:
    with pytest.raises(ValueError, match="canonical integer"):
        FeatureParameter("window", FeatureParameterType.INTEGER, "05")
    with pytest.raises(ValueError, match="canonical decimal"):
        FeatureParameter("threshold", FeatureParameterType.DECIMAL, "2.0")
    with pytest.raises(ValueError, match="strict boolean"):
        FeatureParameter("enabled", FeatureParameterType.BOOLEAN, "yes")
    with pytest.raises(ValueError, match="integer list"):
        FeatureParameter("periods", FeatureParameterType.INTEGER_LIST, "5,5")


def test_configuration_change_changes_identity() -> None:
    first = _configuration()
    second = _configuration(ema_seed="SMA_SEED")

    assert first.configuration_id != second.configuration_id
    assert first.configuration_hash != second.configuration_hash


def test_feature_set_rejects_missing_extra_and_duplicate_configuration() -> None:
    definition = _definition()
    configuration = _configuration()
    with pytest.raises(ValueError, match="exactly cover definitions"):
        FeatureSetConfiguration.create(
            feature_set_version="1.0.0",
            definitions=(definition,),
            configurations=(),
            required_feature_ids=(definition.feature_id,),
            optional_feature_ids=(),
            timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
            coverage_policy=RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING,
            minimum_required_coverage=Decimal("1"),
            missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
            validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
            limitations=(),
        )
    with pytest.raises(ValueError, match="duplicate feature definition"):
        FeatureSetConfiguration.create(
            feature_set_version="1.0.0",
            definitions=(definition, definition),
            configurations=(configuration, configuration),
            required_feature_ids=(definition.feature_id,),
            optional_feature_ids=(),
            timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
            coverage_policy=RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING,
            minimum_required_coverage=Decimal("1"),
            missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
            validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
            limitations=(),
        )


def test_feature_set_rejects_classification_conflict_and_bad_coverage() -> None:
    definition = _definition()
    configuration = _configuration()
    with pytest.raises(ValueError, match="required and optional"):
        FeatureSetConfiguration.create(
            feature_set_version="1.0.0",
            definitions=(definition,),
            configurations=(configuration,),
            required_feature_ids=(definition.feature_id,),
            optional_feature_ids=(definition.feature_id,),
            timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
            coverage_policy=RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING,
            minimum_required_coverage=Decimal("1"),
            missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
            validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
            limitations=(),
        )
    with pytest.raises(ValueError, match="minimum_required_coverage"):
        FeatureSetConfiguration.create(
            feature_set_version="1.0.0",
            definitions=(definition,),
            configurations=(configuration,),
            required_feature_ids=(definition.feature_id,),
            optional_feature_ids=(),
            timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
            coverage_policy=RequiredFeatureCoveragePolicy.ALLOW_PARTIAL,
            minimum_required_coverage=Decimal("1.1"),
            missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
            validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
            limitations=(),
        )


def test_definition_rejects_unknown_or_duplicate_output() -> None:
    with pytest.raises(ValueError, match="duplicate output"):
        FeatureDefinitionV2.create(
            feature_id="technical.bad.v1",
            feature_version="1.0.0",
            model_id=ModelId("bad-model"),
            model_version="1.0.0",
            required_fields=("close",),
            supported_timeframes=(Timeframe.DAILY,),
            minimum_history=1,
            warmup_policy="STRICT",
            missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
            output_schema=(
                FeatureOutputDefinition("same", ValueType.DECIMAL),
                FeatureOutputDefinition("same", ValueType.TEXT),
            ),
            validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
            limitations=(),
        )
