from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.market.domain import (
    BarTimeframe,
    PriceBasis,
    ProviderEvidenceClass,
    ProviderQualificationArtifact,
    ProviderQualificationProtocol,
    ProviderQualificationPurpose,
    ProviderQualificationRequirement,
    ProviderRequirementKind,
)


def _artifact(value: str) -> ProviderQualificationArtifact:
    return ProviderQualificationArtifact(
        artifact_id=uuid4(),
        content_sha256=value * 64,
        size_bytes=17,
    )


def _protocol() -> ProviderQualificationProtocol:
    protocol_id = uuid4()
    requirements = tuple(
        ProviderQualificationRequirement(
            provider_qualification_requirement_id=uuid4(),
            provider_qualification_protocol_id=protocol_id,
            ordinal=ordinal,
            requirement_kind=kind,
            minimum_observation_count=1,
            minimum_ratio=Decimal("1.0000000000"),
        )
        for ordinal, kind in enumerate(ProviderRequirementKind, start=1)
    )
    start = datetime(2025, 1, 1, tzinfo=UTC)
    return ProviderQualificationProtocol(
        provider_qualification_protocol_id=protocol_id,
        protocol_code="sse-minute-pit",
        revision=1,
        supersedes_protocol_id=None,
        provider_product_id=uuid4(),
        purpose=ProviderQualificationPurpose.HISTORICAL_PIT,
        evidence_class=ProviderEvidenceClass.ENGINEERING_REHEARSAL,
        market_scope="A_SHARE",
        instrument_scope="SSE_EQUITY",
        exchange_code="SSE",
        timeframe=BarTimeframe.MINUTE_1,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        decision_time_rule="SESSION_10_30_ASIA_SHANGHAI",
        capture_window_start=start,
        capture_window_end=start + timedelta(days=5),
        evidence_cutoff=start + timedelta(days=6),
        outcome_path_sessions=5,
        requirements=requirements,
        code_artifact=_artifact("a"),
        config_artifact=_artifact("b"),
        provenance_sha256="c" * 64,
    )


def test_provider_protocol_freezes_complete_closed_requirement_roster() -> None:
    protocol = _protocol()

    assert protocol.requirement_count == len(ProviderRequirementKind)
    assert protocol.requirement_roster_sha256
    assert protocol.content_sha256
    assert tuple(item.ordinal for item in protocol.requirements) == tuple(
        range(1, len(protocol.requirements) + 1)
    )


def test_provider_protocol_rejects_duplicate_missing_or_noncontiguous_requirements() -> None:
    protocol = _protocol()
    with pytest.raises(ValueError, match="exactly once"):
        replace(protocol, requirements=protocol.requirements[:-1])
    with pytest.raises(ValueError, match="exactly once"):
        replace(
            protocol,
            requirements=(protocol.requirements[0], *protocol.requirements),
        )
    with pytest.raises(ValueError, match="contiguous"):
        replace(
            protocol,
            requirements=(
                replace(protocol.requirements[0], ordinal=99),
                *protocol.requirements[1:],
            ),
        )


def test_provider_protocol_rejects_invalid_window_and_revision_chain() -> None:
    protocol = _protocol()
    with pytest.raises(ValueError, match="capture window"):
        replace(protocol, capture_window_end=protocol.capture_window_start)
    with pytest.raises(ValueError, match="evidence cutoff"):
        replace(protocol, evidence_cutoff=protocol.capture_window_end - timedelta(1))
    with pytest.raises(ValueError, match="revision chain"):
        replace(protocol, revision=2, supersedes_protocol_id=None)
