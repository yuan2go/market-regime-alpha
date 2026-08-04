"""Behavior tests for the decision-role migration model contract."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.decision import model_contracts
from market_regime_alpha.decision.model_contracts import (
    DecisionModel,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionOutcome,
)


HASH_A = "sha256:" + "a" * 64
AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)


def _request(**changes: object) -> DecisionModelRequest:
    request = DecisionModelRequest(
        as_of_time=AS_OF,
        configuration_id=ArtifactId("decision-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"),),
        input_hashes=(HASH_A,),
        inputs=("signal-artifact",),
        configuration=(("version", "1"),),
    )
    return replace(request, **changes)


def _result(**changes: object) -> DecisionModelResult:
    result = DecisionModelResult(
        model_id=ModelId("decision-model"),
        model_version="1.0.0",
        configuration_id=ArtifactId("decision-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"),),
        input_hashes=(HASH_A,),
        as_of_time=AS_OF,
        state=DecisionOutcome.WAIT,
        score=None,
        reason_codes=("ENTRY_NOT_CONFIRMED",),
        limitations=("MANUAL_EXECUTION_ONLY",),
        validation_status="UNVALIDATED",
    )
    return replace(result, **changes)


class _DecisionStub:
    model_id = ModelId("decision-stub")
    model_version = "1.0.0"

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        return _result()


class _SignalLikeStub:
    model_id = ModelId("signal-stub")
    model_version = "1.0.0"
    supported_meanings = ("TREND_CONTINUATION",)

    def run(self, request: object) -> object:
        return request


def test_decision_model_is_an_independent_runtime_protocol() -> None:
    assert isinstance(_DecisionStub(), DecisionModel)
    assert not isinstance(_SignalLikeStub(), DecisionModel)
    assert not hasattr(model_contracts, "Model")


def test_decision_outcome_has_no_order_or_automatic_execution_semantics() -> None:
    assert {item.value for item in DecisionOutcome} == {
        "REJECT",
        "WAIT",
        "READY_FOR_MANUAL_CONFIRMATION",
        "REDUCE",
        "EXIT",
    }
    for prohibited in (
        "BUY",
        "SELL_ORDER",
        "BROKER_ORDER",
        "FILL",
        "AUTO_EXECUTE",
        "ENTER_SIMULATION",
    ):
        with pytest.raises(ValueError):
            DecisionOutcome(prohibited)


def test_decision_contract_requires_typed_outcome_and_strict_metadata() -> None:
    assert _result(score=Decimal("-0.1")).score == Decimal("-0.1")

    with pytest.raises(TypeError, match="DecisionOutcome"):
        _result(state="WAIT")
    with pytest.raises(ValueError, match="timezone-aware"):
        _request(as_of_time=datetime(2026, 8, 4, 7, 0))
    with pytest.raises(ValueError, match="sorted"):
        _result(reason_codes=("Z_REASON", "A_REASON"))
    with pytest.raises(ValueError, match="validation_status"):
        _result(validation_status="")
