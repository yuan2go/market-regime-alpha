"""Controlled catalog for the first canonical technical-observable feature set."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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


PRICE_ACTION_FEATURE_ID = "technical.price_action.v1"
MOVING_AVERAGE_FEATURE_ID = "technical.moving_average.v2"
MACD_FEATURE_ID = "technical.macd.v1"
CAPITAL_VOLUME_FEATURE_ID = "technical.volume_amount_structure.v1"
VWAP_FEATURE_ID = "technical.session_vwap.v1"
OVERHEAT_FEATURE_ID = "technical.overheat_extension.v1"

PRICE_ACTION_OUTPUTS = (
    "close_location_value",
    "gap_return",
    "high_low_range",
    "intraday_return_to_decision_time",
    "return_1",
    "return_10",
    "return_3",
    "return_5",
)
MOVING_AVERAGE_DECIMAL_OUTPUTS = (
    "distance_ema12_ema26",
    "distance_sma5_sma20",
    "ema_10",
    "ema_12",
    "ema_20",
    "ema_26",
    "ema_5",
    "ema_60",
    "ma_slope_20",
    "ma_slope_5",
    "ma_slope_60",
    "price_vs_ema20_return",
    "price_vs_sma10_return",
    "price_vs_sma20_return",
    "price_vs_sma5_return",
    "sma_10",
    "sma_20",
    "sma_5",
    "sma_60",
)
MOVING_AVERAGE_TEXT_OUTPUTS = ("ma_alignment", "short_ma_cross_state")
MACD_DECIMAL_OUTPUTS = (
    "dea",
    "dea_slope",
    "dif",
    "dif_slope",
    "histogram",
)
MACD_TEXT_OUTPUTS = (
    "cross_state",
    "divergence_candidate",
    "histogram_expansion_state",
    "zero_axis_state",
)
VOLUME_DECIMAL_OUTPUTS = (
    "amount_contraction",
    "amount_expansion",
    "amount_percentile_20",
    "amount_ratio_10",
    "amount_ratio_20",
    "amount_ratio_5",
    "turnover_expansion",
    "volume_contraction",
    "volume_expansion",
    "volume_percentile_20",
    "volume_ratio_10",
    "volume_ratio_20",
    "volume_ratio_5",
)
VOLUME_TEXT_OUTPUTS = (
    "abnormal_volume_state",
    "breakout_volume_confirmation",
    "price_volume_direction_agreement",
)
VWAP_DECIMAL_OUTPUTS = (
    "distance_from_vwap",
    "price_vs_vwap_return",
    "session_vwap",
    "vwap_slope",
)
VWAP_TEXT_OUTPUTS = ("price_crossing_vwap",)
OVERHEAT_OUTPUTS = (
    "distance_from_rolling_high",
    "gap_extension",
    "price_vs_sma10",
    "price_vs_sma5",
    "range_expansion",
    "short_return",
    "volume_price_overextension",
)


def canonical_technical_feature_set(
    *, effective_from: datetime
) -> FeatureSetConfiguration:
    definitions = (
        _definition(
            feature_id=PRICE_ACTION_FEATURE_ID,
            required_fields=("close", "high", "low", "open"),
            timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
            minimum_history=11,
            outputs=_outputs(PRICE_ACTION_OUTPUTS, ValueType.DECIMAL),
        ),
        _definition(
            feature_id=MOVING_AVERAGE_FEATURE_ID,
            required_fields=("close",),
            timeframes=(Timeframe.DAILY,),
            minimum_history=61,
            outputs=(
                *_outputs(MOVING_AVERAGE_DECIMAL_OUTPUTS, ValueType.DECIMAL),
                *_outputs(MOVING_AVERAGE_TEXT_OUTPUTS, ValueType.TEXT),
            ),
        ),
        _definition(
            feature_id=MACD_FEATURE_ID,
            required_fields=("close",),
            timeframes=(Timeframe.DAILY,),
            minimum_history=34,
            outputs=(
                *_outputs(MACD_DECIMAL_OUTPUTS, ValueType.DECIMAL),
                FeatureOutputDefinition(
                    "histogram_consecutive_direction", ValueType.INTEGER
                ),
                *_outputs(MACD_TEXT_OUTPUTS, ValueType.TEXT),
            ),
        ),
        _definition(
            feature_id=CAPITAL_VOLUME_FEATURE_ID,
            required_fields=("close", "volume"),
            timeframes=(Timeframe.DAILY,),
            minimum_history=21,
            outputs=(
                *_outputs(VOLUME_DECIMAL_OUTPUTS, ValueType.DECIMAL),
                FeatureOutputDefinition("turnover_persistence", ValueType.INTEGER),
                FeatureOutputDefinition("volume_persistence", ValueType.INTEGER),
                *_outputs(VOLUME_TEXT_OUTPUTS, ValueType.TEXT),
            ),
        ),
        _definition(
            feature_id=VWAP_FEATURE_ID,
            required_fields=("amount", "close", "volume"),
            timeframes=(
                Timeframe.MINUTE_1,
                Timeframe.MINUTE_5,
                Timeframe.MINUTE_15,
                Timeframe.MINUTE_30,
                Timeframe.MINUTE_60,
            ),
            minimum_history=1,
            outputs=(
                *_outputs(VWAP_DECIMAL_OUTPUTS, ValueType.DECIMAL),
                *_outputs(VWAP_TEXT_OUTPUTS, ValueType.TEXT),
            ),
        ),
        _definition(
            feature_id=OVERHEAT_FEATURE_ID,
            required_fields=("close", "high", "low", "open", "volume"),
            timeframes=(Timeframe.DAILY,),
            minimum_history=21,
            outputs=(
                FeatureOutputDefinition("consecutive_up_sessions", ValueType.INTEGER),
                *_outputs(OVERHEAT_OUTPUTS, ValueType.DECIMAL),
            ),
        ),
    )
    configurations = (
        _configuration(
            feature_id=PRICE_ACTION_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _integer_list("return_windows", "1,3,5,10"),
                _integer("output_scale", 12),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.DAILY.value),
            ),
        ),
        _configuration(
            feature_id=MOVING_AVERAGE_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _text("ema_seed", "FIRST_OBSERVATION_RECURSIVE"),
                _integer_list("ema_periods", "5,10,12,20,26,60"),
                _integer("output_scale", 12),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.DAILY.value),
                _integer_list("sma_periods", "5,10,20,60"),
            ),
        ),
        _configuration(
            feature_id=MACD_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _integer("divergence_lookback", 20),
                _text("ema_seed", "FIRST_OBSERVATION_RECURSIVE"),
                _integer("fast_period", 12),
                _decimal("histogram_multiplier", "2"),
                _integer("output_scale", 12),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.DAILY.value),
                _integer("signal_period", 9),
                _integer("slow_period", 26),
                _integer("warmup_observations", 34),
            ),
        ),
        _configuration(
            feature_id=CAPITAL_VOLUME_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _decimal("abnormal_ratio_threshold", "2"),
                _decimal("breakout_ratio_threshold", "1.5"),
                _integer("output_scale", 12),
                _integer_list("ratio_windows", "5,10,20"),
                _text("ratio_denominator", "PRIOR_COMPLETED_SESSIONS_EXCLUDING_CURRENT"),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.DAILY.value),
            ),
        ),
        _configuration(
            feature_id=VWAP_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _integer("output_scale", 12),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.MINUTE_5.value),
                _text("session_policy", "A_SHARE_REGULAR_SESSION_OBSERVED_BARS_ONLY"),
            ),
        ),
        _configuration(
            feature_id=OVERHEAT_FEATURE_ID,
            effective_from=effective_from,
            parameters=(
                _integer("output_scale", 12),
                _integer("range_window", 5),
                _integer("rolling_high_window", 20),
                _text("rounding", "ROUND_HALF_EVEN"),
                _text("selected_timeframe", Timeframe.DAILY.value),
                _integer("short_return_window", 3),
                _integer("volume_window", 5),
            ),
        ),
    )
    required = (
        CAPITAL_VOLUME_FEATURE_ID,
        MACD_FEATURE_ID,
        MOVING_AVERAGE_FEATURE_ID,
        OVERHEAT_FEATURE_ID,
        PRICE_ACTION_FEATURE_ID,
    )
    return FeatureSetConfiguration.create(
        feature_set_version="canonical-technical-observables-v1",
        definitions=definitions,
        configurations=configurations,
        required_feature_ids=required,
        optional_feature_ids=(VWAP_FEATURE_ID,),
        timeframe_policy=TimeframePolicy.EXACT_MATCH_ONLY,
        coverage_policy=RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING,
        minimum_required_coverage=Decimal("1"),
        missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=(
            "MODEL_ASSUMPTION",
            "NOT_EMPIRICALLY_VALIDATED",
            "RESEARCH_ONLY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


def _definition(
    *,
    feature_id: str,
    required_fields: tuple[str, ...],
    timeframes: tuple[Timeframe, ...],
    minimum_history: int,
    outputs: tuple[FeatureOutputDefinition, ...],
) -> FeatureDefinitionV2:
    return FeatureDefinitionV2.create(
        feature_id=feature_id,
        feature_version="1.0.0",
        model_id=ModelId(f"{feature_id}.model"),
        model_version="1.0.0",
        required_fields=required_fields,
        supported_timeframes=timeframes,
        minimum_history=minimum_history,
        warmup_policy="STRICT_CONFIRMED_TRAILING_OBSERVATIONS",
        missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
        output_schema=outputs,
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=("NOT_EMPIRICALLY_VALIDATED", "RESEARCH_ONLY"),
    )


def _configuration(
    *,
    feature_id: str,
    effective_from: datetime,
    parameters: tuple[FeatureParameter, ...],
) -> FeatureConfiguration:
    return FeatureConfiguration.create(
        configuration_version="1.0.0",
        feature_id=feature_id,
        effective_from=effective_from,
        parameters=parameters,
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
    )


def _outputs(names: tuple[str, ...], value_type: ValueType) -> tuple[FeatureOutputDefinition, ...]:
    return tuple(FeatureOutputDefinition(name, value_type) for name in names)


def _integer(name: str, value: int) -> FeatureParameter:
    return FeatureParameter(name, FeatureParameterType.INTEGER, str(value))


def _integer_list(name: str, value: str) -> FeatureParameter:
    return FeatureParameter(name, FeatureParameterType.INTEGER_LIST, value)


def _decimal(name: str, value: str) -> FeatureParameter:
    return FeatureParameter(name, FeatureParameterType.DECIMAL, value)


def _text(name: str, value: str) -> FeatureParameter:
    return FeatureParameter(name, FeatureParameterType.TEXT, value)
