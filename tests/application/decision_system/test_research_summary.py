from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.research_summary import (
    LEGACY_RESEARCH_DAILY_SUMMARY_SCHEMA,
    LEGACY_RESEARCH_STAGE_EVIDENCE_SCHEMA,
    ProviderContractLineage,
    ResearchDailySummary,
    ResearchDailySummaryOutcome,
    ResearchStageEvidence,
    ResearchStageResult,
    ResearchStageStatus,
)
from market_regime_alpha.application.state_system.runtime import (
    STATE_RESEARCH_STAGE_ORDER,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


NOW = datetime(2026, 8, 9, 6, 45, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _reference(kind: str, suffix: str, digest: str = HASH_A) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(kind, ArtifactId(f"artifact-{suffix}"), digest)


def _stages(
    *,
    missing: str | None = None,
    rejected: str | None = None,
    available_at: datetime = NOW,
    candidate_result: ResearchStageResult = ResearchStageResult.EMPTY,
    signal_result: ResearchStageResult = ResearchStageResult.EMPTY,
    forecast_result: ResearchStageResult = ResearchStageResult.EMPTY,
) -> tuple[ResearchStageEvidence, ...]:
    result = []
    for stage in STATE_RESEARCH_STAGE_ORDER:
        status = ResearchStageStatus.COMPLETED
        missing_evidence: tuple[str, ...] = ()
        reasons = (f"{stage.value}_COMPLETED",)
        selection = None
        structured_result = ResearchStageResult.AVAILABLE
        if stage.value == "CANDIDATE":
            structured_result = candidate_result
        elif stage.value == "SIGNAL":
            structured_result = signal_result
        elif stage.value == "FORECAST":
            structured_result = forecast_result
        if stage.value == missing:
            status = ResearchStageStatus.DATA_INSUFFICIENT
            missing_evidence = (f"{stage.value}_EVIDENCE_UNAVAILABLE",)
            reasons = ("DATA_INSUFFICIENT", *missing_evidence)
        if stage.value == rejected:
            status = ResearchStageStatus.MODEL_NOT_QUALIFIED_FOR_MODE
            reasons = ("MODEL_NOT_QUALIFIED_FOR_MODE",)
            selection = _reference("MODEL_SELECTION_RECEIPT", stage.value, HASH_B)
        if status is not ResearchStageStatus.COMPLETED:
            structured_result = ResearchStageResult.UNAVAILABLE
        result.append(
            ResearchStageEvidence.create(
                stage=stage,
                status=status,
                output_reference=(
                    None
                    if status is not ResearchStageStatus.COMPLETED
                    else _reference(f"{stage.value}_OUTPUT", stage.value)
                ),
                selection_receipt=selection,
                evidence_available_at=available_at,
                stage_completed_at=available_at,
                result=structured_result,
                data_eligibility=DataEligibility.EXPLORATORY,
                evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
                missing_evidence=missing_evidence,
                reason_codes=tuple(sorted(reasons)),
            )
        )
    return tuple(result)


def _summary(
    *,
    mode: RuntimeAuthorityMode = RuntimeAuthorityMode.RESEARCH,
    stages: tuple[ResearchStageEvidence, ...] | None = None,
    revision: int = 1,
    previous_summary_id: ArtifactId | None = None,
    correction_of_summary_id: ArtifactId | None = None,
    run_id: ArtifactId = ArtifactId("continuous-run-a"),
    tick_id: ArtifactId = ArtifactId("continuous-tick-a"),
    trading_date: date = date(2026, 8, 9),
    decision_time: datetime = NOW,
) -> ResearchDailySummary:
    stage_values = stages or _stages()
    selections = tuple(
        item.selection_receipt
        for item in stage_values
        if item.selection_receipt is not None
    )
    return ResearchDailySummary.create(
        runtime_mode=mode,
        run_id=run_id,
        tick_id=tick_id,
        trading_date=trading_date,
        decision_time=decision_time,
        provider_profile_id="TENCENT_FREE_OPERATIONAL_V1",
        provider_contracts=(
            ProviderContractLineage(
                provider_id="baostock",
                product="daily-history-and-status",
                contract_version="public-composite-v1",
            ),
            ProviderContractLineage(
                provider_id="tencent",
                product="decision-quote-and-minute",
                contract_version="public-composite-v1",
            ),
        ),
        source_manifest=_reference("SOURCE_MANIFEST", "source"),
        dataset=_reference("MARKET_DATA_DATASET", "dataset"),
        feature_bundle=_reference("FEATURE_BUNDLE", "features"),
        state_system_receipt=_reference("STATE_SYSTEM_RECEIPT", "state"),
        candidate_set=_reference("STATE_CONSTRAINED_CANDIDATE_SET", "candidates"),
        stages=stage_values,
        model_selection_receipts=selections,
        configuration_references=(_reference("RUNTIME_CONFIGURATION", "config", HASH_C),),
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
        revision=revision,
        previous_summary_id=previous_summary_id,
        correction_of_summary_id=correction_of_summary_id,
        idempotency_key=f"summary-{mode.value}-{revision}",
        created_at=decision_time,
    )


def test_research_summary_round_trips_and_binds_complete_lineage() -> None:
    summary = _summary()

    restored = ResearchDailySummary.from_canonical_dict(summary.to_canonical_dict())

    assert restored == summary
    assert summary.outcome is ResearchDailySummaryOutcome.NO_ACTION
    assert tuple(item.stage for item in summary.stages) == STATE_RESEARCH_STAGE_ORDER
    assert summary.no_order is True
    assert summary.no_fill is True
    assert summary.no_broker is True
    assert summary.no_position_mutation_from_shadow is True


def test_legacy_v1_summary_remains_content_exact_readable() -> None:
    current = _summary()
    legacy_stages = tuple(
        ResearchStageEvidence.create(
            **{
                **stage.creation_values(),
                "schema_version": LEGACY_RESEARCH_STAGE_EVIDENCE_SCHEMA,
            }
        )
        for stage in current.stages
    )
    legacy = ResearchDailySummary.create(
        **{
            **current.creation_values(),
            "state_system_receipt": None,
            "candidate_set": None,
            "stages": legacy_stages,
            "schema_version": LEGACY_RESEARCH_DAILY_SUMMARY_SCHEMA,
        }
    )
    payload = legacy.to_canonical_dict()

    restored = ResearchDailySummary.from_canonical_dict(payload)

    assert restored.to_canonical_dict() == payload
    assert restored.summary_id == legacy.summary_id
    assert restored.state_system_receipt is None


def test_summary_outcome_uses_structured_results_not_reason_strings() -> None:
    no_action = _summary(stages=_stages())
    watch = _summary(
        stages=_stages(
            candidate_result=ResearchStageResult.RESEARCH_QUALIFIED,
            signal_result=ResearchStageResult.WATCH,
            forecast_result=ResearchStageResult.EMPTY,
        )
    )
    candidate = _summary(
        stages=_stages(
            candidate_result=ResearchStageResult.RESEARCH_QUALIFIED,
            signal_result=ResearchStageResult.RESEARCH_QUALIFIED,
            forecast_result=ResearchStageResult.RESEARCH_QUALIFIED,
        )
    )
    misleading_reasons = tuple(
        ResearchStageEvidence.create(
            **{
                **stage.creation_values(),
                "reason_codes": tuple(
                    sorted({*stage.reason_codes, "RESEARCH_CANDIDATE", "WATCH"})
                ),
            }
        )
        for stage in no_action.stages
    )

    assert no_action.outcome is ResearchDailySummaryOutcome.NO_ACTION
    assert watch.outcome is ResearchDailySummaryOutcome.WATCH
    assert candidate.outcome is ResearchDailySummaryOutcome.RESEARCH_CANDIDATE
    assert (
        _summary(stages=misleading_reasons).outcome
        is ResearchDailySummaryOutcome.NO_ACTION
    )


def test_stage_preserves_evidence_and_computation_times() -> None:
    completed = NOW.replace(minute=46)
    summary = _summary(stages=_stages(available_at=NOW))
    stage = ResearchStageEvidence.create(
        **{
            **summary.stages[0].creation_values(),
            "stage_completed_at": completed,
        }
    )

    assert stage.evidence_available_at == NOW
    assert stage.stage_completed_at == completed
    assert stage.stage_completed_at > stage.evidence_available_at


def test_missing_stage_is_summary_data_insufficient_not_runtime_disappearance() -> None:
    summary = _summary(stages=_stages(missing="ETF_ROTATION"))

    assert summary.outcome is ResearchDailySummaryOutcome.DATA_INSUFFICIENT
    assert "ETF_ROTATION_EVIDENCE_UNAVAILABLE" in summary.missing_evidence
    assert summary.stages[2].status is ResearchStageStatus.DATA_INSUFFICIENT


def test_rejected_mode_selection_is_preserved_in_summary() -> None:
    summary = _summary(
        mode=RuntimeAuthorityMode.SHADOW,
        stages=_stages(rejected="SIGNAL"),
    )

    assert (
        summary.outcome
        is ResearchDailySummaryOutcome.MODEL_NOT_QUALIFIED_FOR_MODE
    )
    assert summary.model_selection_receipts


def test_summary_rejects_evidence_ceiling_or_data_eligibility_inflation() -> None:
    summary = _summary(stages=_stages(missing="CAPITAL_STATE"))

    with pytest.raises(ValueError, match="Evidence ceiling"):
        ResearchDailySummary.create(
            **{
                **summary.creation_values(),
                "evidence_ceiling": PITSourceEvidenceLevel.PIT_INCOMPLETE,
            }
        )
    with pytest.raises(ValueError, match="DataEligibility"):
        ResearchDailySummary.create(
            **{
                **summary.creation_values(),
                "data_eligibility": DataEligibility.REHEARSAL,
            }
        )


def test_original_is_final_and_correction_is_a_new_revision() -> None:
    original = _summary()
    correction = _summary(
        revision=2,
        previous_summary_id=original.summary_id,
        correction_of_summary_id=original.summary_id,
    )

    assert correction.summary_id != original.summary_id
    assert correction.previous_summary_id == original.summary_id
    with pytest.raises(ValueError, match="correction"):
        _summary(revision=2, previous_summary_id=original.summary_id)


def test_production_uses_existing_strict_decision_path_not_research_summary() -> None:
    with pytest.raises(ValueError, match="Research/Shadow"):
        _summary(mode=RuntimeAuthorityMode.PRODUCTION)
