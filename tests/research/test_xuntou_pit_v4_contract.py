from datetime import datetime

import pytest

from market_regime_alpha.research.xuntou_pit_v4_contract import (
    AmountUnitContract,
    ResearchOrderabilityStatus,
    XuntouPITSourceArtifact,
)


def test_source_artifact_rejects_non_content_addressed_identity() -> None:
    with pytest.raises(ValueError, match="content hash"):
        XuntouPITSourceArtifact(
            provider="XUNTOU",
            product="XTQUANT",
            contract_version="xuntou-pit-validation-bundle-v4",
            retrieved_at=datetime.fromisoformat("2026-07-18T15:00:00+08:00"),
            export_started_at=datetime.fromisoformat("2026-07-18T14:00:00+08:00"),
            export_completed_at=datetime.fromisoformat("2026-07-18T14:30:00+08:00"),
            content_hash="forged",
            locator_role="EXTERNAL_IMMUTABLE_INPUT",
            entitlement_class="REDACTED_RESEARCH",
            runtime_version="unknown",
            xtquant_version="unknown",
            timezone="Asia/Shanghai",
            evidence_classification="PROVIDER_EXPORT",
        )


def test_amount_unit_requires_explicit_native_semantics() -> None:
    ambiguous = AmountUnitContract("CNY", "UNKNOWN", 1.0, "UNKNOWN", "NONE", "amount", "")
    assert ambiguous.absolute_threshold_qualified is False
    qualified = AmountUnitContract(
        "CNY", "YUAN", 1.0, "SUM_NATIVE_PERIOD_AMOUNT", "NONE", "amount", "XUNTOU_OFFICIAL_FIELD_EVIDENCE"
    )
    assert qualified.absolute_threshold_qualified is True


def test_orderability_enum_does_not_alias_unknown_to_orderable() -> None:
    assert ResearchOrderabilityStatus.UNKNOWN is not ResearchOrderabilityStatus.RESEARCH_ORDERABLE
