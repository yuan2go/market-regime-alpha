from __future__ import annotations

import json
import os

from market_regime_alpha.cli.pit_authority import main
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory as postgres_factory,
)
from tests.persistence.postgres.pit_fixture import (
    INGEST_TIME,
    MutableClock,
    NOW,
    authorize_source,
    pit_fact,
    pit_authority,
    pit_request,
    required_facts,
)


def _authority(factory: PostgresConnectionFactory) -> list[str]:
    return [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--database-schema",
        factory.application_schema,
    ]


def test_cli_inspects_and_replays_formal_pit_evidence(
    postgres_factory: PostgresConnectionFactory,
    capsys,
) -> None:
    clock = MutableClock(INGEST_TIME)
    pit = pit_authority(postgres_factory, clock=clock)
    authorize_source(pit, idempotency_key="cli-authorize-source")
    for index, required in enumerate(required_facts()):
        pit.record_fact(
            pit_fact(required),
            actor="source-ingestor",
            reason="record CLI fixture",
            idempotency_key=f"cli-pit-fact-{index}",
        )
    clock.value = NOW
    evidence = pit.validate(pit_request(idempotency_key="cli-pit-validate"))

    assert main([*_authority(postgres_factory), "revision"]) == 0
    revision = json.loads(capsys.readouterr().out)
    assert revision["authority_revision"] == pit.current_revision()

    for operation in ("inspect-evidence", "replay-evidence"):
        assert main(
            [
                *_authority(postgres_factory),
                operation,
                "--evidence-id",
                str(evidence.evidence_id),
            ]
        ) == 0
        inspected = json.loads(capsys.readouterr().out)
        assert inspected == evidence.to_canonical_dict()
