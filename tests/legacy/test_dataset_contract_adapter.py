from __future__ import annotations

import pytest

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.data.contracts import DataEligibility, ProviderReference
from market_regime_alpha.dividend_t.macd import PriceAdjustmentMode
from market_regime_alpha.dividend_t.macd_oos import (
    DATASET_MANIFEST_SCHEMA_VERSION,
    DatasetClassification,
    DatasetManifest,
    DatasetQualityStats,
    DatasetSymbolManifest,
    dataset_version,
)
from market_regime_alpha.legacy.dataset_contract_adapter import adapt_legacy_dataset_manifest


def _manifest(classification: DatasetClassification) -> DatasetManifest:
    return DatasetManifest(
        schema_version=DATASET_MANIFEST_SCHEMA_VERSION,
        classification=classification,
        files=(),
        symbols=("000001.SZ",),
        symbols_detail=(
            DatasetSymbolManifest(
                symbol="000001.SZ",
                start_time="2026-01-02 09:35:00",
                end_time="2026-04-02 15:00:00",
                bar_count=100,
            ),
        ),
        start_time="2026-01-02 09:35:00",
        end_time="2026-04-02 15:00:00",
        total_bar_count=100,
        data_source="controlled-fixture-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="calendar-v1",
        trading_calendar_hash="a" * 64,
        universe_hash="b" * 64,
        corporate_action_hash="c" * 64,
        suspension_hash="d" * 64,
        quality=DatasetQualityStats(
            finalized_bar_count=100,
            provisional_bar_count=0,
            missing_expected_bar_count=0,
            unexpected_timestamp_count=0,
            invalid_price_bar_count=0,
            duplicate_timestamp_count=0,
            nonpositive_volume_bar_count=0,
            bar_final_column_present=True,
        ),
        volume_unit="SHARES",
        amount_unit="CNY",
        price_unit="CNY_PER_SHARE",
        vwap_formula_version="amount_cny_per_volume_share-v1",
    )


def _provider() -> ProviderReference:
    return ProviderReference(
        provider_id=ProviderId("provider-controlled-fixture"),
        product="5-minute-bars",
        contract_version="v1",
    )


def test_legacy_rehearsal_maps_to_canonical_rehearsal_without_new_identity_system() -> None:
    manifest = _manifest(DatasetClassification.REHEARSAL)

    adapted = adapt_legacy_dataset_manifest(
        manifest,
        manifest_artifact_id=ArtifactId("legacy-manifest-artifact-v1"),
        provider_references=(_provider(),),
        scope="candidate-rehearsal",
        limitations=("Legacy MACD rehearsal scope",),
    )

    assert str(adapted.dataset_id) == dataset_version(manifest)
    assert adapted.eligibility is DataEligibility.REHEARSAL
    assert adapted.pit_correct_for_scope is True


def test_legacy_fixture_does_not_gain_exploratory_or_formal_authority() -> None:
    adapted = adapt_legacy_dataset_manifest(
        _manifest(DatasetClassification.FIXTURE),
        manifest_artifact_id=ArtifactId("legacy-fixture-artifact-v1"),
        provider_references=(_provider(),),
        scope="contract-testing-only",
    )

    assert adapted.eligibility is DataEligibility.UNQUALIFIED


def test_legacy_formal_final_candidate_requires_canonical_eligibility_review() -> None:
    with pytest.raises(ValueError, match="CANONICAL_DATA_ELIGIBILITY_REVIEW_REQUIRED"):
        adapt_legacy_dataset_manifest(
            _manifest(DatasetClassification.FORMAL_FINAL_CANDIDATE),
            manifest_artifact_id=ArtifactId("legacy-formal-candidate-artifact-v1"),
            provider_references=(_provider(),),
            scope="candidate-formal-research",
        )
