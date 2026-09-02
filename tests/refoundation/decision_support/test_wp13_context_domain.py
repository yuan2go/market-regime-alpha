from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.decision_support.domain.context import (
    ContextKind,
    ContextMeasure,
    ContextMetricDefinition,
    ContextMetricStatus,
    ContextMissingnessPolicy,
    ContextOperator,
    ContextPolicyPlan,
    ContextReducer,
    ContextSourceKind,
    ContextSourceRole,
    ContextSourceValueStatus,
    DecisionArtifactBinding,
    PreparedContextInputs,
    PreparedContextSource,
    build_context_assessment_authority,
)
from tests.refoundation.decision_support.test_decision_domain import _uuid


DECISION_TIME = datetime(2026, 9, 1, 7, 1, tzinfo=UTC)


def _artifact(suffix: int, character: str) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        artifact_id=_uuid(suffix),
        content_sha256=character * 64,
        size_bytes=100 + suffix,
    )


def _metric(
    ordinal: int,
    kind: ContextKind,
    measure: ContextMeasure,
    reducer: ContextReducer,
    *,
    missingness: ContextMissingnessPolicy = ContextMissingnessPolicy.NOT_ESTIMABLE,
) -> ContextMetricDefinition:
    return ContextMetricDefinition(
        context_policy_metric_id=_uuid(100 + ordinal),
        context_policy_id=_uuid(100),
        metric_code=f"{kind.value.lower()}_{measure.value.lower()}",
        ordinal=ordinal,
        context_kind=kind,
        measure=measure,
        reducer=reducer,
        operator=ContextOperator.AT_LEAST,
        lower_threshold=Decimal("0.50"),
        upper_threshold=None,
        minimum_source_count=0,
        minimum_available_count=1,
        missingness_policy=missingness,
        source_role=ContextSourceRole.PRIMARY_DECISION_REFERENCE,
    )


def _policy() -> ContextPolicyPlan:
    return ContextPolicyPlan(
        context_policy_id=_uuid(100),
        policy_code="wp13_context_baseline",
        version=1,
        supersedes_policy_id=None,
        metrics=(
            _metric(
                1,
                ContextKind.MARKET_REGIME,
                ContextMeasure.ADVANCE_RATE,
                ContextReducer.TRUE_RATE,
            ),
            _metric(
                2,
                ContextKind.ETF_ROTATION,
                ContextMeasure.RETURN,
                ContextReducer.MEAN_DECIMAL,
            ),
            _metric(
                3,
                ContextKind.THEME_ROTATION,
                ContextMeasure.MEMBER_COVERAGE,
                ContextReducer.TRUE_RATE,
            ),
            _metric(
                4,
                ContextKind.CAPITAL_BREADTH,
                ContextMeasure.FLOW_PROXY,
                ContextReducer.SUM_DECIMAL,
            ),
        ),
        code_artifact=_artifact(201, "a"),
        config_artifact=_artifact(202, "b"),
        provenance_sha256="c" * 64,
    )


def _source(
    metric: ContextMetricDefinition,
    suffix: int,
    *,
    decimal_value: Decimal | None = None,
    boolean_value: bool | None = None,
    status: ContextSourceValueStatus = ContextSourceValueStatus.AVAILABLE,
    kind: ContextSourceKind = ContextSourceKind.MARKET_BAR,
) -> PreparedContextSource:
    return PreparedContextSource(
        context_policy_metric_id=metric.context_policy_metric_id,
        candidate_id=_uuid(300 + suffix),
        instrument_id=_uuid(400 + suffix),
        source_kind=kind,
        source_ordinal=suffix,
        decision_reference_observation_id=_uuid(450 + suffix),
        bar_revision_id=_uuid(500 + suffix) if kind is ContextSourceKind.MARKET_BAR else None,
        source_gap_id=_uuid(600 + suffix) if kind is ContextSourceKind.SOURCE_GAP else None,
        known_at=DECISION_TIME,
        value_status=status,
        decimal_value=decimal_value,
        boolean_value=boolean_value,
    )


def test_context_policy_freezes_complete_kind_and_metric_rosters() -> None:
    policy = _policy()

    assert policy.metric_count == 4
    assert policy.kind_count == 4
    assert len(policy.metric_roster_sha256) == 64
    assert len(policy.kind_roster_sha256) == 64
    assert len(policy.content_sha256) == 64

    with pytest.raises(ValueError, match="contiguous"):
        replace(policy, metrics=(replace(policy.metrics[0], ordinal=2),))
    with pytest.raises(ValueError, match="duplicate"):
        replace(policy, metrics=(policy.metrics[0], replace(policy.metrics[0], ordinal=2)))


def test_metric_freezes_measure_reducer_and_threshold_compatibility() -> None:
    metric = _policy().metrics[0]

    with pytest.raises(ValueError, match="BOOLEAN measure"):
        replace(metric, reducer=ContextReducer.MEAN_DECIMAL)
    with pytest.raises(ValueError, match="BETWEEN"):
        replace(
            metric,
            operator=ContextOperator.BETWEEN,
            upper_threshold=None,
        )
    with pytest.raises(ValueError, match="minimum available"):
        replace(metric, minimum_available_count=-1)


def test_context_assessment_preserves_complete_sources_and_typed_missingness() -> None:
    policy = _policy()
    sources = (
        _source(policy.metrics[0], 1, boolean_value=True),
        _source(policy.metrics[0], 2, boolean_value=False),
        _source(policy.metrics[1], 1, decimal_value=Decimal("0.10")),
        _source(
            policy.metrics[1],
            2,
            status=ContextSourceValueStatus.UNAVAILABLE,
            kind=ContextSourceKind.SOURCE_GAP,
        ),
        _source(policy.metrics[2], 1, boolean_value=True),
        _source(policy.metrics[2], 2, boolean_value=False, kind=ContextSourceKind.SOURCE_GAP),
        _source(policy.metrics[3], 1, decimal_value=Decimal("12.5")),
        _source(
            policy.metrics[3],
            2,
            status=ContextSourceValueStatus.FAILED,
            kind=ContextSourceKind.SOURCE_GAP,
        ),
    )
    prepared = PreparedContextInputs(
        decision_run_id=_uuid(700),
        candidate_set_id=_uuid(701),
        candidate_set_content_sha256="9" * 64,
        candidate_roster_sha256="d" * 64,
        decision_time=DECISION_TIME,
        candidate_count=2,
        policy=policy,
        sources=sources,
    )

    authority = build_context_assessment_authority(
        assessment_group_id=_uuid(710),
        prepared=prepared,
        request_identity="assess-context-1",
        request_sha256="e" * 64,
        command_receipt_id=_uuid(711),
        recorded_at=datetime(2026, 9, 1, 7, 2, tzinfo=UTC),
        assessment_id_factory=lambda kind, ordinal: _uuid(720 + ordinal),
        metric_id_factory=lambda metric: _uuid(740 + metric.ordinal),
        source_id_factory=lambda metric, source: _uuid(
            800 + metric.ordinal * 10 + source.source_ordinal
        ),
    )

    by_kind = {item.context_kind: item for item in authority.assessments}
    market_metric = by_kind[ContextKind.MARKET_REGIME].metrics[0]
    assert market_metric.status is ContextMetricStatus.AVAILABLE
    assert market_metric.decimal_value == Decimal("0.5")
    assert len(market_metric.sources) == 2
    assert by_kind[ContextKind.ETF_ROTATION].metrics[0].decimal_value == Decimal("0.10")
    assert by_kind[ContextKind.CAPITAL_BREADTH].metrics[0].status is (
        ContextMetricStatus.NOT_ESTIMABLE
    )
    assert authority.assessment_count == 4
    assert authority.metric_count == 4
    assert authority.source_count == 8
    assert len(authority.assessment_roster_sha256) == 64


def test_context_assessment_rejects_posterior_candidate_omission_and_late_source() -> None:
    policy = replace(_policy(), metrics=(_policy().metrics[0],))
    one_source = _source(policy.metrics[0], 1, boolean_value=True)

    with pytest.raises(ValueError, match="complete Candidate roster"):
        PreparedContextInputs(
            decision_run_id=_uuid(900),
            candidate_set_id=_uuid(901),
            candidate_set_content_sha256="8" * 64,
            candidate_roster_sha256="f" * 64,
            decision_time=DECISION_TIME,
            candidate_count=2,
            policy=policy,
            sources=(one_source,),
        )
    with pytest.raises(ValueError, match="DecisionTime"):
        replace(
            one_source,
            known_at=datetime(2026, 9, 1, 7, 2, tzinfo=UTC),
        ).validate_for_decision_time(DECISION_TIME)
