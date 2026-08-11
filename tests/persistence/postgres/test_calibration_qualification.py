from __future__ import annotations

from market_regime_alpha.application.research_validation.phase_c_gates import (
    PhaseCStageOutcome,
)
from market_regime_alpha.application.research_validation.postgres_calibration_qualification import (
    PostgresCalibrationQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_phase_c_gates import (
    PostgresPhaseCGateAuthority,
)
from market_regime_alpha.application.research_validation.qualification import (
    QualificationOutcome,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    record_phase_c_protocol_owners,
)


def test_calibration_owner_records_real_missing_oos_as_blocked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = fixture.protocol
    policy = fixture.calibration_policy
    entry_policy = fixture.entry_policy
    PostgresFormalProtocolRepository(postgres_factory).record_protocol(
        protocol=protocol
    )
    authority = PostgresCalibrationQualificationAuthority(postgres_factory)

    decision = authority.qualify(
        policy=policy,
        formal_protocol_id=protocol.protocol_id,
        calibration_artifact_id=None,
        actor="phase-c-test",
        reason="resolve C5 against PostgreSQL evidence",
        idempotency_key="phase-c5-blocked",
    )
    replayed = authority.qualify(
        policy=policy,
        formal_protocol_id=protocol.protocol_id,
        calibration_artifact_id=None,
        actor="phase-c-test",
        reason="resolve C5 against PostgreSQL evidence",
        idempotency_key="phase-c5-blocked",
    )

    assert replayed == decision
    assert decision.outcome is QualificationOutcome.BLOCKED
    assert decision.calibrated is False
    assert decision.reason_codes == ("FORMAL_OOS_QUALIFICATION_MISSING",)

    gates = PostgresPhaseCGateAuthority(postgres_factory)
    strategy = gates.resolve_entry_holding_exit(
        formal_protocol_id=protocol.protocol_id,
        policy=entry_policy,
        actor="phase-c-test",
        reason="resolve C6 against PostgreSQL evidence",
        idempotency_key="phase-c6-blocked",
    )
    admission = gates.resolve_production_admission(
        formal_protocol_id=protocol.protocol_id,
        governance_version="phase-c8-v1",
        actor="phase-c-test",
        reason="resolve C8 against PostgreSQL evidence",
        idempotency_key="phase-c8-blocked",
    )
    execution = gates.resolve_controlled_execution(
        formal_protocol_id=protocol.protocol_id,
        actor="phase-c-test",
        reason="resolve C9 against PostgreSQL evidence",
        idempotency_key="phase-c9-blocked",
    )

    assert strategy.outcome is PhaseCStageOutcome.BLOCKED
    with postgres_factory.connection(read_only=True) as connection:
        stored_entry_policy = connection.execute(
            "SELECT policy_hash FROM entry_holding_exit_qualification_policy"
        ).fetchone()
    assert stored_entry_policy == (entry_policy.policy_hash,)
    assert admission.production_authorized is False
    assert execution.outcome is PhaseCStageOutcome.BLOCKED
    assert "BROKER_CONTRACT_MISSING" in execution.reason_codes
