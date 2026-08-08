from __future__ import annotations

import json
import os

from market_regime_alpha.cli.model_governance import main
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
