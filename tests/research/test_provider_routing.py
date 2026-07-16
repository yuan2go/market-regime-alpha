from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.data import DataEligibility
from market_regime_alpha.research.provider_routing import (
    PROVIDER_SELECTION_POLICY_VERSION,
    CandidateDataSource,
    CandidateRunSourceMode,
    ProviderAvailabilityStatus,
    ProviderCapabilityReport,
    ProviderRoutingError,
    ProviderRoutingErrorCode,
    ProviderSelectionDisposition,
    select_candidate_data_source,
)


def _report(
    source: CandidateDataSource,
    status: ProviderAvailabilityStatus,
    maximum: DataEligibility,
    *,
    input_identity: str | None = None,
) -> ProviderCapabilityReport:
    return ProviderCapabilityReport(
        source=source,
        availability_status=status,
        maximum_data_eligibility=maximum,
        supported_evidence=("DAILY_OHLCV",),
        unsupported_evidence=("FORMAL_PIT",),
        limitations=("TEST_LIMITATION",),
        input_identity=input_identity or f"test:{source.value}:{status.value}",
    )


def test_auto_prefers_available_xuntou() -> None:
    decision = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=_report(
            CandidateDataSource.XUNTOU,
            ProviderAvailabilityStatus.AVAILABLE,
            DataEligibility.REHEARSAL,
        ),
        tencent=_report(
            CandidateDataSource.TENCENT_COMPOSITE,
            ProviderAvailabilityStatus.AVAILABLE,
            DataEligibility.EXPLORATORY,
        ),
    )

    assert decision.selected_source is CandidateDataSource.XUNTOU
    assert decision.selected_data_eligibility is DataEligibility.REHEARSAL
    assert decision.policy_version == PROVIDER_SELECTION_POLICY_VERSION
    assert tuple(item.disposition for item in decision.attempts) == (
        ProviderSelectionDisposition.SELECTED,
    )


def test_auto_uses_tencent_only_when_xuntou_is_unavailable() -> None:
    decision = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=_report(
            CandidateDataSource.XUNTOU,
            ProviderAvailabilityStatus.UNAVAILABLE,
            DataEligibility.REHEARSAL,
        ),
        tencent=_report(
            CandidateDataSource.TENCENT_COMPOSITE,
            ProviderAvailabilityStatus.AVAILABLE,
            DataEligibility.EXPLORATORY,
        ),
    )

    assert decision.selected_source is CandidateDataSource.TENCENT_COMPOSITE
    assert decision.selected_data_eligibility is DataEligibility.EXPLORATORY
    assert tuple(item.disposition for item in decision.attempts) == (
        ProviderSelectionDisposition.UNAVAILABLE,
        ProviderSelectionDisposition.SELECTED,
    )
    assert "XUNTOU_PRIMARY_UNAVAILABLE" in decision.limitations


def test_invalid_xuntou_fails_closed_without_tencent_fallback() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.EXPLORATORY,
            xuntou=_report(
                CandidateDataSource.XUNTOU,
                ProviderAvailabilityStatus.INVALID,
                DataEligibility.REHEARSAL,
            ),
            tencent=_report(
                CandidateDataSource.TENCENT_COMPOSITE,
                ProviderAvailabilityStatus.AVAILABLE,
                DataEligibility.EXPLORATORY,
            ),
        )

    assert exc_info.value.code is ProviderRoutingErrorCode.SOURCE_INVALID
    assert tuple(item.source for item in exc_info.value.attempts) == (
        CandidateDataSource.XUNTOU,
    )


def test_rehearsal_requirement_rejects_tencent() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.REHEARSAL,
            xuntou=_report(
                CandidateDataSource.XUNTOU,
                ProviderAvailabilityStatus.UNAVAILABLE,
                DataEligibility.REHEARSAL,
            ),
            tencent=_report(
                CandidateDataSource.TENCENT_COMPOSITE,
                ProviderAvailabilityStatus.AVAILABLE,
                DataEligibility.EXPLORATORY,
            ),
        )

    assert exc_info.value.code is ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED


@pytest.mark.parametrize(
    ("mode", "source"),
    (
        (CandidateRunSourceMode.XUNTOU, CandidateDataSource.XUNTOU),
        (CandidateRunSourceMode.TENCENT, CandidateDataSource.TENCENT_COMPOSITE),
    ),
)
def test_explicit_modes_select_only_the_requested_source(
    mode: CandidateRunSourceMode,
    source: CandidateDataSource,
) -> None:
    decision = select_candidate_data_source(
        mode=mode,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=_report(
            CandidateDataSource.XUNTOU,
            ProviderAvailabilityStatus.AVAILABLE,
            DataEligibility.REHEARSAL,
        ),
        tencent=_report(
            CandidateDataSource.TENCENT_COMPOSITE,
            ProviderAvailabilityStatus.AVAILABLE,
            DataEligibility.EXPLORATORY,
        ),
    )

    assert decision.selected_source is source
    assert tuple(item.source for item in decision.attempts) == (source,)


def test_explicit_unavailable_source_does_not_try_the_other_source() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.XUNTOU,
            minimum_eligibility=DataEligibility.EXPLORATORY,
            xuntou=_report(
                CandidateDataSource.XUNTOU,
                ProviderAvailabilityStatus.UNAVAILABLE,
                DataEligibility.REHEARSAL,
            ),
            tencent=_report(
                CandidateDataSource.TENCENT_COMPOSITE,
                ProviderAvailabilityStatus.AVAILABLE,
                DataEligibility.EXPLORATORY,
            ),
        )

    assert exc_info.value.code is ProviderRoutingErrorCode.REQUIRED_SOURCE_UNAVAILABLE
    assert tuple(item.source for item in exc_info.value.attempts) == (
        CandidateDataSource.XUNTOU,
    )


def test_no_available_source_is_explicit() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.EXPLORATORY,
            xuntou=_report(
                CandidateDataSource.XUNTOU,
                ProviderAvailabilityStatus.UNAVAILABLE,
                DataEligibility.REHEARSAL,
            ),
            tencent=_report(
                CandidateDataSource.TENCENT_COMPOSITE,
                ProviderAvailabilityStatus.UNAVAILABLE,
                DataEligibility.EXPLORATORY,
            ),
        )

    assert exc_info.value.code is ProviderRoutingErrorCode.NO_ELIGIBLE_SOURCE
    assert len(exc_info.value.attempts) == 2


def test_formal_research_is_never_routable() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.FORMAL_RESEARCH,
            xuntou=_report(
                CandidateDataSource.XUNTOU,
                ProviderAvailabilityStatus.AVAILABLE,
                DataEligibility.REHEARSAL,
            ),
            tencent=_report(
                CandidateDataSource.TENCENT_COMPOSITE,
                ProviderAvailabilityStatus.AVAILABLE,
                DataEligibility.EXPLORATORY,
            ),
        )

    assert exc_info.value.code is ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED


def test_decision_identity_is_deterministic_and_input_sensitive() -> None:
    xuntou = _report(
        CandidateDataSource.XUNTOU,
        ProviderAvailabilityStatus.AVAILABLE,
        DataEligibility.REHEARSAL,
    )
    tencent = _report(
        CandidateDataSource.TENCENT_COMPOSITE,
        ProviderAvailabilityStatus.AVAILABLE,
        DataEligibility.EXPLORATORY,
    )
    first = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=xuntou,
        tencent=tencent,
    )
    second = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=xuntou,
        tencent=tencent,
    )
    changed = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=replace(xuntou, input_identity="test:xuntou:changed"),
        tencent=tencent,
    )

    assert first.decision_id == second.decision_id
    assert first.decision_id.startswith("provider-selection:sha256:")
    assert changed.decision_id != first.decision_id


def test_capability_report_rejects_evidence_overlap() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        ProviderCapabilityReport(
            source=CandidateDataSource.XUNTOU,
            availability_status=ProviderAvailabilityStatus.AVAILABLE,
            maximum_data_eligibility=DataEligibility.REHEARSAL,
            supported_evidence=("DAILY_OHLCV",),
            unsupported_evidence=("DAILY_OHLCV",),
            limitations=(),
            input_identity="test:xuntou",
        )
