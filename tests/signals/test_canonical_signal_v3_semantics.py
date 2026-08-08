from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, UniverseId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.platform.contracts import EvidenceLevel, ModelLifecycleStatus
from market_regime_alpha.platform.model_registry import ModelRegistry
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from tests.postgres_path_repositories import (
    PostgresModelRegistryRepository,
)
from market_regime_alpha.signals.contracts import SignalState
from market_regime_alpha.signals.decimal_model import (
    CanonicalSignalModelV2,
    canonical_signal_model_configuration_v2,
)
from market_regime_alpha.signals.governance import (
    persist_canonical_signal_model_for_research,
    register_canonical_signal_model_for_research,
)
from market_regime_alpha.signals.input_assembly import SignalFactorName
from market_regime_alpha.signals.input_v3 import canonical_signal_input_mapping_v2
from market_regime_alpha.signals.policies import (
    FactorFreshnessState,
    SignalFactorFreshnessMode,
    SignalFactorFreshnessRule,
    SignalFactorRequirementMode,
    SignalFactorRequirementPolicy,
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
)
from market_regime_alpha.market_data import Timeframe


UTC = timezone.utc
HASH = "sha256:" + "a" * 64
DECISION = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)


def _canonical_snapshot_hash(
    *,
    missing_factor: SignalFactorName | None = None,
    overheat: Decimal = Decimal("0.01"),
) -> tuple[str, object]:
    values = {
        SignalFactorName.PRICE_ACTION_RETURN: Decimal("0.01"),
        SignalFactorName.VOLUME_RATIO: Decimal("1.2"),
        SignalFactorName.TREND_RETURN: Decimal("0.02"),
        SignalFactorName.PRICE_VS_VWAP_RETURN: Decimal("0.003"),
        SignalFactorName.OVERHEAT_RETURN: overheat,
    }
    if missing_factor is not None:
        values[missing_factor] = None
    candidate = SimpleNamespace(
        envelope=SimpleNamespace(
            artifact_id=ArtifactId("candidate-test"),
            content_hash=HASH,
            source_manifest_id=ArtifactId("manifest-test"),
            source_manifest_hash=HASH,
            data_eligibility=DataEligibility.EXPLORATORY,
        )
    )
    observation = SimpleNamespace(
        verify_identity=lambda: None,
        decision_time=DECISION,
        factors=tuple(
            SimpleNamespace(factor_name=factor, value=values[factor])
            for factor in sorted(SignalFactorName, key=lambda item: item.value)
        ),
        factor_requirements_satisfied=missing_factor is None,
        reason_codes=(
            ("SIGNAL_FACTOR_REQUIREMENTS_SATISFIED",)
            if missing_factor is None
            else (f"FACTOR_{missing_factor.value}_MISSING",)
        ),
        observation_id=ArtifactId("observation-test"),
        content_hash=HASH,
        symbol="600000.SH",
    )
    snapshot = CanonicalSignalModelV2().run(
        candidate_set=candidate,
        observation=observation,
        configuration=canonical_signal_model_configuration_v2(),
        decision_time=DecisionTime(DECISION),
        created_at=DECISION + timedelta(seconds=1),
        code_revision="canonical-v3-reference-test",
    )
    return snapshot.envelope.content_hash, snapshot


def test_decimal_model_has_fixed_denominator_missingness_and_overheat_gate() -> None:
    _, confirmed = _canonical_snapshot_hash()
    assert confirmed.signal_state is SignalState.CONFIRMED_FOR_RESEARCH
    assert confirmed.signal_score == Decimal("1")
    assert confirmed.confidence == Decimal("1")
    assert confirmed.score_denominator == 5

    _, missing = _canonical_snapshot_hash(
        missing_factor=SignalFactorName.TREND_RETURN
    )
    assert missing.signal_state is SignalState.DATA_INSUFFICIENT
    assert missing.signal_score is None
    assert missing.confidence == Decimal("0.8")

    _, overheated = _canonical_snapshot_hash(overheat=Decimal("0.08"))
    assert overheated.signal_state is SignalState.INACTIVE
    assert overheated.signal_score == Decimal("0.6")
    assert overheated.reason_codes == ("OVERHEAT_CONTRADICTED",)


def test_decimal_model_ignores_global_context_and_is_cross_process_stable() -> None:
    original_precision = getcontext().prec
    try:
        getcontext().prec = 7
        first, _ = _canonical_snapshot_hash()
        getcontext().prec = 50
        second, _ = _canonical_snapshot_hash()
    finally:
        getcontext().prec = original_precision
    assert first == second
    script = (
        "from tests.signals.test_canonical_signal_v3_semantics "
        "import _canonical_snapshot_hash; print(_canonical_snapshot_hash()[0])"
    )
    observed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert observed == first


def test_requirement_policy_modes_and_mapping_flags_are_unambiguous() -> None:
    all_required = canonical_all_factors_required_policy()
    complete = {factor: Decimal("1") for factor in SignalFactorName}
    assert all_required.assess(complete).sufficient
    missing = dict(complete)
    missing[SignalFactorName.VOLUME_RATIO] = None
    assessment = all_required.assess(missing)
    assert not assessment.sufficient
    assert assessment.missing_required_factors == (SignalFactorName.VOLUME_RATIO,)
    assert "MINIMUM_SIGNAL_FACTOR_COUNT_NOT_MET" in assessment.reason_codes

    declared = SignalFactorRequirementPolicy.create(
        policy_version="declared-test-v1",
        mode=SignalFactorRequirementMode.DECLARED_REQUIRED_FACTORS,
        required_factors=(SignalFactorName.PRICE_ACTION_RETURN,),
        minimum_factor_count=1,
    )
    optional_missing = {factor: None for factor in SignalFactorName}
    optional_missing[SignalFactorName.PRICE_ACTION_RETURN] = Decimal("0")
    assert declared.assess(optional_missing).sufficient

    minimum = SignalFactorRequirementPolicy.create(
        policy_version="minimum-test-v1",
        mode=SignalFactorRequirementMode.REQUIRED_PLUS_MINIMUM_TOTAL,
        required_factors=(SignalFactorName.PRICE_ACTION_RETURN,),
        minimum_factor_count=3,
    )
    assert not minimum.assess(optional_missing).sufficient
    optional_missing[SignalFactorName.TREND_RETURN] = Decimal("0")
    optional_missing[SignalFactorName.VOLUME_RATIO] = Decimal("1")
    assert minimum.assess(optional_missing).sufficient

    mapping = canonical_signal_input_mapping_v2(
        effective_from=DECISION - timedelta(days=1)
    )
    mapping.validate_requirement_policy(all_required)
    with pytest.raises(ValueError, match="required flags conflict"):
        mapping.validate_requirement_policy(declared)
    with pytest.raises(ValueError, match="complete factor set"):
        SignalFactorRequirementPolicy.create(
            policy_version="invalid-v1",
            mode=SignalFactorRequirementMode.ALL_FACTORS_REQUIRED,
            required_factors=(SignalFactorName.PRICE_ACTION_RETURN,),
            minimum_factor_count=1,
        )


def _calendar(dates: tuple[date, ...], *, version: str = "test-v1"):
    zone = timezone(timedelta(hours=8))
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source"),
        market="A_SHARE",
        calendar_version=version,
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=value,
                session_close=datetime.combine(value, time(15), tzinfo=zone),
            )
            for value in dates
        ),
    )


def test_trading_session_freshness_handles_weekends_holidays_and_intraday() -> None:
    friday = date(2026, 7, 31)
    monday = date(2026, 8, 3)
    calendar = _calendar((friday, monday))
    policy = canonical_signal_freshness_policy(trading_calendar=calendar)
    friday_close = datetime(2026, 7, 31, 7, 0, tzinfo=UTC)
    monday_1455 = datetime(2026, 8, 3, 6, 55, tzinfo=UTC)
    daily = policy.assess(
        factor_name=SignalFactorName.TREND_RETURN,
        source_available_at=friday_close,
        decision_time=monday_1455,
        timeframe=Timeframe.DAILY,
        trading_calendar=calendar,
    )
    assert daily.state is FactorFreshnessState.FRESH
    assert daily.session_lag == 0

    holiday_calendar = _calendar((date(2026, 9, 30), date(2026, 10, 8)))
    holiday_policy = canonical_signal_freshness_policy(
        trading_calendar=holiday_calendar
    )
    holiday = holiday_policy.assess(
        factor_name=SignalFactorName.PRICE_ACTION_RETURN,
        source_available_at=datetime(2026, 9, 30, 7, tzinfo=UTC),
        decision_time=datetime(2026, 10, 8, 6, 55, tzinfo=UTC),
        timeframe=Timeframe.DAILY,
        trading_calendar=holiday_calendar,
    )
    assert holiday.state is FactorFreshnessState.FRESH
    assert holiday.session_lag == 0

    intraday = policy.assess(
        factor_name=SignalFactorName.PRICE_VS_VWAP_RETURN,
        source_available_at=monday_1455 - timedelta(minutes=5),
        decision_time=monday_1455,
        timeframe=Timeframe.MINUTE_5,
        trading_calendar=calendar,
    )
    assert intraday.state is FactorFreshnessState.FRESH
    assert intraday.elapsed_seconds == 300

    lunch = policy.assess(
        factor_name=SignalFactorName.PRICE_VS_VWAP_RETURN,
        source_available_at=datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
        decision_time=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        timeframe=Timeframe.MINUTE_5,
        trading_calendar=calendar,
    )
    assert lunch.state is FactorFreshnessState.OUTSIDE_TRADING_SESSION

    future = policy.assess(
        factor_name=SignalFactorName.PRICE_VS_VWAP_RETURN,
        source_available_at=monday_1455 + timedelta(seconds=1),
        decision_time=monday_1455,
        timeframe=Timeframe.MINUTE_5,
        trading_calendar=calendar,
    )
    assert future.state is FactorFreshnessState.FUTURE

    with pytest.raises(ValueError, match="identity does not match"):
        policy.assess(
            factor_name=SignalFactorName.TREND_RETURN,
            source_available_at=friday_close,
            decision_time=monday_1455,
            timeframe=Timeframe.DAILY,
            trading_calendar=_calendar((friday, monday), version="different"),
        )


def test_missing_calendar_coverage_and_stale_minute_fail_closed() -> None:
    calendar = _calendar((date(2026, 8, 3),))
    policy = canonical_signal_freshness_policy(trading_calendar=calendar)
    decision = datetime(2026, 8, 3, 6, 55, tzinfo=UTC)
    missing = policy.assess(
        factor_name=SignalFactorName.TREND_RETURN,
        source_available_at=datetime(2026, 7, 31, 7, tzinfo=UTC),
        decision_time=decision,
        timeframe=Timeframe.DAILY,
        trading_calendar=calendar,
    )
    assert missing.state is FactorFreshnessState.CALENDAR_INSUFFICIENT
    stale = policy.assess(
        factor_name=SignalFactorName.PRICE_VS_VWAP_RETURN,
        source_available_at=decision - timedelta(minutes=20),
        decision_time=decision,
        timeframe=Timeframe.MINUTE_5,
        trading_calendar=calendar,
    )
    assert stale.state is FactorFreshnessState.STALE


def test_signal_governance_stops_at_research_exploratory() -> None:
    registry = ModelRegistry()
    mapping = canonical_signal_input_mapping_v2(
        effective_from=DECISION - timedelta(days=1)
    )
    registration = register_canonical_signal_model_for_research(
        registry,
        universe_id=UniverseId("controlled-a-share-universe-v1"),
        mapping=mapping,
        model_configuration=canonical_signal_model_configuration_v2(),
        changed_at=DECISION,
        evidence_refs=("artifact:wp-sig-01a-reference-tests",),
        transition_reason="Canonical Decimal Signal engineering registration",
        approval_boundary_ref="maintainer-controlled-research-boundary",
    )
    assert registration.lifecycle_status is ModelLifecycleStatus.RESEARCH
    assert registration.evidence_level is EvidenceLevel.EXPLORATORY
    assert registration.transitions[0].approval_ref == (
        "maintainer-controlled-research-boundary"
    )
    assert registration.definition.supported_data_eligibilities == (
        DataEligibility.EXPLORATORY,
    )
    assert registration.definition.compatibility_refs == (
        "signal-run-artifact-v1-reader-replay-only",
        "signal-run-artifact-v2-reader-replay-only",
    )


def test_signal_governance_persists_draft_to_research_transition(
    tmp_path: Path,
) -> None:
    service = PersistentModelRegistry(
        PostgresModelRegistryRepository(tmp_path / "model-governance.postgres-scope")
    )
    result = persist_canonical_signal_model_for_research(
        service,
        universe_id=UniverseId("controlled-a-share-universe-v1"),
        mapping=canonical_signal_input_mapping_v2(
            effective_from=DECISION - timedelta(days=1)
        ),
        model_configuration=canonical_signal_model_configuration_v2(),
        changed_at=DECISION,
        evidence_refs=("artifact:wp-sig-01a-reference-tests",),
        transition_reason="Canonical Decimal Signal engineering registration",
        approval_boundary_ref="maintainer-controlled-research-boundary",
        registration_idempotency_key="register-canonical-signal-v2",
        transition_idempotency_key="transition-canonical-signal-v2-research",
    )
    restored = service.get(result.registration.definition.model_id)
    assert restored == result
    assert restored.version == 1
    assert restored.registration.lifecycle_status is ModelLifecycleStatus.RESEARCH
    assert restored.registration.evidence_level is EvidenceLevel.EXPLORATORY


def test_freshness_rule_rejects_ambiguous_parameters() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        SignalFactorFreshnessRule(
            factor_name=SignalFactorName.TREND_RETURN,
            modes=(SignalFactorFreshnessMode.SAME_TRADING_SESSION,),
            maximum_session_lag=1,
            maximum_elapsed_seconds=None,
        )
