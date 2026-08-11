from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
import pytest

from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalResearchConflict,
    HistoricalRunStatus,
    HistoricalSessionStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchSessionStageReceipt,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from tests.application.historical_research.test_contracts import CREATED_AT, HASH, _command
from tests.universe.test_runtime_scope import _policy


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _receipt(command, claim) -> ResearchSessionStageReceipt:
    request = command.session_request(claim.trading_date)
    return ResearchSessionStageReceipt.create(
        request=request,
        stage=claim.stage,
        status=SessionStageStatus.COMPLETE,
        predecessors=claim.completed_prefix,
        input_references=tuple(
            reference
            for predecessor in claim.completed_prefix
            for reference in predecessor.output_references
        ),
        output_references=(
            ValidationArtifactReference(
                f"{claim.stage.value}_OUTPUT",
                ArtifactId(
                    f"{claim.trading_date.isoformat()}-{claim.stage.value.lower()}"
                ),
                HASH,
            ),
        ),
        completed_at=CREATED_AT,
        reason_codes=(f"{claim.stage.value}_COMPLETE",),
    )


def _journal(postgres_factory, clock, *, lease_duration=timedelta(minutes=10)):
    PostgresRuntimeScopeRepository(postgres_factory).register_policy(_policy())
    return PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=clock,
        lease_duration=lease_duration,
    )


def test_historical_journal_is_idempotent_and_orders_sessions(postgres_factory) -> None:
    clock = MutableClock(CREATED_AT)
    journal = _journal(postgres_factory, clock)
    command = _command()

    first = journal.create_or_get(command)
    second = journal.create_or_get(command)
    claim = journal.claim_next(command.run_id)

    assert first == second
    assert claim is not None
    assert claim.trading_date == command.trading_sessions[0]
    assert claim.stage.value == "SCOPE"
    session = journal.record_stage(claim=claim, receipt=_receipt(command, claim))
    assert session.status is HistoricalSessionStatus.PENDING
    assert session.receipts[0].stage.value == "SCOPE"
    assert journal.get_run(command.run_id).status is HistoricalRunStatus.RUNNING


def test_expired_claim_is_fenced_and_stale_writer_is_rejected(postgres_factory) -> None:
    clock = MutableClock(CREATED_AT)
    journal = _journal(
        postgres_factory,
        clock,
        lease_duration=timedelta(seconds=10),
    )
    command = _command()
    journal.create_or_get(command)
    stale = journal.claim_next(command.run_id)
    assert stale is not None
    clock.now += timedelta(seconds=11)

    replacement = journal.claim_next(command.run_id)

    assert replacement is not None
    assert replacement.fencing_token == stale.fencing_token + 1
    with pytest.raises(HistoricalResearchConflict, match="stale Historical stage claim"):
        journal.record_stage(claim=stale, receipt=_receipt(command, stale))
    journal.record_stage(
        claim=replacement,
        receipt=_receipt(command, replacement),
    )


def test_historical_stage_receipts_are_append_only(postgres_factory) -> None:
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    command = _command()
    journal.create_or_get(command)
    claim = journal.claim_next(command.run_id)
    assert claim is not None
    receipt = _receipt(command, claim)
    journal.record_stage(claim=claim, receipt=receipt)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="historical_research_stage_receipt is append-only",
    ):
        connection.execute(
            "UPDATE historical_research_stage_receipt "
            "SET payload_json = payload_json WHERE receipt_id = %s",
            (str(receipt.receipt_id),),
        )
