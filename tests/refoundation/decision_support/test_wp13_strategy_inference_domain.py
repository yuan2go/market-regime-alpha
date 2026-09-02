from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.decision_support.domain import (
    CandidateDisposition,
    ContextKind,
    ContextMetricStatus,
    ContextState,
    DecisionArtifactBinding,
)
from market_regime_alpha.decision_support.domain.inference import (
    ForecastCalibrationStatus,
    ForecastStatus,
    PreparedForecastCommitment,
    PreparedForecastInputs,
    PreparedSignalCandidate,
    PreparedSignalContext,
    PreparedSignalInputs,
    SignalStatus,
    build_forecast_authority,
    build_signal_authority,
)
from market_regime_alpha.decision_support.domain.strategy import (
    ContextFailureAction,
    ForecastSourceMeasure,
    StrategyActionPolicy,
    StrategyContextRequirement,
    StrategyForecastRule,
    StrategyPlan,
    StrategySignalRule,
    StrategyVersionPlan,
)
from tests.refoundation.decision_support.test_decision_domain import _uuid


DECISION_TIME = datetime(2026, 9, 1, 7, 1, tzinfo=UTC)
RECORDED_AT = datetime(2026, 9, 1, 7, 3, tzinfo=UTC)


def _artifact(suffix: int, character: str) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        artifact_id=_uuid(suffix),
        content_sha256=character * 64,
        size_bytes=100 + suffix,
    )


def _strategy() -> StrategyVersionPlan:
    strategy_id = _uuid(2000)
    version_id = _uuid(2001)
    return StrategyVersionPlan(
        strategy=StrategyPlan(
            strategy_id=strategy_id,
            strategy_code="transparent_context_baseline",
            objective="Context-confirmed uncalibrated Target forecast",
        ),
        strategy_version_id=version_id,
        version=1,
        supersedes_strategy_version_id=None,
        primary_change="Initial transparent deterministic baseline",
        action_policy=StrategyActionPolicy.LONG_ONLY_RESEARCH,
        context_requirements=(
            StrategyContextRequirement(
                strategy_context_requirement_id=_uuid(2010),
                strategy_version_id=version_id,
                ordinal=1,
                context_policy_id=_uuid(2005),
                context_policy_content_sha256="8" * 64,
                context_kind=ContextKind.MARKET_REGIME,
                required_state=ContextState.POSITIVE,
                missing_action=ContextFailureAction.WAIT,
            ),
            StrategyContextRequirement(
                strategy_context_requirement_id=_uuid(2011),
                strategy_version_id=version_id,
                ordinal=2,
                context_policy_id=_uuid(2005),
                context_policy_content_sha256="8" * 64,
                context_kind=ContextKind.CAPITAL_BREADTH,
                required_state=ContextState.POSITIVE,
                missing_action=ContextFailureAction.NOT_ESTIMABLE,
            ),
        ),
        signal_rule=StrategySignalRule(
            strategy_signal_rule_id=_uuid(2020),
            strategy_version_id=version_id,
            eligible_disposition=CandidateDisposition.SELECTED,
            positive_status=SignalStatus.PRESENT,
            negative_status=SignalStatus.NO_SIGNAL,
            ineligible_status=SignalStatus.NO_SIGNAL,
        ),
        forecast_rules=(
            StrategyForecastRule(
                strategy_forecast_rule_id=_uuid(2030),
                strategy_version_id=version_id,
                ordinal=1,
                target_definition_id=_uuid(2040),
                target_definition_sha256="d" * 64,
                target_checkpoint_id=_uuid(2041),
                target_checkpoint_sha256="e" * 64,
                target_metric_definition_id=_uuid(2042),
                target_metric_definition_sha256="f" * 64,
                source_measure=ForecastSourceMeasure.CANDIDATE_COMPOSITE_SCORE,
                coefficient=Decimal("0.02"),
                intercept=Decimal("-0.01"),
                lower_offset=Decimal("0.03"),
                upper_offset=Decimal("0.03"),
                value_unit="DECIMAL_RETURN",
            ),
        ),
        code_artifact=_artifact(2050, "a"),
        config_artifact=_artifact(2051, "b"),
        provenance_sha256="c" * 64,
    )


def _context(
    candidate_suffix: int,
    requirement,
    *,
    status: ContextMetricStatus = ContextMetricStatus.AVAILABLE,
    state: ContextState = ContextState.POSITIVE,
) -> PreparedSignalContext:
    del candidate_suffix
    return PreparedSignalContext(
        strategy_context_requirement_id=(
            requirement.strategy_context_requirement_id
        ),
        context_policy_id=requirement.context_policy_id,
        context_policy_content_sha256=requirement.context_policy_content_sha256,
        context_assessment_id=_uuid(2100 + requirement.ordinal),
        assessment_group_id=_uuid(2110),
        context_kind=requirement.context_kind,
        assessment_status=status,
        assessment_state=state,
        assessment_content_sha256=format(2100 + requirement.ordinal, "064x"),
        recorded_at=RECORDED_AT,
    )


def _candidate(
    strategy: StrategyVersionPlan,
    suffix: int,
    disposition: CandidateDisposition,
    *,
    second_status: ContextMetricStatus = ContextMetricStatus.AVAILABLE,
) -> PreparedSignalCandidate:
    return PreparedSignalCandidate(
        candidate_id=_uuid(2200 + suffix),
        instrument_id=_uuid(2250 + suffix),
        disposition=disposition,
        composite_score=(
            None
            if disposition is CandidateDisposition.UNRANKABLE
            else Decimal("0.75")
        ),
        contexts=(
            _context(suffix, strategy.context_requirements[0]),
            _context(
                suffix,
                strategy.context_requirements[1],
                status=second_status,
                state=(
                    ContextState.UNKNOWN
                    if second_status is not ContextMetricStatus.AVAILABLE
                    else ContextState.POSITIVE
                ),
            ),
        ),
    )


def test_strategy_version_freezes_complete_relational_definition() -> None:
    strategy = _strategy()

    assert strategy.context_requirement_count == 2
    assert strategy.forecast_rule_count == 1
    assert len(strategy.context_requirement_roster_sha256) == 64
    assert len(strategy.forecast_rule_roster_sha256) == 64
    assert len(strategy.content_sha256) == 64
    with pytest.raises(ValueError, match="contiguous"):
        replace(
            strategy,
            context_requirements=(
                replace(strategy.context_requirements[0], ordinal=2),
            ),
        )
    with pytest.raises(ValueError, match="duplicate"):
        replace(
            strategy,
            context_requirements=(
                strategy.context_requirements[0],
                replace(strategy.context_requirements[0], ordinal=2),
            ),
        )


def test_forecast_rule_rejects_invalid_decimal_bounds_and_target_shape() -> None:
    rule = _strategy().forecast_rules[0]

    with pytest.raises(ValueError, match="offset"):
        replace(rule, lower_offset=Decimal("-0.01"))
    with pytest.raises(ValueError, match="Target"):
        replace(rule, target_definition_id=rule.target_checkpoint_id)


def test_signal_preserves_every_candidate_and_missing_context_state() -> None:
    strategy = _strategy()
    candidates = (
        _candidate(strategy, 1, CandidateDisposition.SELECTED),
        _candidate(strategy, 2, CandidateDisposition.RANKED_NOT_SELECTED),
        _candidate(
            strategy,
            3,
            CandidateDisposition.SELECTED,
            second_status=ContextMetricStatus.NOT_ESTIMABLE,
        ),
    )
    prepared = PreparedSignalInputs(
        decision_run_id=_uuid(2300),
        candidate_set_id=_uuid(2301),
        candidate_set_content_sha256="0" * 64,
        candidate_roster_sha256="1" * 64,
        decision_time=DECISION_TIME,
        strategy_version=strategy,
        candidates=candidates,
    )
    authority = build_signal_authority(
        signal_group_id=_uuid(2310),
        prepared=prepared,
        request_identity="produce-signal-1",
        request_sha256="2" * 64,
        command_receipt_id=_uuid(2311),
        recorded_at=RECORDED_AT,
        signal_id_factory=lambda candidate, ordinal: _uuid(2320 + ordinal),
        binding_id_factory=lambda candidate, context: _uuid(
            2400
            + int(str(candidate.candidate_id)[-2:], 16)
            + int(str(context.strategy_context_requirement_id)[-2:], 16)
        ),
    )

    assert tuple(signal.status for signal in authority.signals) == (
        SignalStatus.PRESENT,
        SignalStatus.NO_SIGNAL,
        SignalStatus.NOT_ESTIMABLE,
    )
    assert authority.signal_count == 3
    assert authority.context_binding_count == 6

    with pytest.raises(ValueError, match="complete Context roster"):
        replace(
            prepared,
            candidates=(
                replace(candidates[0], contexts=(candidates[0].contexts[0],)),
                *candidates[1:],
            ),
        )


def test_forecast_is_target_bound_uncalibrated_and_complete() -> None:
    strategy = _strategy()
    candidates = (
        _candidate(strategy, 1, CandidateDisposition.SELECTED),
        _candidate(strategy, 2, CandidateDisposition.RANKED_NOT_SELECTED),
    )
    signals = build_signal_authority(
        signal_group_id=_uuid(2500),
        prepared=PreparedSignalInputs(
            decision_run_id=_uuid(2510),
            candidate_set_id=_uuid(2511),
            candidate_set_content_sha256="2" * 64,
            candidate_roster_sha256="3" * 64,
            decision_time=DECISION_TIME,
            strategy_version=strategy,
            candidates=candidates,
        ),
        request_identity="signal-for-forecast",
        request_sha256="4" * 64,
        command_receipt_id=_uuid(2512),
        recorded_at=RECORDED_AT,
        signal_id_factory=lambda candidate, ordinal: _uuid(2520 + ordinal),
        binding_id_factory=lambda candidate, context: _uuid(
            2600
            + int(str(candidate.candidate_id)[-2:], 16)
            + int(str(context.strategy_context_requirement_id)[-2:], 16)
        ),
    )
    rule = strategy.forecast_rules[0]
    commitments = tuple(
        PreparedForecastCommitment(
            commitment_id=_uuid(2700 + ordinal),
            candidate_id=signal.candidate.candidate_id,
            instrument_id=signal.candidate.instrument_id,
            target_definition_id=rule.target_definition_id,
            target_definition_sha256=rule.target_definition_sha256,
            target_checkpoint_id=rule.target_checkpoint_id,
            target_checkpoint_sha256=rule.target_checkpoint_sha256,
            commitment_content_sha256=format(2700 + ordinal, "064x"),
        )
        for ordinal, signal in enumerate(signals.signals, start=1)
    )
    authority = build_forecast_authority(
        forecast_group_id=_uuid(2750),
        prepared=PreparedForecastInputs(
            decision_run_id=signals.decision_run_id,
            strategy_version=strategy,
            signal_authority=signals,
            commitments=commitments,
        ),
        request_identity="produce-forecast-1",
        request_sha256="5" * 64,
        command_receipt_id=_uuid(2751),
        recorded_at=RECORDED_AT,
        forecast_id_factory=lambda signal, commitment: _uuid(
            2760 + signal.ordinal
        ),
        estimate_id_factory=lambda rule, forecast: _uuid(
            2800 + forecast.ordinal
        ),
    )

    assert authority.forecast_count == 2
    assert authority.estimate_count == 2
    assert authority.forecasts[0].status is ForecastStatus.AVAILABLE
    assert authority.forecasts[0].calibration_status is (
        ForecastCalibrationStatus.UNCALIBRATED
    )
    assert authority.forecasts[0].estimates[0].point_estimate == Decimal("0.0050")
    assert authority.forecasts[1].status is ForecastStatus.NOT_APPLICABLE
    assert authority.forecasts[1].estimates[0].point_estimate is None
    assert not hasattr(authority.forecasts[0], "probability")

    with pytest.raises(ValueError, match="complete commitment roster"):
        replace(
            PreparedForecastInputs(
                decision_run_id=signals.decision_run_id,
                strategy_version=strategy,
                signal_authority=signals,
                commitments=commitments,
            ),
            commitments=(commitments[0],),
        )
