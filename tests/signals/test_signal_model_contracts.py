"""Behavior tests for the signal-role migration model contract."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.signals import model_contracts
from market_regime_alpha.signals.model_contracts import (
    SignalMeaning,
    SignalModel,
    SignalModelRequest,
    SignalModelResult,
)


HASH_A = "sha256:" + "a" * 64
AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)


def _request(**changes: object) -> SignalModelRequest:
    request = SignalModelRequest(
        as_of_time=AS_OF,
        configuration_id=ArtifactId("signal-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"),),
        input_hashes=(HASH_A,),
        inputs=("research-artifact",),
        configuration=(("version", "1"),),
    )
    return replace(request, **changes)


def _result(**changes: object) -> SignalModelResult:
    result = SignalModelResult(
        model_id=ModelId("signal-model"),
        model_version="1.0.0",
        configuration_id=ArtifactId("signal-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"),),
        input_hashes=(HASH_A,),
        as_of_time=AS_OF,
        state=SignalMeaning.TREND_CONTINUATION,
        score=Decimal("0.40"),
        reason_codes=("TREND_PERSISTS",),
        limitations=("UNCALIBRATED_SCORE",),
        validation_status="UNVALIDATED",
    )
    return replace(result, **changes)


class _SignalStub:
    model_id = ModelId("signal-stub")
    model_version = "1.0.0"
    supported_meanings = tuple(SignalMeaning)

    def run(self, request: SignalModelRequest) -> SignalModelResult:
        return _result()


class _ResearchLikeStub:
    model_id = ModelId("research-stub")
    model_version = "1.0.0"
    research_domain = "MARKET_REGIME"

    def run(self, request: object) -> object:
        return request


def test_signal_model_is_an_independent_runtime_protocol() -> None:
    assert isinstance(_SignalStub(), SignalModel)
    assert not isinstance(_ResearchLikeStub(), SignalModel)
    assert not hasattr(model_contracts, "Model")


def test_signal_meaning_contains_only_observation_semantics() -> None:
    assert {item.value for item in SignalMeaning} == {
        "ENTRY_CONFIRMATION",
        "TREND_CONTINUATION",
        "REVERSAL_WARNING",
        "SELL_PRESSURE",
        "OVERHEAT",
        "VOLUME_CONFIRMATION",
    }
    for prohibited in ("ORDER", "BROKER_ORDER", "FILL", "AUTO_EXECUTE", "BUY"):
        with pytest.raises(ValueError):
            SignalMeaning(prohibited)


def test_signal_contract_rejects_untyped_semantics_and_bad_trace_metadata() -> None:
    assert _result().state is SignalMeaning.TREND_CONTINUATION

    with pytest.raises(TypeError, match="SignalMeaning"):
        _result(state="TREND_CONTINUATION")
    with pytest.raises(ValueError, match="align"):
        _request(input_hashes=())
    with pytest.raises(ValueError, match="unique"):
        _result(reason_codes=("SAME", "SAME"))
    with pytest.raises(ValueError, match="model_version"):
        _result(model_version=" 1.0.0")
