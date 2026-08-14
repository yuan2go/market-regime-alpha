from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from market_regime_alpha.application.historical_corpus.decision_materializer import (
    NORMALIZED_DATASET_KIND,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    EvidenceMetricStatus,
)
from market_regime_alpha.application.historical_corpus.evidence_producer import (
    HistoricalEvidenceProducer,
    _incremental_is_estimable,
    _metrics_payload,
)
from market_regime_alpha.application.research_validation.ablation import (
    AblationMetrics,
    AblationVariantKind,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


def test_unobserved_layer_incremental_lift_is_not_estimable() -> None:
    metrics = _metrics()
    variant_id = AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF.value.lower()
    coverage = {FactorFamily.ETF: 0}

    assert not _incremental_is_estimable(variant_id, coverage)
    payload = _metrics_payload(metrics, incremental_estimable=False)
    assert payload["incremental_lift"] is None
    assert (
        payload["incremental_lift_status"]
        == EvidenceMetricStatus.NOT_ESTIMABLE.value
    )


def test_observed_layer_retains_computed_incremental_lift() -> None:
    metrics = _metrics()
    variant_id = AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF.value.lower()
    coverage = {FactorFamily.ETF: 1}

    assert _incremental_is_estimable(variant_id, coverage)
    payload = _metrics_payload(metrics, incremental_estimable=True)
    assert payload["incremental_lift"] == "0"
    assert payload["incremental_lift_status"] == EvidenceMetricStatus.AVAILABLE.value


def test_evidence_opens_verified_index_without_loading_whole_package() -> None:
    corpus = Mock()
    index = object()
    corpus.open_index.return_value = index
    corpus.load.side_effect = AssertionError("whole package must not be loaded")
    producer = HistoricalEvidenceProducer(
        journal=Mock(),
        corpus_repository=corpus,
        component_repository=Mock(),
        evidence_repository=Mock(),
    )
    reference = ValidationArtifactReference(
        artifact_kind=NORMALIZED_DATASET_KIND,
        artifact_id=ArtifactId("historical-data-owner-index-only"),
        content_hash=f"sha256:{'0' * 64}",
    )

    assert producer._normalized_owner((reference,)) is index
    corpus.open_index.assert_called_once_with(reference)
    corpus.load.assert_not_called()


def _metrics() -> AblationMetrics:
    return AblationMetrics(
        sample_count=1,
        session_count=1,
        ic=None,
        rank_ic=None,
        icir=None,
        top_k_return=Decimal("0"),
        spread=Decimal("0"),
        hit_rate=Decimal("1"),
        mean_return=Decimal("0"),
        mean_mfe=None,
        mean_mae=None,
        turnover=Decimal("0"),
        max_drawdown=Decimal("0"),
        overlap=None,
        incremental_lift=Decimal("0"),
        gross_return=Decimal("0"),
        cost_return=Decimal("0"),
        net_return=Decimal("0"),
    )
