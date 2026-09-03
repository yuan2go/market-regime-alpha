from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.research_model_uow import (
    PostgresResearchModelUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.research_models import (
    ModelCommands,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ResearchModelPlan,
)
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from tests.refoundation.outcome import test_outcome_postgres as _outcome
from tests.refoundation.research_qualification import test_research_postgres as _research


@pytest.fixture
def model_stack(target_database_url, tmp_path, request):
    return _outcome.outcome_stack.__wrapped__(target_database_url, tmp_path, request)


def test_model_family_registration_is_atomic_idempotent_and_relational(model_stack) -> None:
    stack = model_stack
    target = _outcome._register_midnight_target(stack)
    feature = _research._feature(stack.artifacts, key_prefix="wp17p-model-feature")
    stack.research.register_feature_definition(
        feature,
        _research._context("wp17p-register-model-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    plan = ResearchModelPlan(
        model_id=uuid4(),
        model_code=f"wp17p_ridge_{uuid4().hex[:8]}",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        feature_definitions=((feature.feature_definition_id, feature.content_sha256),),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="e" * 64,
    )
    commands = ModelCommands(
        PostgresResearchModelUnitOfWorkProvider(stack.pool),
        id_factory=uuid4,
    )
    context = _research._context("wp17p-register-model", "REGISTER_RESEARCH_MODEL")

    first = commands.register_model(plan, context)
    replay = commands.register_model(plan, context)

    assert first.replayed is False
    assert replay.replayed is True
    assert first.result_hash == replay.result_hash
    with psycopg.connect(stack.database_url) as connection:
        root = connection.execute(
            """
            SELECT feature_count, feature_roster_sha256, content_sha256
            FROM mra.model WHERE model_id = %s
            """,
            (plan.model_id,),
        ).fetchone()
        members = connection.execute(
            """
            SELECT ordinal, feature_definition_id, feature_definition_sha256,
                   feature_value_type
            FROM mra.model_feature_definition WHERE model_id = %s
            ORDER BY ordinal
            """,
            (plan.model_id,),
        ).fetchall()
    assert root == (1, str(plan.feature_roster_sha256), str(plan.content_sha256))
    assert members == [
        (1, feature.feature_definition_id, str(feature.content_sha256), "DECIMAL")
    ]

    with pytest.raises(IdempotencyKeyReusedError):
        commands.register_model(
            replace(plan, provenance_sha256="f" * 64),
            context,
        )
