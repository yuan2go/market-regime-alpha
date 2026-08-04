from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ProviderId,
    UniverseId,
)
from market_regime_alpha.core.time import (
    AsOfTime,
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision.snapshot import DecisionPriceSnapshot
from market_regime_alpha.research.platform_v2.inputs import (
    MarketObservation,
    ResearchEvidenceKind,
    ResearchInputBundle,
)
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilityRecord,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
    UniverseMembershipRecord,
)
from tests.daily_decision.conftest import daily_decision_fixture


__all__ = ["daily_decision_fixture", "research_input_bundle"]


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 29, 14, 55, tzinfo=SHANGHAI)


@pytest.fixture
def research_input_bundle() -> ResearchInputBundle:
    decision_time = DecisionTime(DECISION_AT)
    source_manifest = SourceManifest(
        provider_profile_id="public-composite-replay-v1",
        decision_time=decision_time,
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=ArtifactId("fixture-source-artifact"),
                provider_id=ProviderId("provider-fixture"),
                retrieved_at=RetrievedAt(DECISION_AT),
                content_hash="sha256:" + "0" * 64,
                locator="fixture://research-input",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=("FIXTURE_RESEARCH_INPUT",),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    universe = PITUniverseSnapshot(
        universe_id=UniverseId("fixture-universe"),
        as_of=AsOfTime(DECISION_AT),
        source_dataset_id=DatasetId("fixture-universe-dataset"),
        evidence_artifact_id=ArtifactId("fixture-universe-artifact"),
        method_version="fixture-v1",
        records=tuple(
            UniverseMembershipRecord(symbol=f"60000{i}.SH", is_member=True)
            for i in range(1, 7)
        ),
    )
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(DECISION_AT),
        source_dataset_id=universe.source_dataset_id,
        evidence_artifact_id=ArtifactId("fixture-eligibility-artifact"),
        records=tuple(
            TradingEligibilityRecord(
                symbol=record.symbol,
                status=TradingEligibilityStatus.ELIGIBLE,
            )
            for record in universe.records
        ),
    )
    decision_prices = DecisionPriceSnapshot(
        source_manifest_id=source_manifest.source_manifest_id,
        decision_time=decision_time,
        observations=(),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return ResearchInputBundle(
        evidence_kind=ResearchEvidenceKind.SYNTHETIC_FIXTURE,
        source_manifest=source_manifest,
        universe_snapshot=universe,
        eligibility_snapshot=eligibility,
        decision_price_snapshot=decision_prices,
        market_observation=MarketObservation(
            available_at=AvailabilityTime(
                datetime(2026, 7, 29, 14, 50, tzinfo=SHANGHAI)
            ),
            source_artifact_id=ArtifactId("fixture-market-observation"),
            market_direction_return=0.005,
            market_intraday_range_to_cutoff=0.015,
            market_amount_change_same_cutoff=0.10,
            candidate_breadth_at_cutoff=0.60,
            limit_structure_score=0.10,
            coverage=1.0,
        ),
        theme_observations=(),
        symbol_observations=(),
        theme_memberships=(),
        etf_observations=(),
        stock_daily_bars=(),
        prediction_runs=(),
        input_artifact_ids=(
            decision_prices.decision_snapshot_id,
            ArtifactId("fixture-eligibility-artifact"),
            ArtifactId("fixture-market-observation"),
            ArtifactId("fixture-universe-artifact"),
        ),
        input_content_hashes=(
            decision_prices.content_hash,
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
        ),
        created_at=datetime(2026, 7, 29, 15, 0, tzinfo=SHANGHAI),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
