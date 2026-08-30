from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID, uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.research_uow import (
    PostgresResearchUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.target_uow import (
    PostgresTargetUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.research_qualification.application import (
    ResearchQualificationApplication,
)
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
)
from tests.refoundation.research_qualification.test_target_domain import valid_target


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="target-registration-test",
        reason_code="REGISTER_TARGET_DEFINITION",
    )


def _binding(record) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=record.artifact_id,
        content_sha256=record.content_sha256,
        size_bytes=record.size_bytes,
    )


@pytest.fixture
def target_stack(target_database_url: str, tmp_path, request):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    request.addfinalizer(pool.close)
    store = LocalArtifactStore(tmp_path / "target-definition-artifacts")
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    application = ResearchQualificationApplication(
        store,
        PostgresResearchUnitOfWorkProvider(pool),
        PostgresTargetUnitOfWorkProvider(pool),
    )
    code = artifacts.publish(
        b"def simple_return(reference, observation): return observation / reference - 1\n",
        media_type="text/plain",
        context=_context("target-code"),
    )
    config = artifacts.publish(
        b'{"reference":"14:55","outcome":"T+1 10:30"}\n',
        media_type="application/json",
        context=_context("target-config"),
    )
    definition = valid_target()
    algorithm = replace(
        definition.algorithm,
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    definition = replace(
        definition,
        algorithm=algorithm,
        metrics=tuple(
            replace(metric, algorithm=algorithm) for metric in definition.metrics
        ),
    )
    return application, definition, pool, target_database_url


def test_register_target_definition_closes_complete_relational_authority_and_exact_replay(
    target_stack,
) -> None:
    application, definition, _, database_url = target_stack
    first = application.register_target_definition(
        definition,
        _context("register-target-v1"),
    )
    replay = application.register_target_definition(
        definition,
        _context("register-target-v1"),
    )
    assert replay == replace(first, replayed=True)
    assert first.target_definition_id == definition.target_definition_id
    assert first.definition_sha256 == str(definition.content_sha256)
    assert (
        first.checkpoint_count,
        first.metric_count,
        first.dependency_count,
    ) == (2, 1, 2)

    with psycopg.connect(database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.target_definition),
              (SELECT count(*) FROM mra.target_checkpoint),
              (SELECT count(*) FROM mra.target_metric_definition),
              (SELECT count(*) FROM mra.target_metric_dependency),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'REGISTER_TARGET_DEFINITION'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'REGISTER_TARGET_DEFINITION')
            """
        ).fetchone()
    assert counts == (1, 2, 1, 2, 1, 1)


def test_register_target_definition_rejects_changed_exact_identity_and_keeps_original(
    target_stack,
) -> None:
    application, definition, _, database_url = target_stack
    original = application.register_target_definition(
        definition,
        _context("register-target-conflict"),
    )
    changed = replace(
        definition,
        checkpoints=(
            definition.checkpoints[0],
            replace(
                definition.checkpoints[1],
                local_time=definition.checkpoints[1].local_time.replace(minute=35),
            ),
        ),
    )
    with pytest.raises(IdempotencyKeyReusedError):
        application.register_target_definition(
            changed,
            _context("register-target-conflict"),
        )
    replay = application.register_target_definition(
        definition,
        _context("register-target-conflict"),
    )
    assert replay.target_definition_id == original.target_definition_id
    assert replay.definition_sha256 == original.definition_sha256
    assert replay.replayed is True
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.target_definition"
        ).fetchone() == (1,)


def test_closed_target_children_and_root_are_immutable(target_stack) -> None:
    application, definition, _, database_url = target_stack
    application.register_target_definition(definition, _context("register-immutable"))
    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE mra.target_definition SET target_code = target_code"
            )
        connection.rollback()
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE mra.target_checkpoint SET checkpoint_code = checkpoint_code"
            )
        connection.rollback()
        row = connection.execute(
            """
            SELECT target_checkpoint_id, target_definition_id,
                   checkpoint_code, ordinal, checkpoint_role,
                   session_offset, timing_rule, local_time, timezone_name,
                   timeframe, price_basis, value_field, reference_rule,
                   availability_rule, finality_rule, content_sha256
            FROM mra.target_checkpoint
            WHERE target_definition_id = %s
            ORDER BY ordinal
            LIMIT 1
            """,
            (definition.target_definition_id,),
        ).fetchone()
        assert row is not None
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                INSERT INTO mra.target_checkpoint (
                    target_checkpoint_id, target_definition_id,
                    checkpoint_code, ordinal, checkpoint_role,
                    session_offset, timing_rule, local_time, timezone_name,
                    timeframe, price_basis, value_field, reference_rule,
                    availability_rule, finality_rule, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (uuid4(), *row[1:]),
            )


def test_concurrent_identical_target_registration_has_one_canonical_writer(
    target_stack,
) -> None:
    application, definition, _, database_url = target_stack

    def register():
        return application.register_target_definition(
            definition,
            _context("register-target-concurrent"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _: register(), range(2)))
    assert {item.target_definition_id for item in outcomes} == {
        definition.target_definition_id
    }
    assert sorted(item.replayed for item in outcomes) == [False, True]
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.target_definition"
        ).fetchone() == (1,)


def test_target_supersession_appends_complete_next_version_without_mutating_history(
    target_stack,
) -> None:
    application, first, _, database_url = target_stack
    application.register_target_definition(
        first,
        _context("register-target-supersession-v1"),
    )
    second_id = UUID("00000000-0000-4000-8000-000000009101")
    checkpoint_ids = {
        item.target_checkpoint_id: UUID(
            f"00000000-0000-4000-8000-0000000091{index:02d}"
        )
        for index, item in enumerate(first.checkpoints, start=2)
    }
    metric_ids = {
        item.target_metric_definition_id: UUID(
            f"00000000-0000-4000-8000-0000000092{index:02d}"
        )
        for index, item in enumerate(first.metrics, start=1)
    }
    checkpoints = tuple(
        replace(
            item,
            target_checkpoint_id=checkpoint_ids[item.target_checkpoint_id],
            target_definition_id=second_id,
        )
        for item in first.checkpoints
    )
    metrics = tuple(
        replace(
            item,
            target_metric_definition_id=metric_ids[
                item.target_metric_definition_id
            ],
            target_definition_id=second_id,
        )
        for item in first.metrics
    )
    dependencies = tuple(
        replace(
            item,
            target_metric_dependency_id=UUID(
                f"00000000-0000-4000-8000-0000000093{index:02d}"
            ),
            target_definition_id=second_id,
            target_metric_definition_id=metric_ids[
                item.target_metric_definition_id
            ],
            target_checkpoint_id=checkpoint_ids[item.target_checkpoint_id],
        )
        for index, item in enumerate(first.dependencies, start=1)
    )
    second = replace(
        first,
        target_definition_id=second_id,
        version=2,
        supersedes_target_definition_id=first.target_definition_id,
        checkpoints=checkpoints,
        metrics=metrics,
        dependencies=dependencies,
    )

    application.register_target_definition(
        second,
        _context("register-target-supersession-v2"),
    )

    with psycopg.connect(database_url) as connection:
        roots = connection.execute(
            """
            SELECT target_definition_id, version,
                   supersedes_target_definition_id, content_sha256
            FROM mra.target_definition
            WHERE target_code = %s
            ORDER BY version
            """,
            (first.target_code,),
        ).fetchall()
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.target_checkpoint),
              (SELECT count(*) FROM mra.target_metric_definition),
              (SELECT count(*) FROM mra.target_metric_dependency)
            """
        ).fetchone()
    assert roots == [
        (
            first.target_definition_id,
            1,
            None,
            str(first.content_sha256),
        ),
        (
            second.target_definition_id,
            2,
            first.target_definition_id,
            str(second.content_sha256),
        ),
    ]
    assert counts == (4, 2, 4)


def test_missing_artifact_rolls_back_all_target_rows(target_stack) -> None:
    application, definition, _, database_url = target_stack
    missing = replace(
        definition.algorithm.code_artifact,
        artifact_id=uuid4(),
    )
    algorithm = replace(definition.algorithm, code_artifact=missing)
    invalid = replace(
        definition,
        algorithm=algorithm,
        metrics=tuple(
            replace(metric, algorithm=algorithm) for metric in definition.metrics
        ),
    )
    with pytest.raises(RuntimeNotFoundError):
        application.register_target_definition(
            invalid,
            _context("register-target-missing-artifact"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.target_definition),
              (SELECT count(*) FROM mra.target_checkpoint),
              (SELECT count(*) FROM mra.target_metric_definition),
              (SELECT count(*) FROM mra.target_metric_dependency),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'REGISTER_TARGET_DEFINITION'
                 AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'RESEARCH_COMMAND_FAILED')
            """
        ).fetchone() == (0, 0, 0, 0, 1, 1)
