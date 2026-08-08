from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.research_input import (
    ControlledOperationalResearchInput,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    ControlledPlatformResearchRunner,
    load_verified_controlled_research_artifact,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.application.operational_research.contracts import MissingEvidence
from market_regime_alpha.application.research_layer.runner import PlatformResearchRunner
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
)
from market_regime_alpha.features.materialization_v2 import load_verified_feature_bundle_v2
from market_regime_alpha.features.operational_overlay import StaticUniverseFeatureBundle
from market_regime_alpha.features.technical.catalog import static_technical_feature_set
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    load_verified_market_data_dataset,
    publish_market_data_dataset,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSelectionStatus,
)
from market_regime_alpha.universe import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from tests.application.operational_research.test_bridge import _supplemental
from tests.daily_decision.conftest import (
    DailyDecisionFixture,
    daily_decision_fixture,
)
from tests.postgres_path_repositories import feature_repository_factory


_daily_decision_fixture = daily_decision_fixture


UTC = timezone.utc
HASH = "sha256:" + "9" * 64


def _static_inputs(tmp_path: Path, fixture: DailyDecisionFixture):
    supplemental = _supplemental(fixture)
    decision = supplemental.decision_time.value.astimezone(UTC).replace(microsecond=0)
    symbols = tuple(sorted(item.symbol for item in supplemental.symbol_observations))
    bars = tuple(
        CanonicalMarketBar.create(
            symbol=symbol,
            exchange=Exchange(symbol[-2:]),
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.DAILY,
            market_date=(decision - timedelta(days=40 - index)).date(),
            event_start=datetime.combine(
                (decision - timedelta(days=40 - index)).date(),
                time(1, 30),
                tzinfo=UTC,
            ),
            event_end=datetime.combine(
                (decision - timedelta(days=40 - index)).date(),
                time(7),
                tzinfo=UTC,
            ),
            available_at=datetime.combine(
                (decision - timedelta(days=40 - index)).date(),
                time(7, 1),
                tzinfo=UTC,
            ),
            open=Decimal("10") + Decimal(index) / 100,
            high=Decimal("10.2") + Decimal(index) / 100,
            low=Decimal("9.8") + Decimal(index) / 100,
            close=Decimal("10.1") + Decimal(index) / 100,
            previous_close=(Decimal("10") + Decimal(index - 1) / 100 if index else None),
            volume=Decimal(1_000_000 + index * 10_000),
            volume_unit=VolumeUnit.SHARES,
            amount=(Decimal("10.1") + Decimal(index) / 100)
            * Decimal(1_000_000 + index * 10_000),
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=ArtifactId(f"daily-source-{symbol}-{index}"),
            source_content_hash=HASH,
        )
        for symbol in symbols
        for index in range(35)
    )
    dataset_artifact = MarketDataDatasetArtifact.create(
        decision_time=decision,
        created_at=supplemental.created_at.astimezone(UTC).replace(microsecond=0),
        bars=bars,
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.DAILY,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="controlled-test-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (supplemental.source_manifest.source_manifest_id, supplemental.source_manifest.content_hash),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    dataset_path = publish_market_data_dataset(root=tmp_path / "daily", artifact=dataset_artifact)
    dataset = load_verified_market_data_dataset(dataset_path)
    universe_source = ArtifactId("controlled-universe-source")
    universe = OperationalUniverseArtifact.create(
        decision_date=decision.date(),
        effective_at=decision - timedelta(hours=1),
        available_at=decision - timedelta(minutes=30),
        records=tuple(
            OperationalUniverseRecord(
                symbol=symbol,
                asset_type=AssetType.A_SHARE,
                exchange=Exchange(symbol[-2:]),
                membership_source="CONTROLLED_RECORDED_FIXTURE",
                listing_status=ListingStatus.LISTED,
                st_status=STStatus.NOT_ST,
                suspension_status=SuspensionStatus.NOT_SUSPENDED,
                liquidity_evidence=OperationalLiquidityEvidence(
                    lookback_sessions=20,
                    observed_sessions=20,
                    median_daily_amount=Decimal("100000000"),
                    minimum_daily_amount=Decimal("50000000"),
                    available_at=decision - timedelta(minutes=31),
                    source_artifact_id=universe_source,
                    source_content_hash=HASH,
                ),
                history_sessions_observed=250,
                history_sessions_required=250,
                included=True,
                inclusion_reasons=("CONTROLLED_FIXTURE_ELIGIBLE",),
                exclusion_reasons=(),
                source_artifact_references=((universe_source, HASH),),
                data_eligibility=DataEligibility.EXPLORATORY,
            )
            for symbol in symbols
        ),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=((universe_source, HASH),),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    feature_set = static_technical_feature_set(
        effective_from=decision - timedelta(days=100)
    )
    receipt = FeatureMaterializationRunner(
        max_workers=2,
        repository_factory=feature_repository_factory(
            tmp_path / "features.postgres-scope",
            fallback_clock=lambda: supplemental.created_at,
        ),
    ).run(
        verified_dataset=dataset,
        feature_set=feature_set,
        decision_time=decision,
        created_at=supplemental.created_at.astimezone(UTC).replace(microsecond=0),
        selected_symbols=symbols,
        code_revision="controlled-research-test",
        output_root=tmp_path / "features",
        idempotency_key="controlled-static",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    verified_features = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    static = StaticUniverseFeatureBundle.create(
        universe=universe,
        daily_dataset=dataset,
        feature_bundle=verified_features,
        run_receipt=receipt,
        code_revision="controlled-research-test",
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental", bundle=supplemental
    )
    verified_supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    return universe, static, verified_features, verified_supplemental


def test_controlled_platform_research_uses_static_features_and_no_prediction_runs(
    tmp_path: Path, daily_decision_fixture: DailyDecisionFixture
) -> None:
    universe, static, verified_features, supplemental = _static_inputs(
        tmp_path, daily_decision_fixture
    )
    inputs = ControlledOperationalResearchInput.create(
        operational_universe=universe,
        static_feature_bundle=static,
        supplemental_evidence=supplemental,
    )
    configuration = ControlledResearchPipelineConfig.create(
        candidate_discovery=ControlledCandidateDiscoveryConfig.create(
            top_n=1,
            minimum_candidate_population=1,
        )
    )

    verified = PlatformResearchRunner().run_controlled(
        inputs=inputs,
        static_feature_bundle=verified_features,
        configuration=configuration,
        output_root=tmp_path / "research",
        code_revision="controlled-research-test",
    )

    artifact = verified.artifact
    assert artifact.candidate_set.selected
    assert all(
        item.selection_status
        in {
            CandidateSelectionStatus.SELECTED,
            CandidateSelectionStatus.WATCHLIST,
            CandidateSelectionStatus.REJECTED,
            CandidateSelectionStatus.DATA_INSUFFICIENT,
        }
        for item in artifact.candidate_set.records
    )
    assert "B0_B1_PREDICTION_RUNS_NOT_USED" in artifact.limitations
    assert "prediction_runs" not in artifact.inputs.to_canonical_dict()
    assert all(
        "prediction" not in str(artifact_id).lower()
        for artifact_id in artifact.candidate_set.envelope.input_artifact_ids
    )
    loaded = load_verified_controlled_research_artifact(verified.root)
    assert loaded.artifact == artifact
    assert ControlledPlatformResearchRunner().replay(
        path=verified.root,
        static_feature_bundle=verified_features,
    ).artifact == artifact


def test_controlled_research_preserves_typed_missing_theme_evidence_as_fail_closed(
    tmp_path: Path, daily_decision_fixture: DailyDecisionFixture
) -> None:
    universe, static, verified_features, supplemental = _static_inputs(
        tmp_path, daily_decision_fixture
    )
    incomplete = replace(
        supplemental.bundle,
        theme_observations=(),
        capital_observations=(),
        theme_memberships=(),
        etf_theme_mappings=(),
        etf_observations=(),
        missing_evidence=tuple(
            MissingEvidence(
                evidence_kind="THEME_MEMBERSHIP",
                key=symbol,
                reason_codes=("FREE_DATA_THEME_MEMBERSHIP_NOT_PROVIDED",),
            )
            for symbol in universe.symbols
        )
        + (
            MissingEvidence(
                evidence_kind="THEME_OBSERVATION",
                key="ALL_THEMES",
                reason_codes=("THEME_COMPONENT_EVIDENCE_NOT_PROVIDED",),
            ),
            MissingEvidence(
                evidence_kind="CAPITAL_OBSERVATION",
                key="ALL_THEMES",
                reason_codes=("OBSERVABLE_THEME_CAPITAL_PROXY_NOT_PROVIDED",),
            ),
        ),
        reason_codes=tuple(
            dict.fromkeys((*supplemental.bundle.reason_codes, "SUPPLEMENTAL_EVIDENCE_INCOMPLETE"))
        ),
    )
    incomplete_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental-incomplete",
        bundle=incomplete,
    )
    inputs = ControlledOperationalResearchInput.create(
        operational_universe=universe,
        static_feature_bundle=static,
        supplemental_evidence=load_verified_supplemental_research_evidence(
            incomplete_path
        ),
    )

    verified = PlatformResearchRunner().run_controlled(
        inputs=inputs,
        static_feature_bundle=verified_features,
        configuration=ControlledResearchPipelineConfig.create(
            candidate_discovery=ControlledCandidateDiscoveryConfig.create(
                top_n=1,
                minimum_candidate_population=1,
            )
        ),
        output_root=tmp_path / "research-incomplete",
        code_revision="controlled-research-test",
    )

    assert verified.artifact.candidate_set.selected == ()
    assert all(
        "THEME_MEMBERSHIP_MISSING" in item.reason_codes
        or "MARKET_REGIME_PROHIBITS_RISK" in item.reason_codes
        for item in verified.artifact.candidate_set.records
    )
    assert "SUPPLEMENTAL_EVIDENCE_INCOMPLETE" in verified.artifact.limitations
