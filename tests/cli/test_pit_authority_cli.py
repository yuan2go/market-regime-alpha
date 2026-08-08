from __future__ import annotations

import json
import os
from pathlib import Path

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_source_manifest,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data.pit_authority import PITArtifactKind, PITArtifactReference
from market_regime_alpha.data.source_manifest import SourceManifest
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


def test_cli_resolves_canonical_artifact_and_persists_reader_receipt(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    capsys,
) -> None:
    manifest = SourceManifest(
        provider_profile_id="cli-engineering-fixture-provider",
        decision_time=DecisionTime(NOW),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=ArtifactId("cli-raw-source-a"),
                provider_id=ProviderId("cli-engineering-fixture-provider"),
                retrieved_at=RetrievedAt(NOW),
                content_hash="sha256:" + "a" * 64,
                locator="fixture://cli-raw-source-a",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=("ENGINEERING_FIXTURE",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    root = tmp_path / "source-manifests"
    publish_controlled_source_manifest(root=root, artifact=manifest)
    command = tmp_path / "resolve.json"
    reference = PITArtifactReference(
        PITArtifactKind.SOURCE_MANIFEST.value,
        manifest.source_manifest_id,
        manifest.content_hash,
    )
    command.write_text(
        json.dumps(
            {
                "reference": reference.to_canonical_dict(),
                "actor": "cli-artifact-authority-operator",
                "reason": "register canonical strict Reader receipt",
                "idempotency_key": "cli-resolve-source-manifest",
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            *_authority(postgres_factory),
            "--pit-source-manifest-root",
            str(root),
            "resolve-artifact",
            "--input",
            str(command),
        ]
    ) == 0
    resolved = json.loads(capsys.readouterr().out)

    assert resolved["reference"] == reference.to_canonical_dict()
    assert resolved["reader_contract"] == "controlled-source-manifest-package-v1"
