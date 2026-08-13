from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

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
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.evidence_producer import (
    HistoricalEvidenceProducer,
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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
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
    scope_repository = PostgresRuntimeScopeRepository(postgres_factory)
    policy = scope_repository.register_policy(_policy())
    target_repository = PostgresTargetOutcomeRepository(postgres_factory)
    target_protocol = target_repository.register_protocol(
        exploratory_five_minute_multi_horizon_protocol(),
        recorded_at=MATERIALIZED_AT,
    )
    command = _command(
        normalized.reference,
        ValidationArtifactReference(
            FREE_RESEARCH_UNIVERSE_KIND,
            universe.snapshot_id,
            universe.snapshot_hash,
        ),
        policy.policy_id,
        policy.policy_hash,
        ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
    )
    journal = PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(MATERIALIZED_AT),
    )
    component_repository = PostgresHistoricalMaterializationRepository(
        postgres_factory
    )
    materializer = HistoricalDecisionMaterializer(
        run_id=command.run_id,
        corpus_repository=corpus,
        component_repository=component_repository,
        universe_repository=universe_repository,
        scope_repository=scope_repository,
        target_repository=target_repository,
    )
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(
            PostgresHistoricalSessionOwner(
                postgres_factory,
                archive_materializer=materializer,
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
    decision_kinds = {
        item.artifact_kind
        for item in partial.sessions[0].receipts[-1].output_references
    }
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
        item
        for item in partial.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_SIGNAL"
    )
    signal = component_repository.get(signal_reference)
    feature_reference = next(
        item
        for item in partial.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_FEATURE"
    )
    feature = component_repository.get(feature_reference)
    feature_value = feature.payload["features"][0]["values"][0]
    assert feature_value["source_bar_count"] >= 0
    assert feature_value["source_bar_lineage_hash"].startswith("sha256:")
    assert "source_bar_ids" not in feature_value
    assert "source_bar_hashes" not in feature_value
    pool_reference = next(
        item
        for item in partial.sessions[0].receipts[0].output_references
        if item.artifact_kind == "HISTORICAL_DYNAMIC_POOL"
    )
    pool = component_repository.get(pool_reference)
    security_coverage = pool.payload["historical_security_fact_coverage"]
    assert security_coverage["listing_date_available_count"] == len(STOCKS)
    assert security_coverage["listing_age_available_count"] == len(STOCKS)
    assert security_coverage["market_cap_status"] == "NOT_ESTIMABLE"
    assert security_coverage["industry_status"] == "UNKNOWN"
    assert pool.payload["selective_reads"]
    assert any(read["selected_partitions"] for read in pool.payload["selective_reads"])
    for read in pool.payload["selective_reads"]:
        assert read["metrics"]["predicate_pushdown"] is True
        assert read["metrics"]["maximum_batch_row_count"] <= read["query"]["batch_size"]
        assert all(
            item["physical_checksum"].startswith("sha256:")
            for item in read["selected_partitions"]
        )
    market_reference = next(
        item
        for item in partial.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_MARKET_REGIME"
    )
    market = component_repository.get(market_reference)
    candidate_reference = next(
        item
        for item in partial.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_CANDIDATE"
    )
    candidate = component_repository.get(candidate_reference)
    etf_reference = next(
        item
        for item in partial.sessions[0].receipts[-1].output_references
        if item.artifact_kind == "HISTORICAL_ETF"
    )
    etf = component_repository.get(etf_reference)
    assert etf.payload["instrument_coverage"]["etf_available_count"] == 1
    assert etf.payload["instrument_coverage"]["index_available_count"] == 0
    assert market.payload["market_state"] != "DATA_INSUFFICIENT"
    assert "MARKET_REGIME_DATA_INSUFFICIENT" not in market.payload["reason_codes"]
    assert len(candidate.payload["records"]) == len(STOCKS)
    assert signal.payload["signal_count"] == signal.payload["selected_candidate_count"]
    assert resumed.status is HistoricalRunStatus.COMPLETE
    assert resumed.sessions[0].receipts[-1].stage is ResearchSessionStage.PERFORMANCE
    assert resumed.sessions[0].receipts[-1].status is SessionStageStatus.COMPLETE
    outcome_reference = next(
        item
        for item in resumed.sessions[0].receipts[-2].output_references
        if item.artifact_kind == "HISTORICAL_OUTCOME"
    )
    outcome = component_repository.get(outcome_reference)
    assert outcome.payload["available_label_count"] == len(STOCKS) * 6
    assert len(outcome.payload["strategy_economics"]) == len(STOCKS) * 6
    for result in outcome.payload["strategy_economics"]:
        if result["net_return"] is not None:
            assert Decimal(result["net_return"]) == (
                Decimal(result["gross_return"]) - Decimal(result["cost_return"])
            )
    panel_reference = resumed.sessions[0].receipts[-1].output_references[0]
    panel = component_repository.get(panel_reference)
    assert panel.payload["row_count"] == len(STOCKS)
    assert panel.payload["missing_target_count"] == 0
    assert replay.matched is True
    evidence_repository = PostgresHistoricalEvidenceRepository(postgres_factory)
    produced = HistoricalEvidenceProducer(
        journal=journal,
        corpus_repository=corpus,
        component_repository=component_repository,
        evidence_repository=evidence_repository,
    ).produce(run_id=command.run_id)
    assert produced.observation_count == len(STOCKS)
    assert {item.evidence_kind for item in produced.evidence} == {
        HistoricalEvidenceKind.CORPUS_SUMMARY,
        HistoricalEvidenceKind.ALPHA_ABLATION,
        HistoricalEvidenceKind.STRATEGY_ECONOMICS,
        HistoricalEvidenceKind.PORTFOLIO_PERFORMANCE,
        HistoricalEvidenceKind.EXPLORATORY_MODEL,
    }
    ablation = next(
        item
        for item in produced.evidence
        if item.evidence_kind is HistoricalEvidenceKind.ALPHA_ABLATION
    )
    assert ablation.classification is ResearchFinding.INCONCLUSIVE
    model = next(
        item
        for item in produced.evidence
        if item.evidence_kind is HistoricalEvidenceKind.EXPLORATORY_MODEL
    )
    assert model.classification is ResearchFinding.NOT_ESTIMABLE
    assert model.payload["owner_resolved_training_matrix"] is True
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


def _normalized_owner(
    raw_reference: ValidationArtifactReference,
) -> HistoricalDataOwner:
    records: list[HistoricalNormalizedBar] = []
    start = DECISION_DATE - timedelta(days=75)
    symbols = (*STOCKS, ETF)
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
            datetime.combine(prior_intraday_date, time(1, 30), tzinfo=UTC)
            + timedelta(minutes=5 * index)
            for index in range(24)
        ) + tuple(
            datetime.combine(prior_intraday_date, time(5, 0), tzinfo=UTC)
            + timedelta(minutes=5 * index)
            for index in range(24)
        )
        for minute_index, event_start in enumerate(prior_intraday_starts):
            close = prior_close * (
                Decimal("0.995")
                + Decimal(minute_index + 1) / Decimal("20000")
            )
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
        starts = tuple(
            datetime.combine(next_date, time(1, 30), tzinfo=UTC)
            + timedelta(minutes=5 * index)
            for index in range(24)
        ) + tuple(
            datetime.combine(next_date, time(5, 0), tzinfo=UTC)
            + timedelta(minutes=5 * index)
            for index in range(24)
        )
        for minute_index, event_start in enumerate(starts):
            close = prior_close * (
                Decimal("1.001")
                + Decimal(minute_index + 1) / Decimal("10000")
            )
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


def _universe():
    return build_historical_constituent_universe_snapshot(
        effective_date=DECISION_DATE,
        known_at=MATERIALIZED_AT,
        provider_id="provider-baostock-public",
        provider_contract="baostock-historical-constituent/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("phase-e-security-master-manifest"),
            canonical_hash({"security-master": "phase-e"}),
        ),
        constituent_source_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST",
            ArtifactId("phase-e-historical-constituents"),
            canonical_hash({"constituents": "phase-e"}),
        ),
        raw_archive_id="phase-e-security-master-raw",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        constituent_rows=tuple(
            {
                "code": f"{symbol[-2:].lower()}.{symbol[:6]}",
                "code_name": symbol,
                "updateDate": DECISION_DATE.isoformat(),
            }
            for symbol in STOCKS
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
            for symbol in STOCKS
        ),
    )


def _policy():
    return build_research_universe_policy(
        policy_version="phase-e-test/v1",
        selectors=(
            UniversePolicySelector(
                kind=UniverseScopeKind.FULL_A,
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
    policy_id: ArtifactId,
    policy_hash: str,
    target_protocol: ValidationArtifactReference,
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
        experiment_definition_reference=ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            ArtifactId("phase-e-experiment"),
            evidence_hash,
        ),
        configuration_references=(normalized, universe),
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        code_revision="phase-e-integration",
        created_at=MATERIALIZED_AT,
    )
