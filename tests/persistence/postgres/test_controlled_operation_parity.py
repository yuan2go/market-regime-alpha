from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.application.controlled_operation.journal import (
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageStatus,
)
from market_regime_alpha.application.controlled_operation.postgres_journal import (
    ControlledOperationClaimRejected,
    PostgresDecisionTimeOperationJournal,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.controlled_operation.test_journal import (
    NOW,
    MutableClock,
    _command,
    _receipt,
)


def test_postgres_controlled_operation_recovers_expired_claim_and_restarts(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal = PostgresDecisionTimeOperationJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    command = _command()
    created = journal.create_or_get(command)
    assert journal.create_or_get(command) == created
    old_claim = journal.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    with pytest.raises(ControlledOperationClaimRejected, match="active lease"):
        journal.claim_stage(
            run_id=command.run_id,
            stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
        )

    clock.advance(timedelta(seconds=31))
    resumed = journal.resume(command.run_id)
    assert resumed.stages[0].status is DecisionTimeOperationStageStatus.FAILED
    new_claim = journal.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    assert new_claim.claim_epoch == old_claim.claim_epoch + 1
    with pytest.raises(ControlledOperationClaimRejected, match="fencing"):
        journal.complete_stage(
            claim=old_claim,
            receipt=_receipt(old_claim),
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
        )
    completed = journal.complete_stage(
        claim=new_claim,
        receipt=_receipt(new_claim),
        run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
    )
    assert completed.stages[0].status is DecisionTimeOperationStageStatus.COMPLETED

    restarted = PostgresDecisionTimeOperationJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    assert restarted.get(command.run_id) == completed
