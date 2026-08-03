from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable, TypeVar

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.daily_decision import DecisionPriceSnapshot
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence import ArtifactEnvelope
import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.position import (
    CapitalEvolutionStateInRule,
    CapitalRuleScope,
    ManualInvalidationEvidence,
    PriceAboveRule,
    SignalStateInRule,
    ThesisHealth,
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisHealthSupportState,
    ThesisInvalidationRuleSet,
    ThemeRotationStateInRule,
    TradePermissionInRule,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
    TradePermission,
)
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationSnapshot,
)
from market_regime_alpha.forecasting import PathForecast
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals import SignalSnapshot, SignalState

from tests.position.thesis_health_fixtures import (
    ASSESSED_AT,
    RESEARCH_AT,
    SOURCE_MANIFEST_ID,
    H5Fixture,
    make_h5_fixture,
)


T = TypeVar("T")


def _bundle(fixture: H5Fixture, **changes: object) -> ThesisHealthInputBundle:
    values: dict[str, object] = {
        "thesis": fixture.thesis,
        "opportunity": fixture.opportunity,
        "market_regime": fixture.market,
        "theme_rotation": fixture.theme,
        "capital_evolution": fixture.capital,
        "candidate_set": fixture.candidate,
        "signal_snapshot": fixture.signal,
        "path_forecast": fixture.path,
        "price_snapshot": fixture.price,
        "configuration": fixture.configuration,
        "rule_set": fixture.rule_set,
        "manual_evidence": (),
        "prior_observation": None,
        "assessed_at": ASSESSED_AT,
        "actor": "reviewer-a",
        "reason": "artifact-derived H5 fixture",
    }
    values.update(changes)
    return ThesisHealthInputBundle.create(**values)


def _rebind(
    value: T,
    reader: Callable[[dict[str, Any]], T],
    *,
    payload_changes: dict[str, object] | None = None,
    inputs: tuple[tuple[ArtifactId, str], ...] | None = None,
    decision_at=RESEARCH_AT,
    source_manifest_id=SOURCE_MANIFEST_ID,
    source_manifest_hash: str | None = None,
) -> T:
    canonical = value.to_canonical_dict()  # type: ignore[attr-defined]
    old = value.envelope  # type: ignore[attr-defined]
    artifact_payload = {key: item for key, item in canonical.items() if key != "envelope"}
    artifact_payload.update(payload_changes or {})
    input_pairs = (
        tuple(zip(old.input_artifact_ids, old.input_content_hashes, strict=True))
        if inputs is None
        else inputs
    )
    envelope = ArtifactEnvelope.create(
        artifact_type=old.artifact_type,
        artifact_payload=artifact_payload,
        decision_date=decision_at.date(),
        decision_time=DecisionTime(decision_at),
        created_at=decision_at + timedelta(seconds=10),
        code_revision=old.code_revision,
        configuration_id=old.configuration_id,
        configuration_hash=old.configuration_hash,
        source_manifest_id=source_manifest_id,
        source_manifest_hash=source_manifest_hash or old.source_manifest_hash,
        input_artifact_ids=tuple(item[0] for item in input_pairs),
        input_content_hashes=tuple(item[1] for item in input_pairs),
        model_id=old.model_id,
        model_version=old.model_version,
        data_eligibility=old.data_eligibility,
        evidence_authority=old.evidence_authority,
        status=old.status,
        reason_codes=old.reason_codes,
        limitations=old.limitations,
    )
    return reader({"envelope": envelope.to_canonical_dict(), **artifact_payload})


def _price_at(fixture: H5Fixture, *, minutes_after_research: int, available_offset_seconds: int = -1) -> DecisionPriceSnapshot:
    observation = fixture.price.observations[0]
    price_time = RESEARCH_AT + timedelta(minutes=minutes_after_research)
    updated = replace(
        observation,
        event_time=price_time - timedelta(seconds=2),
        available_time=AvailabilityTime(
            price_time + timedelta(seconds=available_offset_seconds)
        ),
    )
    return DecisionPriceSnapshot(
        source_manifest_id=fixture.price.source_manifest_id,
        decision_time=DecisionTime(price_time),
        observations=(updated,),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _cascade_signal(
    fixture: H5Fixture,
    signal: SignalSnapshot,
) -> tuple[SignalSnapshot, PathForecast]:
    path = _rebind(
        fixture.path,
        PathForecast.from_canonical_dict,
        inputs=((signal.envelope.artifact_id, signal.envelope.content_hash),),
    )
    return signal, path


def _cascade_theme_capital_candidate(
    fixture: H5Fixture,
    *,
    theme: ThemeRotationSnapshot | None = None,
    capital: CapitalEvolutionSnapshot | None = None,
) -> tuple[ThemeRotationSnapshot, CapitalEvolutionSnapshot, CandidateSet, SignalSnapshot, PathForecast]:
    current_theme = theme or fixture.theme
    current_capital = capital or _rebind(
        fixture.capital,
        CapitalEvolutionSnapshot.from_canonical_dict,
        inputs=((current_theme.envelope.artifact_id, current_theme.envelope.content_hash),),
    )
    candidate = _rebind(
        fixture.candidate,
        CandidateSet.from_canonical_dict,
        inputs=(
            (fixture.market.envelope.artifact_id, fixture.market.envelope.content_hash),
            (current_theme.envelope.artifact_id, current_theme.envelope.content_hash),
            (current_capital.envelope.artifact_id, current_capital.envelope.content_hash),
        ),
    )
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
    )
    signal, path = _cascade_signal(fixture, signal)
    return current_theme, current_capital, candidate, signal, path


def _rule_set_with(
    fixture: H5Fixture,
    *,
    condition_id: str,
    replacement: object,
) -> ThesisInvalidationRuleSet:
    return ThesisInvalidationRuleSet.create(
        thesis_id=fixture.thesis.thesis_id,
        thesis_version=fixture.thesis.version,
        rules=tuple(
            replacement if item.condition_id == condition_id else item
            for item in fixture.rule_set.rules
        ),
    )


def test_input_bundle_is_content_addressed_and_uses_actual_types() -> None:
    bundle = _bundle(make_h5_fixture())

    assert ThesisHealthInputBundle.from_canonical_dict(
        bundle.to_canonical_dict()
    ) == bundle

    with pytest.raises(TypeError, match="SignalSnapshot"):
        _bundle(make_h5_fixture(), signal_snapshot={"symbol": "000001.SZ"})


def test_all_verified_support_derives_healthy() -> None:
    observation = ThesisHealthObservationBuilder().build(
        _bundle(make_h5_fixture())
    )

    assert observation.observed_health_state is ThesisHealth.HEALTHY
    assert observation.effective_health_state is ThesisHealth.HEALTHY
    assert observation.market_support_state is ThesisHealthSupportState.SUPPORTED
    assert observation.signal_support_state is ThesisHealthSupportState.SUPPORTED
    assert observation.path_support_state is ThesisHealthSupportState.SUPPORTED
    assert observation.theme_support_state is ThesisHealthSupportState.SUPPORTED
    assert observation.capital_support_state is ThesisHealthSupportState.SUPPORTED
    assert observation.triggered_condition_ids == ()


def test_current_signal_must_bind_current_candidate() -> None:
    fixture = make_h5_fixture()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        inputs=((ArtifactId("different-candidate"), "sha256:" + "8" * 64),),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "CURRENT_SIGNAL_CANDIDATE_LINEAGE_MISMATCH" in observation.missing_reason_codes


def test_current_candidate_must_bind_same_market_theme_and_capital() -> None:
    fixture = make_h5_fixture()
    candidate = _rebind(
        fixture.candidate,
        CandidateSet.from_canonical_dict,
        inputs=((ArtifactId("different-market-bundle"), "sha256:" + "7" * 64),),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, candidate_set=candidate)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "CURRENT_CANDIDATE_RESEARCH_LINEAGE_MISMATCH" in observation.missing_reason_codes


def test_price_may_be_later_than_research_within_explicit_skew() -> None:
    fixture = make_h5_fixture()
    price = _price_at(fixture, minutes_after_research=4)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, price_snapshot=price)
    )
    assert observation.observed_health_state is ThesisHealth.HEALTHY
    assert observation.market_price == 10.5


def test_price_beyond_research_skew_is_data_insufficient() -> None:
    fixture = make_h5_fixture()
    price = _price_at(fixture, minutes_after_research=6)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, price_snapshot=price)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "PRICE_RESEARCH_TIME_SKEW_EXCEEDED" in observation.missing_reason_codes


def test_stale_price_is_data_insufficient() -> None:
    fixture = make_h5_fixture()
    configuration_values = {
        name: getattr(fixture.configuration, name)
        for name in fixture.configuration.semantic_payload()
        if name != "schema_version"
    }
    configuration_values["maximum_price_age_seconds"] = 60.0
    configuration = fixture.configuration.create(**configuration_values)
    price = _price_at(fixture, minutes_after_research=2)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, configuration=configuration, price_snapshot=price)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "PRICE_OBSERVATION_STALE" in observation.missing_reason_codes


def test_research_chain_cannot_precede_creation_opportunity_evidence() -> None:
    fixture = make_h5_fixture()
    earlier = RESEARCH_AT - timedelta(minutes=1)
    market = _rebind(
        fixture.market,
        type(fixture.market).from_canonical_dict,
        decision_at=earlier,
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, market_regime=market)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "CURRENT_RESEARCH_PRECEDES_THESIS_CREATION_EVIDENCE" in observation.missing_reason_codes


def test_source_manifest_lineage_mismatch_is_data_insufficient() -> None:
    fixture = make_h5_fixture()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        source_manifest_hash="sha256:" + "9" * 64,
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "CURRENT_RESEARCH_SOURCE_MANIFEST_MISMATCH" in observation.missing_reason_codes


def test_weak_signal_derives_weakening_without_using_score_alone() -> None:
    fixture = make_h5_fixture()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        payload_changes={"volume_confirmation_state": "UNCONFIRMED"},
    )
    signal, path = _cascade_signal(fixture, signal)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal, path_forecast=path)
    )
    assert observation.signal_support_state is ThesisHealthSupportState.WEAKENING
    assert observation.observed_health_state is ThesisHealth.WEAKENING


def test_weak_theme_derives_weakening() -> None:
    fixture = make_h5_fixture()
    theme_payload = fixture.theme.to_canonical_dict()["themes"][0]
    theme_payload["rotation_state"] = "WEAKENING"
    theme = _rebind(
        fixture.theme,
        ThemeRotationSnapshot.from_canonical_dict,
        payload_changes={"themes": [theme_payload]},
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, theme=theme
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
        )
    )
    assert observation.theme_support_state is ThesisHealthSupportState.WEAKENING
    assert observation.observed_health_state is ThesisHealth.WEAKENING


def test_weak_capital_requires_theme_and_symbol_evidence() -> None:
    fixture = make_h5_fixture()
    capital_payload = fixture.capital.to_canonical_dict()
    capital_payload["themes"][0]["capital_evolution_state"] = "EXHAUSTION"
    capital = _rebind(
        fixture.capital,
        CapitalEvolutionSnapshot.from_canonical_dict,
        payload_changes={
            "themes": capital_payload["themes"],
            "symbols": capital_payload["symbols"],
        },
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, capital=capital
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
        )
    )
    assert observation.capital_support_state is ThesisHealthSupportState.WEAKENING
    assert observation.observed_health_state is ThesisHealth.WEAKENING


def test_extreme_risk_typed_rule_invalidates() -> None:
    fixture = make_h5_fixture()
    market = _rebind(
        fixture.market,
        MarketRegimeSnapshot.from_canonical_dict,
        payload_changes={"market_state": "EXTREME_RISK"},
    )
    candidate = _rebind(
        fixture.candidate,
        CandidateSet.from_canonical_dict,
        inputs=(
            (market.envelope.artifact_id, market.envelope.content_hash),
            (fixture.theme.envelope.artifact_id, fixture.theme.envelope.content_hash),
            (fixture.capital.envelope.artifact_id, fixture.capital.envelope.content_hash),
        ),
    )
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
    )
    signal, path = _cascade_signal(fixture, signal)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            market_regime=market,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
        )
    )
    assert observation.triggered_condition_ids == ("market-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_trade_permission_typed_rule_invalidates() -> None:
    fixture = make_h5_fixture()
    market = _rebind(
        fixture.market,
        MarketRegimeSnapshot.from_canonical_dict,
        payload_changes={"trade_permission": "PROHIBIT"},
    )
    candidate = _rebind(
        fixture.candidate,
        CandidateSet.from_canonical_dict,
        inputs=(
            (market.envelope.artifact_id, market.envelope.content_hash),
            (fixture.theme.envelope.artifact_id, fixture.theme.envelope.content_hash),
            (fixture.capital.envelope.artifact_id, fixture.capital.envelope.content_hash),
        ),
    )
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
    )
    signal, path = _cascade_signal(fixture, signal)
    rule_set = _rule_set_with(
        fixture,
        condition_id="market-stop",
        replacement=TradePermissionInRule(
            "market-stop", (TradePermission.PROHIBIT,)
        ),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            market_regime=market,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
            rule_set=rule_set,
        )
    )
    assert observation.triggered_condition_ids == ("market-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_price_above_typed_rule_invalidates() -> None:
    fixture = make_h5_fixture()
    rule_set = _rule_set_with(
        fixture,
        condition_id="price-stop",
        replacement=PriceAboveRule("price-stop", 10.0),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, rule_set=rule_set)
    )
    assert observation.triggered_condition_ids == ("price-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_theme_typed_rule_invalidates() -> None:
    fixture = make_h5_fixture()
    theme_payload = fixture.theme.to_canonical_dict()["themes"][0]
    theme_payload["rotation_state"] = RotationState.FAILED.value
    theme = _rebind(
        fixture.theme,
        ThemeRotationSnapshot.from_canonical_dict,
        payload_changes={"themes": [theme_payload]},
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, theme=theme
    )
    rule_set = _rule_set_with(
        fixture,
        condition_id="theme-stop",
        replacement=ThemeRotationStateInRule(
            "theme-stop", (RotationState.FAILED,)
        ),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
            rule_set=rule_set,
        )
    )
    assert observation.triggered_condition_ids == ("theme-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_capital_both_scope_typed_rule_requires_and_invalidates_both_entries() -> None:
    fixture = make_h5_fixture()
    payload = fixture.capital.to_canonical_dict()
    payload["themes"][0]["capital_evolution_state"] = (
        CapitalEvolutionState.COLLAPSE.value
    )
    payload["symbols"][0]["capital_evolution_state"] = (
        CapitalEvolutionState.COLLAPSE.value
    )
    capital = _rebind(
        fixture.capital,
        CapitalEvolutionSnapshot.from_canonical_dict,
        payload_changes={"themes": payload["themes"], "symbols": payload["symbols"]},
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, capital=capital
    )
    rule_set = _rule_set_with(
        fixture,
        condition_id="capital-stop",
        replacement=CapitalEvolutionStateInRule(
            "capital-stop",
            CapitalRuleScope.BOTH,
            (CapitalEvolutionState.COLLAPSE,),
        ),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
            rule_set=rule_set,
        )
    )
    assert observation.triggered_condition_ids == ("capital-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


@pytest.mark.parametrize(
    ("scope", "payload_key"),
    (
        (CapitalRuleScope.THEME, "themes"),
        (CapitalRuleScope.SYMBOL, "symbols"),
    ),
)
def test_capital_single_scope_typed_rule_invalidates_its_explicit_entry(
    scope: CapitalRuleScope,
    payload_key: str,
) -> None:
    fixture = make_h5_fixture()
    payload = fixture.capital.to_canonical_dict()
    payload[payload_key][0]["capital_evolution_state"] = (
        CapitalEvolutionState.COLLAPSE.value
    )
    capital = _rebind(
        fixture.capital,
        CapitalEvolutionSnapshot.from_canonical_dict,
        payload_changes={"themes": payload["themes"], "symbols": payload["symbols"]},
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, capital=capital
    )
    rule_set = _rule_set_with(
        fixture,
        condition_id="capital-stop",
        replacement=CapitalEvolutionStateInRule(
            "capital-stop",
            scope,
            (CapitalEvolutionState.COLLAPSE,),
        ),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
            rule_set=rule_set,
        )
    )
    assert observation.triggered_condition_ids == ("capital-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_signal_typed_rule_invalidates() -> None:
    fixture = make_h5_fixture()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        payload_changes={"signal_state": SignalState.INACTIVE.value},
    )
    signal, path = _cascade_signal(fixture, signal)
    rule_set = _rule_set_with(
        fixture,
        condition_id="signal-stop",
        replacement=SignalStateInRule("signal-stop", (SignalState.INACTIVE,)),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            signal_snapshot=signal,
            path_forecast=path,
            rule_set=rule_set,
        )
    )
    assert observation.triggered_condition_ids == ("signal-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_price_invalidation_has_priority_over_missing_capital() -> None:
    fixture = make_h5_fixture()
    capital = _rebind(
        fixture.capital,
        CapitalEvolutionSnapshot.from_canonical_dict,
        payload_changes={"themes": [], "symbols": []},
    )
    theme, capital, candidate, signal, path = _cascade_theme_capital_candidate(
        fixture, capital=capital
    )
    price_item = replace(fixture.price.observations[0], price=8.5)
    price = DecisionPriceSnapshot(
        source_manifest_id=fixture.price.source_manifest_id,
        decision_time=fixture.price.decision_time,
        observations=(price_item,),
        data_eligibility=fixture.price.data_eligibility,
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            theme_rotation=theme,
            capital_evolution=capital,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
            price_snapshot=price,
        )
    )
    assert "CURRENT_CAPITAL_THEME_MISSING" in observation.missing_reason_codes
    assert observation.triggered_condition_ids == ("price-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED


def test_time_invalidation_has_priority_over_stale_research() -> None:
    fixture = make_h5_fixture()

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=fixture.thesis.time_invalidation)
    )
    assert observation.triggered_condition_ids == ("time-stop",)
    assert observation.observed_health_state is ThesisHealth.INVALIDATED
    assert observation.missing_reason_codes


def test_manual_condition_absence_is_not_missing_but_valid_evidence_invalidates() -> None:
    fixture = make_h5_fixture()
    without_manual = ThesisHealthObservationBuilder().build(_bundle(fixture))
    evidence = ManualInvalidationEvidence.create(
        thesis_id=fixture.thesis.thesis_id,
        thesis_version=fixture.thesis.version,
        condition_id="manual-stop",
        actor="reviewer-a",
        reason="explicit manual invalidation",
        recorded_at=ASSESSED_AT - timedelta(seconds=2),
        availability_time=ASSESSED_AT - timedelta(seconds=1),
    )
    with_manual = ThesisHealthObservationBuilder().build(
        _bundle(fixture, manual_evidence=(evidence,))
    )

    assert without_manual.observed_health_state is ThesisHealth.HEALTHY
    assert "manual-stop" not in without_manual.triggered_condition_ids
    assert with_manual.triggered_condition_ids == ("manual-stop",)
    assert with_manual.observed_health_state is ThesisHealth.INVALIDATED


def test_future_manual_evidence_is_data_insufficient_not_triggered() -> None:
    fixture = make_h5_fixture()
    evidence = ManualInvalidationEvidence.create(
        thesis_id=fixture.thesis.thesis_id,
        thesis_version=fixture.thesis.version,
        condition_id="manual-stop",
        actor="reviewer-a",
        reason="future evidence",
        recorded_at=ASSESSED_AT + timedelta(seconds=1),
        availability_time=ASSESSED_AT + timedelta(seconds=2),
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, manual_evidence=(evidence,))
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert observation.triggered_condition_ids == ()
    assert "MANUAL_INVALIDATION_EVIDENCE_FROM_FUTURE" in observation.missing_reason_codes


def test_missing_primary_theme_is_explicit_data_insufficient() -> None:
    fixture = make_h5_fixture()
    record = fixture.candidate.to_canonical_dict()["records"][0]
    record["primary_theme_id"] = None
    candidate = _rebind(
        fixture.candidate,
        CandidateSet.from_canonical_dict,
        payload_changes={"records": [record]},
    )
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
    )
    signal, path = _cascade_signal(fixture, signal)

    observation = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=path,
        )
    )
    assert observation.primary_theme_id is None
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "CURRENT_CANDIDATE_PRIMARY_THEME_NOT_ESTABLISHED" in observation.missing_reason_codes


def test_missing_price_observation_is_explicit_data_insufficient() -> None:
    fixture = make_h5_fixture()
    price = DecisionPriceSnapshot(
        source_manifest_id=fixture.price.source_manifest_id,
        decision_time=fixture.price.decision_time,
        observations=(),
        data_eligibility=fixture.price.data_eligibility,
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, price_snapshot=price)
    )
    assert observation.market_price is None
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "PRICE_OBSERVATION_MISSING" in observation.missing_reason_codes


@pytest.mark.parametrize(
    ("artifact", "field", "expected_reason"),
    (
        ("signal", "symbol", "CURRENT_SIGNAL_SYMBOL_MISMATCH"),
        ("path", "symbol", "CURRENT_PATH_SYMBOL_MISMATCH"),
    ),
)
def test_current_symbol_scope_mismatch_is_data_insufficient(
    artifact: str, field: str, expected_reason: str
) -> None:
    fixture = make_h5_fixture()
    if artifact == "signal":
        signal = _rebind(
            fixture.signal,
            SignalSnapshot.from_canonical_dict,
            payload_changes={field: "000002.SZ"},
        )
        signal, path = _cascade_signal(fixture, signal)
    else:
        signal = fixture.signal
        path = _rebind(
            fixture.path,
            PathForecast.from_canonical_dict,
            payload_changes={field: "000002.SZ"},
        )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal, path_forecast=path)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert expected_reason in observation.missing_reason_codes


def test_incomplete_thesis_creation_evidence_is_data_insufficient() -> None:
    fixture = make_h5_fixture()
    thesis = replace(
        fixture.thesis,
        supporting_evidence=fixture.thesis.supporting_evidence[:-1],
    )

    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, thesis=thesis)
    )
    assert observation.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert "THESIS_CREATION_EVIDENCE_INCOMPLETE" in observation.missing_reason_codes
