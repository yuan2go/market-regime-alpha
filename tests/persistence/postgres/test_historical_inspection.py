import json
import os

import psycopg
import pytest

from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.settings import DatabaseSettings


@pytest.mark.unmigrated_postgres
def test_read_only_scope_cannot_be_downgraded_by_a_repository(postgres_factory) -> None:
    with postgres_factory.connection() as connection:
        connection.execute("CREATE TABLE read_only_probe (value integer NOT NULL)")
    settings = DatabaseSettings.from_sources(
        database_url=os.environ["MARKET_REGIME_ALPHA_TEST_DATABASE_URL"], environ={},
    )
    with PostgresConnectionFactory(
        settings, application_schema=postgres_factory.application_schema, read_only=True,
    ) as reader:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with reader.connection(read_only=False) as connection:
                connection.execute("INSERT INTO read_only_probe VALUES (1)")
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            reader.run_transaction(lambda connection: connection.execute("INSERT INTO read_only_probe VALUES (2)"))
        with reader.connection() as connection:
            assert connection.execute("SELECT count(*) FROM read_only_probe").fetchone() == (0,)
            assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)


def test_historical_runtime_report_and_replay_preserve_exact_rows(postgres_factory, capsys) -> None:
    from market_regime_alpha.application.continuous_research.postgres_journal import PostgresContinuousResearchJournal
    from market_regime_alpha.application.continuous_research.replay import replay_continuous_research
    from market_regime_alpha.cli.inspect_historical_runtime import main
    from tests.persistence.postgres.test_continuous_research_journal import NOW, _command, _tick, _receipt
    from market_regime_alpha.application.continuous_research.policy import ContinuousSessionPhase
    from market_regime_alpha.application.continuous_research.journal import ContinuousRunState

    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(_tick(command), session_phase=ContinuousSessionPhase.DECISION_WINDOW)
    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)
    journal.complete_tick(claim=claim, receipt=_receipt(claim), run_state=ContinuousRunState.WAITING_FOR_NEW_DATA)
    before = journal.get_run(command.run_id)
    expected = replay_continuous_research(journal, command.run_id).to_canonical_dict()
    assert expected["tick_count"] == expected["receipt_count"] == 1
    scope = ["--database-url", os.environ["MARKET_REGIME_ALPHA_TEST_DATABASE_URL"],
             "--application-schema", postgres_factory.application_schema]
    for operation in ("runtime-report", "runtime-replay", "runtime-replay"):
        assert main([*scope, operation, "--run-id", str(command.run_id)]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["scope"] == "HISTORICAL_READ_ONLY"
        assert result["current_execution_authority"] is False
        if operation == "runtime-replay":
            assert result["result"] == expected
        assert journal.get_run(command.run_id) == before
