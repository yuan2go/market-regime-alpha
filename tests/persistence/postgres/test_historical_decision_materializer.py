from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.decision_materializer import (
    FREE_RESEARCH_UNIVERSE_KIND,
    HistoricalDecisionMaterializer,
    _historical_facts_reference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.evidence_producer import (
    HistoricalEvidenceProducer,
)
from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_phase_e3_feature_configuration,
    create_golden_loop_v2_historical_experiment,
    create_phase_e3_strategy_economics_policy_set,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
    GoldenLoopSessionEvaluation,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.multi_strategy import (
    MultiStrategyHistoricalAdapter,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.historical_research.postgres_session_owner import (
    PostgresHistoricalSessionOwner,
)
from market_regime_alpha.application.historical_research.runner import (
    HistoricalResearchRunner,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioPolicy,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactCoverageGap,
    HistoricalSecurityFactKind,
    HistoricalSecurityFactsOwner,
)
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    HistoricalConstituentCohort,
    HistoricalConstituentTimeline,
    build_historical_constituent_universe_snapshot,
)
from market_regime_alpha.universe.runtime_scope import (
    UniversePolicySelector,
    UniverseScopeKind,
    build_research_universe_policy,
)
from tests.application.historical_corpus.support import raw_owner
from tests.persistence.postgres.test_historical_research_journal import MutableClock


MATERIALIZED_AT = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
DATA_RETRIEVED_AT = MATERIALIZED_AT - timedelta(hours=1)
DECISION_DATE = date(2022, 4, 12)
STOCKS = (
    "000001.SZ",
    "000002.SZ",
    "000063.SZ",
    "600000.SH",
    "600036.SH",
    "601318.SH",
)
ETF = "510300.SH"
INDEX = "000300.SH"


def test_existing_historical_runner_actively_materializes_and_replays(
    postgres_factory,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifact-root"
    corpus = PostgresHistoricalCorpusRepository(
        postgres_factory,
        artifact_root=artifact_root,
    )
    raw = raw_owner()
    corpus.publish_and_register(raw)
    normalized = _normalized_owner(raw.reference)
    corpus.publish_and_register(normalized)
    universe_repository = PostgresFreeResearchUniverseRepository(postgres_factory)
    universe = universe_repository.publish(_universe())
    universe_reference = ValidationArtifactReference(
        FREE_RESEARCH_UNIVERSE_KIND,
        universe.snapshot_id,
        universe.snapshot_hash,
    )
    timeline = universe_repository.publish_timeline(
        HistoricalConstituentTimeline.create(
            start_date=DECISION_DATE,
            end_date=DECISION_DATE + timedelta(days=1),
            queried_trading_dates=(DECISION_DATE, DECISION_DATE + timedelta(days=1)),
            query_effective_dates=(
                (DECISION_DATE, DECISION_DATE),
                (DECISION_DATE + timedelta(days=1), DECISION_DATE),
            ),
            cohorts=(HistoricalConstituentCohort(DECISION_DATE, universe_reference),),
            scan_source_manifest_reference=ValidationArtifactReference(
                "SOURCE_MANIFEST",
                ArtifactId("phase-e-integration-timeline-source"),
                canonical_hash({"phase-e": "integration-timeline-source"}),
            ),
            raw_archive_id="phase-e-integration-timeline-archive",
            known_at=MATERIALIZED_AT,
        )
    )
    facts_repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    facts = facts_repository.publish(_historical_facts((universe_reference, timeline.reference)))
    scope_repository = PostgresRuntimeScopeRepository(postgres_factory)
    policy = scope_repository.register_policy(_policy())
    target_repository = PostgresTargetOutcomeRepository(postgres_factory)
    target_protocol = target_repository.register_protocol(
        exploratory_five_minute_multi_horizon_protocol(),
        recorded_at=MATERIALIZED_AT,
    )
    context_payload = {
        "schema_version": "historical-context-instrument-set/v1",
        "market_index_symbol": INDEX,
        "theme_etf_symbol": ETF,
        "limitations": [
            "EXPLORATORY_CONTEXT_ONLY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "PIT_INCOMPLETE",
        ],
    }
    context_hash = canonical_hash(context_payload)
    context_reference = ValidationArtifactReference(
        "HISTORICAL_CONTEXT_INSTRUMENT_SET",
        ArtifactId(f"historical-context-instrument-set:{context_hash[7:]}"),
        context_hash,
    )
    validation_repository = PostgresResearchValidationRepository(postgres_factory)
    validation_repository.record(
        artifact_id=context_reference.artifact_id,
        artifact_hash=context_reference.content_hash,
        artifact_kind=context_reference.artifact_kind,
        evidence_authority="ENGINEERING_ONLY",
        payload=context_payload,
        created_at=MATERIALIZED_AT,
    )
    with pytest.raises(ValueError, match="typed owner-specific writer"):
        validation_repository.record(
            artifact_id=ArtifactId("arbitrary-experiment-json"),
            artifact_hash=canonical_hash({"phase-e": "arbitrary"}),
            artifact_kind="RESEARCH_EXPERIMENT_DEFINITION",
            evidence_authority="ENGINEERING_ONLY",
            payload={"phase-e": "arbitrary"},
            created_at=MATERIALIZED_AT,
        )
    feature_owner = create_phase_e3_feature_configuration()
    economics_owner = create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=MATERIALIZED_AT,
    )
    validation_repository.record_feature_set_configuration(
        feature_owner,
        recorded_at=MATERIALIZED_AT,
    )
    validation_repository.record_historical_strategy_economics_policy_set(economics_owner)
    experiment = create_golden_loop_v2_historical_experiment(
        target_protocol,
        locked_at=MATERIALIZED_AT,
    )
    validation_repository.record_historical_experiment_definition(
        experiment,
        recorded_at=MATERIALIZED_AT,
    )
    command = _command(
        normalized.reference,
        universe_reference,
        timeline.reference,
        policy.policy_id,
        policy.policy_hash,
        ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
        facts.reference,
        context_reference,
        ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            experiment.definition_id,
            experiment.definition_hash,
        ),
        (
            experiment.feature_reference,
            experiment.cost_policy_reference,
            GoldenLoopScoringContract.create_v2().reference,
        ),
    )
    journal = PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(MATERIALIZED_AT),
    )
    component_repository = PostgresHistoricalMaterializationRepository(postgres_factory)
    materializer = HistoricalDecisionMaterializer(
        run_id=command.run_id,
        corpus_repository=corpus,
        component_repository=component_repository,
        universe_repository=universe_repository,
        scope_repository=scope_repository,
        target_repository=target_repository,
        validation_repository=validation_repository,
        historical_facts_repository=facts_repository,
    )
    strategy_repository = PostgresMultiStrategyRepository(postgres_factory)
    strategy_repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=MATERIALIZED_AT,
    )
    archive_materializer = MultiStrategyHistoricalAdapter(
        delegate=materializer,
        component_repository=component_repository,
        strategy_repository=strategy_repository,
        parent_run_reference=RuntimeArtifactReference(
            "HISTORICAL_RESEARCH_RUN",
            command.run_id,
            command.command_hash,
        ),
        portfolio_policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.20"),
        ),
    )
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(
            PostgresHistoricalSessionOwner(
                postgres_factory,
                archive_materializer=archive_materializer,
            )
        ),
    )

    partial = runner.run(command=command, max_stage_commits=2)
    resumed = runner.resume(run_id=command.run_id)
    replay = runner.replay(run_id=command.run_id)

    assert partial.status is HistoricalRunStatus.RUNNING
    assert tuple(item.stage for item in partial.sessions[0].receipts) == (
        ResearchSessionStage.SCOPE,
        ResearchSessionStage.DECISION,
    )
    assert partial.sessions[0].receipts[-1].status is SessionStageStatus.COMPLETE
    decision_kinds = {item.artifact_kind for item in partial.sessions[0].receipts[-1].output_references}
    assert {
        "HISTORICAL_FEATURE",
        "HISTORICAL_MARKET_REGIME",
        "HISTORICAL_ETF",
        "HISTORICAL_THEME",
        "HISTORICAL_CAPITAL",
        "HISTORICAL_CANDIDATE",
        "HISTORICAL_SIGNAL",
    }.issubset(decision_kinds)
    signal_reference = next(
        item for item in partial.sessions[0].receipts[-1].output_references if item.artifact_kind == "HISTORICAL_SIGNAL"
    )
    signal = component_repository.get(signal_reference)
    feature_reference = next(
        item for item in partial.sessions[0].receipts[-1].output_references if item.artifact_kind == "HISTORICAL_FEATURE"
    )
    feature = component_repository.get(feature_reference)
    feature_value = feature.payload["features"][0]["values"][0]
    assert feature_value["source_bar_count"] >= 0
    assert feature_value["source_bar_lineage_hash"].startswith("sha256:")
    assert "source_bar_ids" not in feature_value
    assert "source_bar_hashes" not in feature_value
    pool_reference = next(
        item for item in partial.sessions[0].receipts[0].output_references if item.artifact_kind == "HISTORICAL_DYNAMIC_POOL"
    )
    pool = component_repository.get(pool_reference)
    security_coverage = pool.payload["historical_security_fact_coverage"]
    assert security_coverage["listing_date_available_count"] == len(STOCKS)
    assert security_coverage["listing_age_available_count"] == len(STOCKS)
    assert security_coverage["market_cap_available_count"] == len(STOCKS)
    assert security_coverage["industry_available_count"] == len(STOCKS)
    assert security_coverage["facts_owner_bound"] is True
    assert pool.payload["selective_reads"]
    assert any(read["selected_partitions"] for read in pool.payload["selective_reads"])
    for read in pool.payload["selective_reads"]:
        assert read["metrics"]["predicate_pushdown"] is True
        assert read["metrics"]["maximum_batch_row_count"] <= read["query"]["batch_size"]
        assert all(item["physical_checksum"].startswith("sha256:") for item in read["selected_partitions"])
    market_reference = next(
        item for item in partial.sessions[0].receipts[-1].output_references if item.artifact_kind == "HISTORICAL_MARKET_REGIME"
    )
    market = component_repository.get(market_reference)
    candidate_reference = next(
        item for item in partial.sessions[0].receipts[-1].output_references if item.artifact_kind == "HISTORICAL_CANDIDATE"
    )
    candidate = component_repository.get(candidate_reference)
    etf_reference = next(item for item in partial.sessions[0].receipts[-1].output_references if item.artifact_kind == "HISTORICAL_ETF")
    etf = component_repository.get(etf_reference)
    assert etf.payload["instrument_coverage"]["etf_available_count"] == 1
    assert etf.payload["instrument_coverage"]["index_available_count"] == 1
    assert etf.payload["benchmark_usage"] == {
        "market_regime": INDEX,
        "theme": ETF,
    }
    assert market.payload["market_state"] != "DATA_INSUFFICIENT"
    assert "MARKET_REGIME_DATA_INSUFFICIENT" not in market.payload["reason_codes"]
    assert len(candidate.payload["records"]) == len(STOCKS)
    assert signal.payload["signal_count"] == signal.payload["selected_candidate_count"]
    assert resumed.status is HistoricalRunStatus.COMPLETE
    assert resumed.sessions[0].receipts[-1].stage is ResearchSessionStage.PERFORMANCE
    assert resumed.sessions[0].receipts[-1].status is SessionStageStatus.COMPLETE
    assert {
        item.artifact_kind
        for item in resumed.sessions[0].receipts[-1].output_references
    } >= {
        "HISTORICAL_RESEARCH_PANEL",
        "HISTORICAL_RESEARCH_EVALUATION",
    }
    strategy_receipt = resumed.sessions[0].receipts[ResearchSessionStage.STRATEGY.ordinal - 1]
    assert {item.artifact_kind for item in strategy_receipt.output_references} >= {
        "HISTORICAL_STRATEGY",
        "MULTI_STRATEGY_CYCLE",
    }
    portfolio_receipt = resumed.sessions[0].receipts[ResearchSessionStage.PORTFOLIO.ordinal - 1]
    assert {item.artifact_kind for item in portfolio_receipt.output_references} >= {
        "HISTORICAL_PORTFOLIO",
        "CROSS_STRATEGY_PORTFOLIO",
    }
    strategy_cycle = strategy_repository.get_cycle_for_tick(
        run_id=command.run_id,
        tick_id=resumed.sessions[0].request.session_id,
    )
    assert {item.origin.value for item in strategy_cycle.runs} == {"HISTORICAL"}
    assert {strategy_repository.load_registry().family_for(item).value for item in strategy_cycle.runs} == {"OVERNIGHT", "SWING_STATE"}
    outcome_reference = next(
        item for item in resumed.sessions[0].receipts[-2].output_references if item.artifact_kind == "HISTORICAL_OUTCOME"
    )
    outcome = component_repository.get(outcome_reference)
    assert outcome.payload["available_label_count"] == (len(STOCKS) - 1) * 6
    assert outcome.payload["not_estimated_label_count"] == 6
    assert len(outcome.payload["labels"]) == len(STOCKS) * 6
    assert len(outcome.payload["strategy_economics"]) == (len(STOCKS) - 1) * 6
    assert outcome.payload["corporate_action_coverage"] == {
        "facts_owner_bound": True,
        "affected_symbol_count": 1,
        "action_fact_count": 1,
        "coverage_gap_count": 1,
        "incomplete_symbol_count": 1,
        "excluded_target_count": 6,
        "price_adjustment_basis": "RAW_UNADJUSTED_TRADABLE_PRICE_V1",
    }
    assert outcome.payload["selective_reads"]
    assert all(
        item["query"]["symbol_count"] <= len(STOCKS) and item["query"]["symbols_hash"].startswith("sha256:")
        for item in outcome.payload["selective_reads"]
    )
    for result in outcome.payload["strategy_economics"]:
        if result["net_return"] is not None:
            assert Decimal(result["net_return"]) == (Decimal(result["gross_return"]) - Decimal(result["cost_return"]))
    panel_reference = next(
        item
        for item in resumed.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_RESEARCH_PANEL"
    )
    panel = component_repository.get(panel_reference)
    evaluation_reference = next(
        item
        for item in resumed.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_RESEARCH_EVALUATION"
    )
    evaluation = GoldenLoopSessionEvaluation.from_canonical_dict(
        component_repository.get(evaluation_reference).payload
    )
    assert evaluation.portfolio_status == "NO_ACTION"
    assert evaluation.layer_diagnostics["candidate"]["observed_count"] == 0
    assert evaluation.layer_diagnostics["signal"]["observed_count"] == 0
    assert evaluation.layer_diagnostics["forecast"]["observed_count"] == 0
    assert panel.payload["row_count"] == len(STOCKS)
    assert panel.payload["missing_target_count"] == 1
    excluded = next(item for item in panel.payload["rows"] if item["symbol"] == STOCKS[0])
    assert excluded["target_status"] == "CORPORATE_ACTION_EXCLUDED"
    assert outcome.payload["corporate_action_exclusions"][0]["reason_code"] == ("CORPORATE_ACTION_COVERAGE_GAP_RAW_RETURN_NOT_ESTIMABLE")
    action_labels = tuple(TargetOutcomeLabel.from_canonical_dict(item) for item in outcome.payload["labels"] if item["symbol"] == STOCKS[0])
    assert all(item.availability_status is OutcomeAvailabilityStatus.UNAVAILABLE for item in action_labels)
    assert all("CORPORATE_ACTION_POLICY_FAILED_CLOSED" in item.reason_codes for item in action_labels)
    assert excluded["industry"] == "TEST_INDUSTRY"
    assert excluded["market_cap_bucket"] != "NOT_ESTIMABLE"
    assert excluded["signal_diagnostic"]["state"]
    assert excluded["forecast_diagnostic"]["status"]
    cache_metrics = materializer.window_cache_metrics()
    assert cache_metrics["daily_month_cache_entries"] <= cache_metrics["daily_month_cache_limit"]
    assert cache_metrics["minute_session_cache_entries"] <= cache_metrics["minute_session_cache_limit"]
    assert cache_metrics["physical_read_count"] >= 1
    assert cache_metrics["read_metric_objects_retained"] == 1
    assert len(materializer.selective_read_metrics()) == 1
    streamed = tuple(
        component
        for batch in component_repository.iter_for_run(
            run_id=command.run_id,
            batch_size=1,
        )
        for component in batch
    )
    assert streamed == component_repository.list_for_run(run_id=command.run_id)
    assert replay.matched is True
    evidence_repository = PostgresHistoricalEvidenceRepository(postgres_factory)
    produced = HistoricalEvidenceProducer(
        journal=journal,
        corpus_repository=corpus,
        component_repository=component_repository,
        evidence_repository=evidence_repository,
    ).produce(run_id=command.run_id)
    assert produced.observation_count == len(STOCKS) - 1
    assert {item.evidence_kind for item in produced.evidence} == {
        HistoricalEvidenceKind.CORPUS_SUMMARY,
        HistoricalEvidenceKind.ALPHA_ABLATION,
        HistoricalEvidenceKind.STRATEGY_ECONOMICS,
        HistoricalEvidenceKind.PORTFOLIO_PERFORMANCE,
        HistoricalEvidenceKind.METHODOLOGY_ASSESSMENT,
    }
    ablation = next(item for item in produced.evidence if item.evidence_kind is HistoricalEvidenceKind.ALPHA_ABLATION)
    assert ablation.classification is ResearchFinding.INCONCLUSIVE
    corpus_summary = next(item for item in produced.evidence if item.evidence_kind is HistoricalEvidenceKind.CORPUS_SUMMARY)
    assert corpus_summary.payload["diagnostics"]["corporate_action_excluded_count"] == 1
    assert corpus_summary.payload["diagnostics"]["signal_state_counts"]
    assert corpus_summary.payload["diagnostics"]["forecast_status_counts"]
    assert {metric.slice_kind for metric in corpus_summary.metrics if metric.metric_name == "observation_count"} >= {
        "FORECAST_STATUS",
        "MONTH",
        "SIGNAL_STATE",
        "TARGET_STATUS",
    }
    methodology = next(
        item
        for item in produced.evidence
        if item.evidence_kind is HistoricalEvidenceKind.METHODOLOGY_ASSESSMENT
    )
    assert methodology.payload["status"] == "METHODOLOGY_INVALIDATED"
    strategy_economics = next(
        item
        for item in produced.evidence
        if item.evidence_kind is HistoricalEvidenceKind.STRATEGY_ECONOMICS
    )
    assert strategy_economics.classification is ResearchFinding.NOT_ESTIMABLE
    assert strategy_economics.payload["canonical_cycle_portfolio_outcome_bound"] is True
    repeated = HistoricalEvidenceProducer(
        journal=journal,
        corpus_repository=corpus,
        component_repository=component_repository,
        evidence_repository=evidence_repository,
    ).produce(run_id=command.run_id)
    assert repeated.evidence == produced.evidence
    assert evidence_repository.list_for_run(command.run_id) == tuple(
        sorted(
            produced.evidence,
            key=lambda item: (item.evidence_kind.value, str(item.evidence_id)),
        )
    )


def test_materializer_switches_effective_dated_constituent_cohorts(
    postgres_factory,
    tmp_path: Path,
) -> None:
    universe_repository = PostgresFreeResearchUniverseRepository(postgres_factory)
    first = universe_repository.publish(
        _universe(
            effective_date=date(2022, 1, 1),
            stocks=("000001.SZ", "600000.SH"),
            identity="first",
        )
    )
    second = universe_repository.publish(
        _universe(
            effective_date=date(2022, 6, 13),
            stocks=("000002.SZ", "600036.SH"),
            identity="second",
        )
    )
    cohort_references = tuple(
        ValidationArtifactReference(
            FREE_RESEARCH_UNIVERSE_KIND,
            item.snapshot_id,
            item.snapshot_hash,
        )
        for item in (first, second)
    )
    timeline = universe_repository.publish_timeline(
        HistoricalConstituentTimeline.create(
            start_date=date(2022, 6, 1),
            end_date=date(2022, 6, 13),
            queried_trading_dates=(date(2022, 6, 10), date(2022, 6, 13)),
            query_effective_dates=(
                (date(2022, 6, 10), date(2022, 1, 1)),
                (date(2022, 6, 13), date(2022, 6, 13)),
            ),
            cohorts=(
                HistoricalConstituentCohort(date(2022, 1, 1), cohort_references[0]),
                HistoricalConstituentCohort(date(2022, 6, 13), cohort_references[1]),
            ),
            scan_source_manifest_reference=ValidationArtifactReference(
                "SOURCE_MANIFEST",
                ArtifactId("historical-cohort-timeline-source"),
                canonical_hash({"timeline": "source"}),
            ),
            raw_archive_id="historical-cohort-timeline-archive",
            known_at=MATERIALIZED_AT,
        )
    )
    references = tuple(
        sorted(
            (
                *cohort_references,
                timeline.reference,
            ),
            key=lambda item: (item.artifact_kind, str(item.artifact_id)),
        )
    )
    materializer = HistoricalDecisionMaterializer(
        run_id=ArtifactId("historical-run-cohort-switch"),
        corpus_repository=PostgresHistoricalCorpusRepository(
            postgres_factory,
            artifact_root=tmp_path / "artifact-root",
        ),
        component_repository=PostgresHistoricalMaterializationRepository(postgres_factory),
        universe_repository=universe_repository,
        scope_repository=PostgresRuntimeScopeRepository(postgres_factory),
        target_repository=PostgresTargetOutcomeRepository(postgres_factory),
    )

    active_first, first_reference = materializer._active_universe(  # noqa: SLF001
        references,
        date(2022, 6, 10),
    )
    active_second, second_reference = materializer._active_universe(  # noqa: SLF001
        references,
        date(2022, 6, 13),
    )

    assert active_first.snapshot_id == first.snapshot_id
    assert first_reference.artifact_id == first.snapshot_id
    assert {item.symbol for item in active_first.records} == {
        "000001.SZ",
        "600000.SH",
    }
    assert active_second.snapshot_id == second.snapshot_id
    assert second_reference.artifact_id == second.snapshot_id
    assert {item.symbol for item in active_second.records} == {
        "000002.SZ",
        "600036.SH",
    }
    legacy, legacy_reference = materializer._active_universe(  # noqa: SLF001
        (cohort_references[0],),
        date(2022, 6, 10),
    )
    assert legacy == first
    assert legacy_reference == cohort_references[0]
    with pytest.raises(ValueError, match="one exact constituent owner"):
        materializer._active_universe(  # noqa: SLF001
            cohort_references,
            date(2022, 6, 10),
        )
    with pytest.raises(ValueError, match="range/cohort lineage mismatch"):
        materializer._active_universe(references, date(2021, 12, 31))  # noqa: SLF001
    with pytest.raises(ValueError, match="absent from Historical constituent scan"):
        materializer._active_universe(references, date(2022, 6, 11))  # noqa: SLF001
    incomplete = tuple(item for item in references if item.artifact_id != second.snapshot_id)
    with pytest.raises(ValueError, match="range/cohort lineage mismatch"):
        materializer._active_universe(incomplete, date(2022, 6, 13))  # noqa: SLF001


def test_longitudinal_command_requires_historical_fact_owner() -> None:
    reference = ValidationArtifactReference(
        FREE_RESEARCH_UNIVERSE_KIND,
        ArtifactId("longitudinal-facts-required-universe"),
        canonical_hash({"longitudinal": "facts-required-universe"}),
    )
    timeline = ValidationArtifactReference(
        "HISTORICAL_CONSTITUENT_TIMELINE",
        ArtifactId("longitudinal-facts-required-timeline"),
        canonical_hash({"longitudinal": "facts-required-timeline"}),
    )
    command = _command(
        ValidationArtifactReference(
            "NORMALIZED_DATASET",
            ArtifactId("longitudinal-facts-required-dataset"),
            canonical_hash({"longitudinal": "facts-required-dataset"}),
        ),
        reference,
        timeline,
        ArtifactId("longitudinal-facts-required-policy"),
        canonical_hash({"longitudinal": "facts-required-policy"}),
        ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            ArtifactId("longitudinal-facts-required-target"),
            canonical_hash({"longitudinal": "facts-required-target"}),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Longitudinal Historical Research requires",
    ):
        _historical_facts_reference(command.session_request(DECISION_DATE))


def _normalized_owner(
    raw_reference: ValidationArtifactReference,
) -> HistoricalDataOwner:
    records: list[HistoricalNormalizedBar] = []
    start = DECISION_DATE - timedelta(days=75)
    symbols = (*STOCKS, INDEX, ETF)
    for symbol_index, symbol in enumerate(symbols):
        price = Decimal("10") + Decimal(symbol_index)
        for index in range(70):
            market_date = start + timedelta(days=index)
            close = price * (Decimal("1.002") ** index)
            volume = Decimal(1_000_000 + symbol_index * 100_000 + index * 10_000)
            event_start = datetime.combine(market_date, time(1, 30), tzinfo=UTC)
            records.append(
                HistoricalNormalizedBar.create(
                    symbol=symbol,
                    timeframe=Timeframe.DAILY,
                    market_date=market_date,
                    event_start=event_start,
                    event_end=event_start + timedelta(hours=5, minutes=30),
                    retrieved_at=DATA_RETRIEVED_AT,
                    open=close * Decimal("0.999"),
                    high=close * Decimal("1.004"),
                    low=close * Decimal("0.996"),
                    close=close,
                    volume=volume,
                    amount=volume * close,
                    adjustment_basis="RAW_UNADJUSTED",
                    trading_status=HistoricalTradingStatus.TRADING,
                    st_status=False,
                    listing_status=HistoricalListingStatus.UNKNOWN,
                    raw_request_reference=ValidationArtifactReference(
                        "RAW_PROVIDER_REQUEST",
                        ArtifactId(f"raw-request-{symbol_index}"),
                        canonical_hash({"raw": symbol_index}),
                    ),
                    raw_row_number=index + 1,
                    missing_fields=("listing_status",),
                    limitations=("PIT_INCOMPLETE",),
                )
            )
        prior_close = price * (Decimal("1.002") ** 69)
        prior_intraday_date = DECISION_DATE - timedelta(days=1)
        prior_intraday_starts = tuple(
            datetime.combine(prior_intraday_date, time(1, 30), tzinfo=UTC) + timedelta(minutes=5 * index) for index in range(24)
        ) + tuple(datetime.combine(prior_intraday_date, time(5, 0), tzinfo=UTC) + timedelta(minutes=5 * index) for index in range(24))
        for minute_index, event_start in enumerate(prior_intraday_starts):
            close = prior_close * (Decimal("0.995") + Decimal(minute_index + 1) / Decimal("20000"))
            volume = Decimal(15_000 + symbol_index * 500 + minute_index * 50)
            records.append(
                HistoricalNormalizedBar.create(
                    symbol=symbol,
                    timeframe=Timeframe.MINUTE_5,
                    market_date=prior_intraday_date,
                    event_start=event_start,
                    event_end=event_start + timedelta(minutes=5),
                    retrieved_at=DATA_RETRIEVED_AT,
                    open=close * Decimal("0.9999"),
                    high=close * Decimal("1.0005"),
                    low=close * Decimal("0.9995"),
                    close=close,
                    volume=volume,
                    amount=volume * close,
                    adjustment_basis="RAW_UNADJUSTED",
                    trading_status=HistoricalTradingStatus.TRADING,
                    st_status=None,
                    listing_status=HistoricalListingStatus.UNKNOWN,
                    raw_request_reference=ValidationArtifactReference(
                        "RAW_PROVIDER_REQUEST",
                        ArtifactId(f"raw-request-{symbol_index}"),
                        canonical_hash({"raw": symbol_index}),
                    ),
                    raw_row_number=500 + minute_index,
                    missing_fields=("listing_status", "st_status"),
                    limitations=("PIT_INCOMPLETE",),
                )
            )
        for minute_index in range(66):
            event_start = datetime.combine(
                DECISION_DATE,
                time(1, 30),
                tzinfo=UTC,
            ) + timedelta(minutes=5 * minute_index)
            close = prior_close * (Decimal("1") + Decimal(minute_index + 1) / Decimal("10000"))
            volume = Decimal(25_000 + symbol_index * 1_000 + minute_index * 100)
            records.append(
                HistoricalNormalizedBar.create(
                    symbol=symbol,
                    timeframe=Timeframe.MINUTE_5,
                    market_date=DECISION_DATE,
                    event_start=event_start,
                    event_end=event_start + timedelta(minutes=5),
                    retrieved_at=DATA_RETRIEVED_AT,
                    open=close * Decimal("0.9999"),
                    high=close * Decimal("1.0005"),
                    low=close * Decimal("0.9995"),
                    close=close,
                    volume=volume,
                    amount=volume * close,
                    adjustment_basis="RAW_UNADJUSTED",
                    trading_status=HistoricalTradingStatus.TRADING,
                    st_status=None,
                    listing_status=HistoricalListingStatus.UNKNOWN,
                    raw_request_reference=ValidationArtifactReference(
                        "RAW_PROVIDER_REQUEST",
                        ArtifactId(f"raw-request-{symbol_index}"),
                        canonical_hash({"raw": symbol_index}),
                    ),
                    raw_row_number=1000 + minute_index,
                    missing_fields=("listing_status", "st_status"),
                    limitations=("PIT_INCOMPLETE",),
                )
            )
        next_date = DECISION_DATE + timedelta(days=1)
        next_close = prior_close * Decimal("1.01")
        next_start = datetime.combine(next_date, time(1, 30), tzinfo=UTC)
        records.append(
            HistoricalNormalizedBar.create(
                symbol=symbol,
                timeframe=Timeframe.DAILY,
                market_date=next_date,
                event_start=next_start,
                event_end=next_start + timedelta(hours=5, minutes=30),
                retrieved_at=DATA_RETRIEVED_AT,
                open=prior_close * Decimal("1.001"),
                high=prior_close * Decimal("1.02"),
                low=prior_close * Decimal("0.995"),
                close=next_close,
                volume=Decimal("2000000"),
                amount=Decimal("2000000") * next_close,
                adjustment_basis="RAW_UNADJUSTED",
                trading_status=HistoricalTradingStatus.TRADING,
                st_status=False,
                listing_status=HistoricalListingStatus.UNKNOWN,
                raw_request_reference=ValidationArtifactReference(
                    "RAW_PROVIDER_REQUEST",
                    ArtifactId(f"raw-request-{symbol_index}"),
                    canonical_hash({"raw": symbol_index}),
                ),
                raw_row_number=2000,
                missing_fields=("listing_status",),
                limitations=("PIT_INCOMPLETE",),
            )
        )
        starts = tuple(datetime.combine(next_date, time(1, 30), tzinfo=UTC) + timedelta(minutes=5 * index) for index in range(24)) + tuple(
            datetime.combine(next_date, time(5, 0), tzinfo=UTC) + timedelta(minutes=5 * index) for index in range(24)
        )
        for minute_index, event_start in enumerate(starts):
            close = prior_close * (Decimal("1.001") + Decimal(minute_index + 1) / Decimal("10000"))
            records.append(
                HistoricalNormalizedBar.create(
                    symbol=symbol,
                    timeframe=Timeframe.MINUTE_5,
                    market_date=next_date,
                    event_start=event_start,
                    event_end=event_start + timedelta(minutes=5),
                    retrieved_at=DATA_RETRIEVED_AT,
                    open=close * Decimal("0.9999"),
                    high=close * Decimal("1.0005"),
                    low=close * Decimal("0.9995"),
                    close=close,
                    volume=Decimal("30000"),
                    amount=Decimal("30000") * close,
                    adjustment_basis="RAW_UNADJUSTED",
                    trading_status=HistoricalTradingStatus.TRADING,
                    st_status=None,
                    listing_status=HistoricalListingStatus.UNKNOWN,
                    raw_request_reference=ValidationArtifactReference(
                        "RAW_PROVIDER_REQUEST",
                        ArtifactId(f"raw-request-{symbol_index}"),
                        canonical_hash({"raw": symbol_index}),
                    ),
                    raw_row_number=3000 + minute_index,
                    missing_fields=("listing_status", "st_status"),
                    limitations=("PIT_INCOMPLETE",),
                )
            )
    ordered = tuple(records)
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=ordered,
        bucket_count=4,
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id="provider-baostock-public",
        normalization_version="phase-e-normalization/v1",
        parent_reference=raw_reference,
        created_at=MATERIALIZED_AT,
        retrieved_at=DATA_RETRIEVED_AT,
        first_market_date=min(item.market_date for item in ordered),
        last_market_date=max(item.market_date for item in ordered),
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=tuple(sorted(symbols)),
            observed_symbols=tuple(sorted(symbols)),
            expected_request_count=len(symbols) * 2,
            successful_request_count=len(symbols) * 2,
            source_row_count=len(ordered),
            normalized_row_count=len(ordered),
            missing_field_counts=(("listing_status", len(ordered)),),
            failure_counts=(),
        ),
    )


def _universe(
    *,
    effective_date: date = DECISION_DATE,
    stocks: tuple[str, ...] = STOCKS,
    identity: str = "phase-e",
):
    return build_historical_constituent_universe_snapshot(
        effective_date=effective_date,
        known_at=MATERIALIZED_AT,
        provider_id="provider-baostock-public",
        provider_contract="baostock-historical-constituent/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId(f"phase-e-security-master-manifest-{identity}"),
            canonical_hash({"security-master": identity}),
        ),
        constituent_source_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST",
            ArtifactId(f"phase-e-historical-constituents-{identity}"),
            canonical_hash({"constituents": identity}),
        ),
        raw_archive_id=f"phase-e-security-master-raw-{identity}",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        constituent_rows=tuple(
            {
                "code": f"{symbol[-2:].lower()}.{symbol[:6]}",
                "code_name": symbol,
                "updateDate": effective_date.isoformat(),
            }
            for symbol in stocks
        ),
        security_master_rows=tuple(
            {
                "code": f"{symbol[-2:].lower()}.{symbol[:6]}",
                "code_name": symbol,
                "ipoDate": "2000-01-01",
                "outDate": "",
                "type": "1",
                "status": "1",
            }
            for symbol in stocks
        ),
    )


def _policy():
    return build_research_universe_policy(
        policy_version="phase-e-test/v1",
        selectors=(
            UniversePolicySelector(
                kind=UniverseScopeKind.INDEX,
                selector_id="phase-e-historical-constituent-scope",
                symbols=(),
            ),
        ),
        minimum_history_sessions=60,
        minimum_median_daily_amount=Decimal("1000000"),
        include_st=False,
        require_tradable=True,
        lot_size=100,
        data_authority="FREE_RESEARCH_ARCHIVE_PIT_INCOMPLETE",
    )


def _command(
    normalized: ValidationArtifactReference,
    universe: ValidationArtifactReference,
    timeline: ValidationArtifactReference,
    policy_id: ArtifactId,
    policy_hash: str,
    target_protocol: ValidationArtifactReference,
    facts: ValidationArtifactReference | None = None,
    context: ValidationArtifactReference | None = None,
    experiment: ValidationArtifactReference | None = None,
    methodology_references: tuple[ValidationArtifactReference, ...] = (),
) -> HistoricalResearchCommand:
    evidence_hash = canonical_hash({"phase-e": "integration"})
    return HistoricalResearchCommand.create(
        idempotency_key="phase-e-decision-materializer-integration-v1",
        start_date=DECISION_DATE,
        end_date=DECISION_DATE,
        trading_sessions=(DECISION_DATE,),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        trading_calendar_id=ArtifactId("phase-e-calendar"),
        trading_calendar_hash=evidence_hash,
        runtime_scope_policy_id=policy_id,
        runtime_scope_policy_hash=policy_hash,
        decision_policy_id=ArtifactId("phase-e-decision-policy"),
        decision_policy_hash=evidence_hash,
        target_protocol_reference=target_protocol,
        experiment_definition_reference=(
            experiment
            if experiment is not None
            else ValidationArtifactReference(
                "RESEARCH_EXPERIMENT_DEFINITION",
                ArtifactId("phase-e-experiment"),
                evidence_hash,
            )
        ),
        configuration_references=(
            normalized,
            universe,
            timeline,
            *methodology_references,
            *((facts,) if facts is not None else ()),
            *((context,) if context is not None else ()),
        ),
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        code_revision="phase-e-integration",
        created_at=MATERIALIZED_AT,
    )


def _historical_facts(
    scope_references: tuple[ValidationArtifactReference, ...],
) -> HistoricalSecurityFactsOwner:
    source = ValidationArtifactReference(
        "RAW_PROVIDER_REQUEST",
        ArtifactId("phase-e-historical-facts-source"),
        canonical_hash({"phase-e": "historical-facts-source"}),
    )
    facts: list[HistoricalSecurityFact] = []
    for symbol in STOCKS:
        facts.extend(
            (
                HistoricalSecurityFact.create(
                    fact_kind=HistoricalSecurityFactKind.INDUSTRY,
                    symbol=symbol,
                    effective_date=DECISION_DATE - timedelta(days=30),
                    published_date=None,
                    values={
                        "industry": "TEST_INDUSTRY",
                        "classification": "TEST_CLASSIFICATION",
                    },
                    source_reference=source,
                ),
                HistoricalSecurityFact.create(
                    fact_kind=HistoricalSecurityFactKind.SHARE_CAPITAL,
                    symbol=symbol,
                    effective_date=DECISION_DATE - timedelta(days=90),
                    published_date=DECISION_DATE - timedelta(days=10),
                    values={
                        "total_shares": "1000000000",
                        "liquid_shares": "800000000",
                    },
                    source_reference=source,
                ),
            )
        )
    facts.append(
        HistoricalSecurityFact.create(
            fact_kind=HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
            symbol=STOCKS[0],
            effective_date=DECISION_DATE + timedelta(days=1),
            published_date=None,
            values={
                "adjustment_factor": "1.1",
                "back_adjust_factor": "1.1",
                "forward_adjust_factor": "0.9",
            },
            source_reference=source,
        )
    )
    return HistoricalSecurityFactsOwner.create(
        known_at=MATERIALIZED_AT,
        provider_id="provider-baostock-public",
        provider_contracts=("baostock-historical-facts-test/v1",),
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("phase-e-historical-facts-manifest"),
            canonical_hash({"phase-e": "historical-facts-manifest"}),
        ),
        raw_archive_id="phase-e-historical-facts-archive",
        facts=tuple(facts),
        requested_symbols=STOCKS,
        acquisition_start_date=DECISION_DATE,
        acquisition_end_date=DECISION_DATE + timedelta(days=1),
        universe_scope_references=scope_references,
        coverage_gaps=(
            HistoricalSecurityFactCoverageGap.create(
                fact_kind=HistoricalSecurityFactKind.DIVIDEND_EVENT,
                symbol=STOCKS[0],
                coverage_start=DECISION_DATE,
                coverage_end=DECISION_DATE + timedelta(days=1),
                raw_row_hash=canonical_hash({"unresolved": STOCKS[0]}),
                source_reference=source,
                reason_codes=("CORPORATE_ACTION_PROVIDER_ROW_UNRESOLVED",),
            ),
        ),
    )
