"""Behavior tests for the research-role migration model contract."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.research import model_contracts
from market_regime_alpha.research.model_contracts import (
    ResearchDomain,
    ResearchModel,
    ResearchModelRequest,
    ResearchModelResult,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)


def _request(**changes: object) -> ResearchModelRequest:
    request = ResearchModelRequest(
        as_of_time=AS_OF,
        configuration_id=ArtifactId("research-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-b")),
        input_hashes=(HASH_A, HASH_B),
        inputs=("market", "themes"),
        configuration=(("version", "1"),),
    )
    return replace(request, **changes)


def _result(**changes: object) -> ResearchModelResult:
    result = ResearchModelResult(
        model_id=ModelId("market-regime-research"),
        model_version="1.0.0",
        configuration_id=ArtifactId("research-configuration"),
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-b")),
        input_hashes=(HASH_A, HASH_B),
        as_of_time=AS_OF,
        state="NEUTRAL",
        score=Decimal("0.25"),
        reason_codes=("REGIME_NEUTRAL",),
        limitations=("FORMAL_OOS_ALPHA_NOT_ESTABLISHED",),
        validation_status="UNVALIDATED",
    )
    return replace(result, **changes)


class _ResearchStub:
    model_id = ModelId("research-stub")
    model_version = "1.0.0"
    research_domain = ResearchDomain.MARKET_REGIME

    def run(self, request: ResearchModelRequest) -> ResearchModelResult:
        return _result()


class _SignalLikeStub:
    model_id = ModelId("signal-stub")
    model_version = "1.0.0"
    supported_meanings = ("TREND_CONTINUATION",)

    def run(self, request: object) -> object:
        return request


def test_research_model_is_an_independent_runtime_protocol() -> None:
    assert isinstance(_ResearchStub(), ResearchModel)
    assert not isinstance(_SignalLikeStub(), ResearchModel)
    assert not hasattr(model_contracts, "Model")


def test_research_domain_is_strictly_scoped_to_research_responsibilities() -> None:
    assert {item.value for item in ResearchDomain} == {
        "MARKET_REGIME",
        "THEME_ROTATION",
        "CAPITAL_EVOLUTION",
        "CANDIDATE_DISCOVERY",
    }


def test_research_request_and_result_are_frozen_and_validate_metadata() -> None:
    request = _request()
    result = _result()

    with pytest.raises(FrozenInstanceError):
        setattr(request, "configuration", ())
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", "BULL")
    with pytest.raises(ValueError, match="timezone-aware"):
        _request(as_of_time=datetime(2026, 8, 4, 7, 0))
    with pytest.raises(ValueError, match="input_hash"):
        _result(input_hashes=(HASH_A, "bad-hash"))
    with pytest.raises(ValueError, match="sorted"):
        _result(limitations=("Z_LIMIT", "A_LIMIT"))
    with pytest.raises(TypeError, match="Decimal"):
        _result(score=0.25)
    with pytest.raises(ValueError, match="finite"):
        _result(score=Decimal("Infinity"))
