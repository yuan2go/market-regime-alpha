from __future__ import annotations

from datetime import UTC, datetime
import inspect

import pytest

from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    FormalForecastComputationRequest,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.core.identity import ArtifactId


def test_formal_forecast_request_contains_only_owner_references_and_scope() -> None:
    request = FormalForecastComputationRequest.create(
        formal_protocol_id=ArtifactId("formal-protocol-1"),
        formal_pit_evidence_id=ArtifactId("formal-pit-1"),
        symbol="000001.SZ",
        idempotency_key="compute-000001-20260101",
    )

    assert FormalForecastComputationRequest.from_canonical_dict(
        request.to_canonical_dict()
    ) == request
    assert "decision_time" not in request.to_canonical_dict()
    assert "materialized_at" not in request.to_canonical_dict()

    forged = {
        **request.to_canonical_dict(),
        "score": "0.99",
        "expected_return": "0.25",
    }
    with pytest.raises(ValueError, match="fields mismatch"):
        FormalForecastComputationRequest.from_canonical_dict(forged)

def test_formal_forecast_request_identity_rejects_caller_backdating() -> None:
    request = FormalForecastComputationRequest.create(
        formal_protocol_id=ArtifactId("formal-protocol-1"),
        formal_pit_evidence_id=ArtifactId("formal-pit-1"),
        symbol="000001.SZ",
        idempotency_key="compute-000001-20260101",
    )
    forged = {
        **request.to_canonical_dict(),
        "created_at": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
    }

    with pytest.raises(ValueError, match="fields mismatch"):
        FormalForecastComputationRequest.from_canonical_dict(forged)


def test_formal_forecast_repository_has_no_per_call_executor_injection() -> None:
    parameters = inspect.signature(
        PostgresFormalProtocolRepository.compute_forecast
    ).parameters

    assert "executor" not in parameters
    assert "executors" not in parameters
    assert "executor_set" not in parameters
