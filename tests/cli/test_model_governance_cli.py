from __future__ import annotations

import json
import os

from market_regime_alpha.cli.model_governance import build_parser, main
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory as postgres_factory,
)
from tests.persistence.postgres.test_model_runtime_governance import (
    _governed_model,
)
from tests.platform.test_platform_kernel import _model_definition


def _authority(factory: PostgresConnectionFactory) -> list[str]:
    return [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--database-schema",
        factory.application_schema,
    ]


def test_cli_exposes_access_governance_without_a_second_cli() -> None:
    for operation in (
        "access-bootstrap-admin",
        "access-create-principal",
        "access-change-role",
        "access-set-principal-status",
        "access-authorize",
        "access-request-approval",
        "access-decide-approval",
        "access-audit",
    ):
        args = build_parser().parse_args(
            [
                "--database-url",
                "postgresql://authority",
                operation,
                "--input",
                "access.json",
            ]
        )
        assert args.operation == operation


def test_cli_bootstraps_engineering_access_governance(
    postgres_factory: PostgresConnectionFactory,
    tmp_path,
    capsys,
) -> None:
    payload_path = tmp_path / "bootstrap-access.json"
    payload_path.write_text(
        json.dumps(
            {
                "external_subject": "local:cli-admin",
                "display_name": "CLI Admin",
                "reason": "test bootstrap",
                "occurred_at": "2026-08-11T01:00:00+00:00",
                "idempotency_key": "cli-access-bootstrap",
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            *_authority(postgres_factory),
            "access-bootstrap-admin",
            "--input",
            str(payload_path),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["external_subject"] == "local:cli-admin"
    assert "PRODUCTION_ADMISSION_PERMISSION_ABSENT" in output["limitations"]


def test_cli_lists_and_inspects_postgres_model_authority(
    postgres_factory: PostgresConnectionFactory,
    capsys,
) -> None:
    governance = PostgresModelGovernanceRepository(postgres_factory)
    definition = _model_definition()
    PersistentModelRegistry(governance).register(
        definition,
        idempotency_key="cli-register-model",
    )

    assert main([*_authority(postgres_factory), "list-models"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["models"][0]["model_id"] == str(definition.model_id)
    assert listed["models"][0]["lifecycle_status"] == "DRAFT"

    assert main(
        [
            *_authority(postgres_factory),
            "inspect-model",
            "--model-id",
            str(definition.model_id),
        ]
    ) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["registry_version"] == 0
    assert inspected["governance_actions"][0]["action_type"] == "MODEL_REGISTER"


def test_cli_inspects_policy_and_qualification_evidence(
    postgres_factory: PostgresConnectionFactory,
    capsys,
) -> None:
    governance = PostgresModelGovernanceRepository(postgres_factory)
    definition, _, policy, _ = _governed_model(governance)
    model = governance.inspect_model(definition.model_id)
    evidence_id = model["qualification_evidence"][0]["evidence_id"]

    assert main(
        [
            *_authority(postgres_factory),
            "inspect-policy",
            "--policy-id",
            str(policy.policy_id),
        ]
    ) == 0
    inspected_policy = json.loads(capsys.readouterr().out)
    assert inspected_policy["policy"]["policy_id"] == str(policy.policy_id)
    assert inspected_policy["qualification_decisions"]

    assert main(
        [
            *_authority(postgres_factory),
            "inspect-evidence",
            "--evidence-id",
            evidence_id,
        ]
    ) == 0
    inspected_evidence = json.loads(capsys.readouterr().out)
    assert inspected_evidence["evidence"]["evidence_id"] == evidence_id
