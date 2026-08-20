from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from market_regime_alpha.application.historical_corpus.decision_materializer import (
    NORMALIZED_DATASET_KIND,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    EvidenceMetricStatus,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.evidence_producer import (
    HistoricalEvidenceProducer,
    _ablation_finding,
    _incremental_is_estimable,
    _metrics_payload,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
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


def test_negative_absolute_alpha_is_not_classified_positive_from_relative_lift() -> None:
    first = replace(
        _metrics(),
        session_count=126,
        rank_ic=Decimal("-0.061"),
        net_return=Decimal("-0.0030"),
    )
    last = replace(
        _metrics(),
        session_count=126,
        rank_ic=Decimal("-0.059"),
        net_return=Decimal("-0.0029"),
    )
    suite = Mock(results=(Mock(metrics=first), Mock(metrics=last)))

    assert _ablation_finding(suite) is ResearchFinding.NEGATIVE


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


def test_v1_evidence_is_not_regenerated_without_canonical_evaluations() -> None:
    journal = Mock()
    journal.get_run.return_value = Mock(status=HistoricalRunStatus.COMPLETE)
    components = Mock()
    components.list_references_for_run.side_effect = (
        lambda *, run_id, component_kind: (
            (_reference("HISTORICAL_RESEARCH_PANEL", "panel"),)
            if component_kind is HistoricalComponentKind.RESEARCH_PANEL
            else ()
        )
    )
    producer = HistoricalEvidenceProducer(
        journal=journal,
        corpus_repository=Mock(),
        component_repository=components,
        evidence_repository=Mock(),
    )

    with pytest.raises(ValueError, match="legacy V1 Evidence remains immutable"):
        producer.produce(run_id=ArtifactId("historical-v1-run"))


def _reference(kind: str, identity: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        artifact_kind=kind,
        artifact_id=ArtifactId(f"{kind.lower()}-{identity}"),
        content_hash=f"sha256:{identity.encode().hex().ljust(64, '0')[:64]}",
    )


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
