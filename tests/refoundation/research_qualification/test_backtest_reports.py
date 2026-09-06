from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import inspect
import json
from uuid import UUID, uuid4, uuid5

import pytest

from market_regime_alpha.research_qualification.application.backtest_reports import (
    BacktestReportApplication,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_reports import (
    PostgresBacktestReportSourcePort,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestComparisonMode,
    BacktestComparisonFingerprint,
    BacktestReportConfiguration,
    BacktestReportMetric,
    BacktestReportSource,
)
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    FormulaResultState,
)
from market_regime_alpha.research_qualification.errors import (
    BacktestReportIntegrityError,
    IncompatibleBacktestComparisonError,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.shared.hashing import sha256_bytes
from market_regime_alpha.research_qualification.ports.backtest_queries import (
    BacktestReplayVerification,
)
from tests.refoundation.research_qualification.test_backtest_execution_planner import (
    _run,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _source(*, cost_hash: str = "7" * 64) -> BacktestReportSource:
    run = _run()
    configuration = BacktestReportConfiguration(
        market_archive=AuthorityBinding(_id(2000), "1" * 64),
        market_archive_seal=AuthorityBinding(_id(2001), "2" * 64),
        universe_revision=AuthorityBinding(_id(2002), "3" * 64),
        eligibility_policy=AuthorityBinding(_id(2004), "f" * 64),
        sample_scope_code="stable-hash-32",
        sample_roster_sha256="4" * 64,
        feature_roster_sha256="5" * 64,
        target=VersionedAuthorityBinding(_id(2003), 1, "6" * 64),
        walk_forward_policy_sha256="8" * 64,
        fold_roster_sha256="9" * 64,
        dependency_roster_sha256="a" * 64,
        cost_roster_sha256=cost_hash,
        effective_policy_roster_sha256="b" * 64,
        evaluation_formula_roster_sha256="c" * 64,
        code_content_sha256="d" * 64,
        config_content_sha256="e" * 64,
        first_session_date="2026-01-02",
        last_session_date="2026-03-06",
        distinct_trading_session_count=44,
        fold_session_binding_count=64,
        sample_member_count=32,
    )
    evaluation_run_ids = tuple(_id(2100 + index) for index in range(1, 8))
    metrics = tuple(
        BacktestReportMetric(
            evaluation_metric_id=_id(2200 + ordinal),
            evaluation_run_id=evaluation_run_ids[ordinal - 1],
            evaluation_requirement_id=_id(2300 + ordinal),
            protocol_metric_id=_id(2400 + ordinal),
            arm_id=run.arms[0].exploratory_backtest_arm_id,
            fold_id=None,
            scope_kind="AGGREGATE",
            slice_key=None,
            surface=surface,
            metric_code=f"metric-{surface.value.lower().replace('_', '-')}",
            formula_code=BacktestFormulaCode.MEAN,
            formula_version=1,
            formula_content_sha256=f"{ordinal:x}" * 64,
            result_state=FormulaResultState.ESTIMABLE,
            decimal_value=Decimal(ordinal) / Decimal(100),
            estimable_count=44,
            reason_code="ESTIMATED_BY_FROZEN_FORMULA",
            acceptance_state="NOT_APPLICABLE",
        )
        for ordinal, surface in enumerate(BacktestMetricSurface, start=1)
    )
    return BacktestReportSource(
        run=run,
        configuration=configuration,
        canonical_completed_at=datetime(2026, 3, 9, 8, 30, tzinfo=UTC),
        evaluation_run_ids=evaluation_run_ids,
        metrics=metrics,
        models=(),
        comparison_scope=BacktestComparisonFingerprint(
            market_archive_sha256="1" * 64, universe_sample_sha256="2" * 64,
            target_sha256="3" * 64, fold_dependency_sha256="4" * 64,
            cost_sha256=cost_hash, portfolio_risk_sha256="5" * 64,
            evaluation_formula_sha256="6" * 64, evidence_lane=run.evidence.value,
        ),
        limitations=("Retrospective exploratory data only.",),
        recommended_next_experiment="Collect target-aligned prospective samples.",
    )


class _Source:
    def __init__(self, sources: dict[UUID, BacktestReportSource]) -> None:
        self.sources = sources

    def load(self, exploratory_backtest_run_id: UUID) -> BacktestReportSource:
        return self.sources[exploratory_backtest_run_id]


class _Verifier:
    def __init__(self, *, matched: bool = True) -> None:
        self.matched = matched

    def verify(self, exploratory_backtest_run_id: UUID) -> BacktestReplayVerification:
        return BacktestReplayVerification(
            exploratory_backtest_run_id,
            self.matched,
            () if self.matched else ("ACTION_INTEGRITY:test",),
            "CURRENT_RELATIONAL",
            "d" * 64,
        )


class _Artifacts:
    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}

    def publish(self, content, *, media_type, context):
        del context
        content_hash = sha256_bytes(content)
        self.contents[media_type] = content
        return ArtifactRecord(
            artifact_id=uuid5(_id(9000), content_hash),
            content_sha256=content_hash,
            size_bytes=len(content),
            media_type=media_type,
            locator=f"artifact://{content_hash}",
            integrity_state="AVAILABLE",
            retention_until=None,
            pin_reason_code="BACKTEST_REPORT",
        )


class _Bindings:
    def __init__(self) -> None:
        self.items = []

    def bind_report(self, binding, context):
        del context
        self.items.append(binding)
        return binding


def test_json_and_markdown_are_byte_stable_and_contain_every_required_section() -> None:
    source = _source()
    app = BacktestReportApplication(
        _Source({source.run.exploratory_backtest_run_id: source}),
        _Verifier(),
    )

    first_json = app.render_json(source.run.exploratory_backtest_run_id)
    second_json = app.render_json(source.run.exploratory_backtest_run_id)
    first_markdown = app.render_markdown(source.run.exploratory_backtest_run_id)

    assert first_json == second_json
    assert b"report_generation_time" not in first_json
    assert b"2026-03-09T08:30:00+00:00" in first_json
    payload = json.loads(first_json)
    assert payload["schema"] == "mra-backtest-report-v1"
    assert {
        "executive_summary",
        "evidence_classification",
        "configuration",
        "data_coverage",
        "universe_sample",
        "feature_target_definitions",
        "model_model_versions",
        "walk_forward_design",
        "candidate_metrics",
        "context_attribution",
        "signal_forecast_metrics",
        "portfolio_risk_metrics",
        "gross_net_economics",
        "fold_time_stability",
        "alpha_funnel_diagnosis",
        "baseline_challenger_comparison",
        "not_estimable_failure_reasons",
        "limitations",
        "evidence_ceiling",
        "recommended_next_experiment",
    } <= payload.keys()
    assert payload["evidence_ceiling"] == {
        "alpha_proven": "NO",
        "formal_oos": "NOT_RUN",
        "formal_pit": "BLOCKED",
        "formal_provider": "BLOCKED",
        "prospective_proven": "NO",
        "retrospective": "EXPLORATORY_RETROSPECTIVE",
    }
    assert first_markdown.startswith(b"# Standard Backtest Report\n")
    assert b"## AlphaFunnelDiagnosis" in first_markdown


def test_integrity_mismatch_fails_before_report_source_is_read() -> None:
    source = _source()
    port = _Source({source.run.exploratory_backtest_run_id: source})
    app = BacktestReportApplication(port, _Verifier(matched=False))

    with pytest.raises(BacktestReportIntegrityError, match="zero-mismatch"):
        app.render_json(source.run.exploratory_backtest_run_id)


def test_comparison_fails_closed_or_is_visibly_descriptive() -> None:
    left = _source()
    right = replace(
        _source(cost_hash="f" * 64),
        run=replace(
            _source(cost_hash="f" * 64).run,
            exploratory_backtest_run_id=_id(9999),
        ),
    )
    sources = {
        left.run.exploratory_backtest_run_id: left,
        right.run.exploratory_backtest_run_id: right,
    }
    app = BacktestReportApplication(_Source(sources), _Verifier())

    with pytest.raises(IncompatibleBacktestComparisonError, match="cost_sha256"):
        app.compare(
            left.run.exploratory_backtest_run_id,
            right.run.exploratory_backtest_run_id,
        )

    comparison = app.compare(
        left.run.exploratory_backtest_run_id,
        right.run.exploratory_backtest_run_id,
        descriptive=True,
    )
    assert comparison.mode is BacktestComparisonMode.DESCRIPTIVE_NON_LIKE_FOR_LIKE
    assert comparison.mismatch_fields == ("cost_sha256",)
    assert comparison.winner_run_id is None


def test_postgres_report_projection_has_no_raw_market_reader_or_formula_execution() -> None:
    source = inspect.getsource(PostgresBacktestReportSourcePort).lower()

    assert "market_bar" not in source
    assert "formulaobservation" not in source
    assert ".evaluate(" not in source
    assert "repeatable read" in source


def test_comparison_scope_is_not_part_of_immutable_report_bytes() -> None:
    source = _source()
    updated = replace(source, comparison_scope=replace(source.comparison_scope, cost_sha256="0" * 64))
    original_app = BacktestReportApplication(_Source({source.run.exploratory_backtest_run_id: source}), _Verifier())
    updated_app = BacktestReportApplication(_Source({source.run.exploratory_backtest_run_id: updated}), _Verifier())
    assert source.content_sha256 == updated.content_sha256
    assert original_app.render_json(source.run.exploratory_backtest_run_id) == updated_app.render_json(source.run.exploratory_backtest_run_id)
    assert original_app.render_markdown(source.run.exploratory_backtest_run_id) == updated_app.render_markdown(source.run.exploratory_backtest_run_id)


def test_like_for_like_projection_matches_folds_across_execution_identities() -> None:
    left = _source()
    left = replace(left, metrics=(
        replace(left.metrics[0], scope_kind="FOLD", fold_id=left.run.folds[0].exploratory_backtest_fold_id),
        *left.metrics[1:],
    ))
    arm_ids = {arm.exploratory_backtest_arm_id: uuid4() for arm in left.run.arms}
    fold_ids = {fold.exploratory_backtest_fold_id: uuid4() for fold in left.run.folds}
    evaluation_ids = {identity: uuid4() for identity in left.evaluation_run_ids}
    right_run = replace(
        left.run, exploratory_backtest_run_id=uuid4(), run_code="same_scope_new_execution",
        arms=tuple(replace(arm, exploratory_backtest_arm_id=arm_ids[arm.exploratory_backtest_arm_id]) for arm in left.run.arms),
        folds=tuple(replace(fold, exploratory_backtest_fold_id=fold_ids[fold.exploratory_backtest_fold_id]) for fold in left.run.folds),
        fold_dependencies=tuple(replace(item, dependency_id=uuid4(), fit_fold_id=fold_ids[item.fit_fold_id], validation_fold_id=fold_ids[item.validation_fold_id]) for item in left.run.fold_dependencies),
        arm_folds=tuple(replace(item, arm_fold_id=uuid4(), arm_id=arm_ids[item.arm_id], fold_id=fold_ids[item.fold_id]) for item in left.run.arm_folds),
        model_training_requirements=tuple(replace(item, requirement_id=uuid4(), model_arm_id=arm_ids[item.model_arm_id], fit_fold_id=fold_ids[item.fit_fold_id], validation_fold_id=fold_ids[item.validation_fold_id]) for item in left.run.model_training_requirements),
        evaluation_requirements=tuple(replace(item, requirement_id=uuid4(), arm_id=arm_ids[item.arm_id], fold_id=fold_ids.get(item.fold_id)) for item in left.run.evaluation_requirements),
    )
    # A source adapter supplies an identical comparison scope while retaining
    # different execution lineage in the report's canonical configuration.
    right = replace(
        left, run=right_run,
        configuration=replace(left.configuration, fold_roster_sha256="0" * 64,
                              dependency_roster_sha256="1" * 64,
                              cost_roster_sha256="2" * 64,
                              effective_policy_roster_sha256="3" * 64,
                              evaluation_formula_roster_sha256="4" * 64),
        evaluation_run_ids=tuple(evaluation_ids.values()),
        metrics=tuple(replace(metric, evaluation_metric_id=uuid4(),
                              evaluation_requirement_id=uuid4(),
                              evaluation_run_id=evaluation_ids[metric.evaluation_run_id],
                              arm_id=arm_ids[metric.arm_id], fold_id=fold_ids.get(metric.fold_id))
                      for metric in left.metrics),
    )
    application = BacktestReportApplication(_Source({
        left.run.exploratory_backtest_run_id: left,
        right.run.exploratory_backtest_run_id: right,
    }), _Verifier())
    comparison = application.compare(left.run.exploratory_backtest_run_id, right.run.exploratory_backtest_run_id)
    assert comparison.mode is BacktestComparisonMode.LIKE_FOR_LIKE
    assert comparison.mismatch_fields == ()
    assert len(comparison.metric_deltas) == len(left.metrics)
    assert all(item.delta == 0 for item in comparison.metric_deltas)
    assert comparison.winner_run_id is None


def test_report_publication_binds_exact_json_and_markdown_artifacts() -> None:
    source = _source()
    app = BacktestReportApplication(
        _Source({source.run.exploratory_backtest_run_id: source}),
        _Verifier(),
    )
    artifacts = _Artifacts()
    bindings = _Bindings()
    context = CommandContext(
        idempotency_key="publish-standard-backtest-report",
        actor_type=ActorType.OPERATOR,
        actor_id="test-operator",
        reason_code="PUBLISH_BACKTEST_REPORT",
    )

    first = app.publish(
        source.run.exploratory_backtest_run_id,
        artifacts=artifacts,
        bindings=bindings,
        context=context,
    )
    second = app.publish(
        source.run.exploratory_backtest_run_id,
        artifacts=artifacts,
        bindings=bindings,
        context=context,
    )

    assert first == second
    assert str(first.json_artifact.content_sha256) == sha256_bytes(artifacts.contents["application/json"])
    assert str(first.markdown_artifact.content_sha256) == sha256_bytes(artifacts.contents["text/markdown"])
    assert first.evaluation_roster_sha256 == source.evaluation_roster_sha256


@pytest.mark.parametrize("evidence_gap", ["none", "missing", "not_estimable"])
def test_alpha_diagnosis_does_not_infer_bottleneck_from_metric_availability(evidence_gap):
    source = _source()
    if evidence_gap == "missing":
        source = replace(source, metrics=source.metrics[1:])
    elif evidence_gap == "not_estimable":
        source = replace(source, metrics=(replace(source.metrics[0], result_state=FormulaResultState.NOT_ESTIMABLE, decimal_value=None, estimable_count=0, reason_code="INSUFFICIENT_OBSERVATIONS"), *source.metrics[1:]))
    app = BacktestReportApplication(_Source({source.run.exploratory_backtest_run_id: source}), _Verifier())
    diagnosis = app.project(source.run.exploratory_backtest_run_id)["alpha_funnel_diagnosis"]
    assert diagnosis["state"] == "NOT_DETERMINED"
    assert diagnosis["bottleneck_surface"] is None
    assert diagnosis["reason_codes"] == ("NO_CANONICAL_BOTTLENECK_ATTRIBUTION",)
    assert tuple(item["surface"] for item in diagnosis["surface_evidence"]) == tuple(surface.value for surface in BacktestMetricSurface)
    if evidence_gap == "missing":
        assert diagnosis["surface_evidence"][0]["reason_codes"] == ("NO_CANONICAL_EVALUATION_METRIC",)
    elif evidence_gap == "not_estimable":
        assert diagnosis["surface_evidence"][0]["reason_codes"] == ("INSUFFICIENT_OBSERVATIONS",)


def test_report_preserves_canonical_risk_reasons_and_rejects_foreign_evaluation():
    from market_regime_alpha.research_qualification.domain.backtest_report import BacktestReportRiskReason
    source = _source()
    reason = BacktestReportRiskReason(
        evaluation_run_id=source.evaluation_run_ids[0], decision_run_id=uuid4(),
        risk_decision_id=uuid4(), risk_decision_sha256='a' * 64,
        risk_reason_id=uuid4(), risk_reason_sha256='b' * 64,
        risk_status='REJECTED', result='FAIL', reason_code='MAXIMUM_SINGLE_WEIGHT',
    )
    with_reasons = replace(source, risk_reasons=(reason,))
    assert with_reasons.content_sha256 != source.content_sha256
    app = BacktestReportApplication(_Source({source.run.exploratory_backtest_run_id: with_reasons}), _Verifier())
    payload = app.project(source.run.exploratory_backtest_run_id)
    row, = payload['not_estimable_failure_reasons']['risk_reasons']
    assert row['risk_reason_id'] == str(reason.risk_reason_id)
    assert row['reason_code'] == 'MAXIMUM_SINGLE_WEIGHT'
    assert b'MAXIMUM_SINGLE_WEIGHT' in app.render_markdown(source.run.exploratory_backtest_run_id)
    with pytest.raises(ValueError, match='Risk.*Evaluation roster'):
        replace(source, risk_reasons=(replace(reason, evaluation_run_id=uuid4()),))
