from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import ChildExecutionRequest
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.repository import (
    StateSystemConflict,
    StateSystemIntegrityError,
)
from market_regime_alpha.application.state_system.runtime import (
    STATE_SYSTEM_STAGE_ORDER,
    OrderedStateResearchPipeline,
    StateResearchStage,
    StateResearchStageArtifact,
    StateResearchStageContext,
    StateSystemRuntimeDelegate,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from tests.application.state_system.test_repositories import _active_claim
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory
from tests.persistence.postgres.test_continuous_research_journal import NOW, MutableClock


HASH = "sha256:" + "1" * 64


def _request(claim) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        trading_date=NOW.date(),
        as_of_time=NOW,
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        claim_id=claim.claim_id,
        fencing_token=claim.fencing_token,
        tick_version=claim.tick_version,
        lease_expires_at=claim.lease_expires_at,
        provider_attempt_id=1,
        source_manifest_id=ArtifactId("manifest-1"),
        source_manifest_hash=HASH,
        evidence_commit_id=ArtifactId("evidence-commit-1"),
        evidence_commit_hash=HASH,
        decision_id=ArtifactId("change-decision-1"),
        decision_hash=HASH,
        input_references=(
            RuntimeArtifactReference("FEATURE_MATERIALIZATION_OUTPUT", ArtifactId("feature-1"), HASH),
        ),
        configuration_references=(
            RuntimeArtifactReference("STATE_CONFIGURATION", ArtifactId("state-config-1"), HASH),
        ),
    )


@dataclass
class RecordingStage:
    stage: StateResearchStage
    calls: list[tuple[StateResearchStage, ...]]

    def execute(self, context: StateResearchStageContext) -> StateResearchStageArtifact:
        self.calls.append(tuple(item.stage for item in context.completed))
        digest = canonical_hash(
            {
                "stage": self.stage.value,
                "upstream": [item.artifact_hash for item in context.completed],
            }
        )
        return StateResearchStageArtifact(
            stage=self.stage,
            artifact_id=ArtifactId(f"state-stage-{self.stage.value.lower()}:{digest[7:]}"),
            artifact_hash=digest,
            available_at=context.request.as_of_time,
            data_eligibility=DataEligibility.EXPLORATORY,
            reason_codes=(f"{self.stage.value}_COMPLETED",),
        )


def _pipeline():
    services: dict[StateResearchStage, RecordingStage] = {}
    for stage in STATE_SYSTEM_STAGE_ORDER:
        services[stage] = RecordingStage(stage, [])
    return OrderedStateResearchPipeline(services=services), services


def test_state_runtime_child_executes_full_order_and_recovers_durable_receipt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    request = _request(claim)
    pipeline, services = _pipeline()
    delegate = StateSystemRuntimeDelegate(
        pipeline=pipeline,
        repository=PostgresStateSystemRepository(postgres_factory, clock=clock),
    )

    first = delegate.execute(request)
    recovered = delegate.lookup(request)
    replay = delegate.execute(request)

    assert first == recovered == replay
    assert first.child_kind is ContinuousChildKind.STATE_SYSTEM
    assert tuple(services[stage].calls[0] for stage in STATE_SYSTEM_STAGE_ORDER) == tuple(
        STATE_SYSTEM_STAGE_ORDER[:index]
        for index in range(len(STATE_SYSTEM_STAGE_ORDER))
    )
    assert all(len(service.calls) == 1 for service in services.values())
    assert delegate.entry_authority_granted is False
    assert delegate.broker_authority_granted is False


def test_state_runtime_receipt_is_fenced_after_pipeline_computation(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, stale = _active_claim(postgres_factory, clock)
    pipeline, _services = _pipeline()
    delegate = StateSystemRuntimeDelegate(
        pipeline=pipeline,
        repository=PostgresStateSystemRepository(postgres_factory, clock=clock),
    )
    clock.advance(timedelta(seconds=30))  # exact expiry is not active

    with pytest.raises(StateSystemConflict, match="stale"):
        delegate.execute(_request(stale))


def test_state_runtime_receipt_composition_is_recomputed_from_postgres(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    request = _request(claim)
    pipeline, _services = _pipeline()
    delegate = StateSystemRuntimeDelegate(
        pipeline=pipeline,
        repository=PostgresStateSystemRepository(postgres_factory, clock=clock),
    )
    delegate.execute(request)

    with postgres_factory.connection() as connection:
        persisted = connection.execute(
            """
            SELECT (receipt_json::jsonb)->>'schema', count(stage)
            FROM state_runtime_receipt AS receipt
            JOIN state_research_stage_authority AS stage
              ON stage.state_receipt_id = receipt.receipt_id
            WHERE receipt.run_id = %s AND receipt.tick_id = %s
            GROUP BY (receipt_json::jsonb)->>'schema'
            """,
            (str(request.run_id), str(request.tick_id)),
        ).fetchone()
        assert persisted == ("state_runtime_child_receipt/v2", 7)
        connection.execute(
            """
            ALTER TABLE state_research_stage_authority
            DISABLE TRIGGER state_research_stage_authority_no_update
            """
        )
        connection.execute(
            """
            UPDATE state_research_stage_authority
            SET artifact_hash = %s
            WHERE run_id = %s AND tick_id = %s AND stage = 'CANDIDATE'
            """,
            ("sha256:" + "2" * 64, str(request.run_id), str(request.tick_id)),
        )
        connection.execute(
            """
            ALTER TABLE state_research_stage_authority
            ENABLE TRIGGER state_research_stage_authority_no_update
            """
        )

    with pytest.raises(
        StateSystemIntegrityError,
        match="composition cannot be reproduced",
    ):
        delegate.lookup(request)


def test_state_runtime_rejects_future_stage_artifact() -> None:
    pipeline, services = _pipeline()
    service = services[StateResearchStage.CANDIDATE]
    original = service.execute

    def future(context: StateResearchStageContext) -> StateResearchStageArtifact:
        artifact = original(context)
        return StateResearchStageArtifact(
            stage=artifact.stage,
            artifact_id=artifact.artifact_id,
            artifact_hash=artifact.artifact_hash,
            available_at=context.request.lease_expires_at,
            data_eligibility=artifact.data_eligibility,
            reason_codes=artifact.reason_codes,
        )

    service.execute = future  # type: ignore[method-assign]
    claim = type(
        "Claim",
        (),
        {
            "run_id": ArtifactId("run"),
            "tick_id": ArtifactId("tick"),
            "tick_sequence": 1,
            "claim_id": "claim",
            "fencing_token": 1,
            "tick_version": 1,
            "lease_expires_at": NOW + timedelta(minutes=1),
        },
    )()

    with pytest.raises(ValueError, match="future evidence"):
        pipeline.execute(_request(claim))
