from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
import json
from uuid import UUID, uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.candidate_uow import (
    PostgresCandidateUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate import (
    PostgresCandidateRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate_artifacts import (
    PostgresCandidateArtifactRepository,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeStateConflictError,
)
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    CandidatePopulationCell,
    CandidatePopulationRow,
    DesirabilityDirection,
    build_candidate_set,
)
from tests.refoundation.research_qualification import (
    test_research_postgres as _research_postgres,
)


_context = _research_postgres._context
_feature = _research_postgres._feature


@pytest.fixture
def candidate_dataset_stack(target_database_url, tmp_path, request):
    return _research_postgres.dataset_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


@dataclass(frozen=True, slots=True)
class _SeededDataset:
    dataset_id: UUID
    dataset_content_sha256: str
    universe_revision_id: UUID
    population: tuple[tuple[UUID, UUID], ...]


def _candidate_binding(artifact: object) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
    )


def _policy(stack, *, feature) -> CandidatePolicy:
    code = stack.artifacts.publish(
        b"candidate-ranking-policy-v1\n",
        media_type="text/plain",
        context=_context("candidate-policy-code", "REGISTER_CANDIDATE_POLICY_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"requested_top_k":1}\n',
        media_type="application/json",
        context=_context("candidate-policy-config", "REGISTER_CANDIDATE_POLICY_CONFIG"),
    )
    policy_id = uuid4()
    return CandidatePolicy(
        candidate_policy_id=policy_id,
        policy_code="transparent_candidate_rank",
        version=1,
        code_artifact=_candidate_binding(code),
        config_artifact=_candidate_binding(config),
        requested_top_k=1,
        components=(
            CandidatePolicyComponent(
                candidate_policy_component_id=uuid4(),
                candidate_policy_id=policy_id,
                component_code="mean_turnover",
                ordinal=1,
                feature_definition_id=feature.feature_definition_id,
                feature_content_sha256=feature.content_sha256,
                feature_value_type=CandidateFeatureValueType.DECIMAL,
                direction=DesirabilityDirection.HIGHER_IS_BETTER,
                declared_weight=Decimal(
                    "1.23456789012345678901234567890123456789"
                ),
            ),
        ),
    )


def _seed_two_row_dataset(stack, *, feature) -> _SeededDataset:
    manifest = stack.artifacts.publish(
        b'{"schema":"candidate-persistence-dataset"}\n',
        media_type="application/json",
        context=_context("candidate-dataset-manifest", "REGISTER_DATASET_MANIFEST"),
    )
    code = stack.artifacts.publish(
        b"candidate-persistence-dataset-builder\n",
        media_type="text/plain",
        context=_context("candidate-dataset-code", "REGISTER_DATASET_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"population":"INCLUDED_AND_ELIGIBLE"}\n',
        media_type="application/json",
        context=_context("candidate-dataset-config", "REGISTER_DATASET_CONFIG"),
    )
    second_instrument_id = uuid4()
    second_membership_revision_id = uuid4()
    universe_id = uuid4()
    universe_revision_id = uuid4()
    member_ids = (uuid4(), uuid4())
    assessment_ids = (uuid4(), uuid4())
    population_source_ids = (uuid4(), uuid4())
    feature_source_id = uuid4()
    dataset_id = uuid4()
    dataset_content_sha256 = "d" * 64

    with stack.pool.connection() as connection:
        instrument = connection.execute(
            """
            SELECT exchange, instrument_type, currency, source_capture_id,
                   recorded_at, known_at, decision_visible_at
            FROM mra.instrument
            WHERE instrument_id = %s
            """,
            (stack.instrument_id.value,),
        ).fetchone()
        assert instrument is not None
        connection.execute(
            """
            INSERT INTO mra.instrument (
                instrument_id, canonical_code, exchange, instrument_type,
                currency, source_capture_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, '600099.XSHG', %s, %s, %s, %s, %s, %s, %s)
            """,
            (second_instrument_id, *instrument),
        )

        member_lineage = connection.execute(
            """
            SELECT classification_id, classification_membership_revision_id,
                   market_capture_id, market_decision_visible_at
            FROM mra.universe_member
            WHERE universe_member_id = %s
            """,
            (stack.universe_member_id,),
        ).fetchone()
        assert member_lineage is not None
        membership = connection.execute(
            """
            SELECT source_capture_id, membership_status, effective_from,
                   effective_to, recorded_at, known_at, decision_visible_at
            FROM mra.classification_membership_revision
            WHERE membership_revision_id = %s
            """,
            (member_lineage[1],),
        ).fetchone()
        assert membership is not None
        connection.execute(
            """
            INSERT INTO mra.classification_membership_revision (
                membership_revision_id, classification_id, instrument_id,
                source_capture_id, membership_status, effective_from,
                effective_to, revision, supersedes_membership_revision_id,
                recorded_at, known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NULL, %s, %s, %s)
            """,
            (
                second_membership_revision_id,
                member_lineage[0],
                second_instrument_id,
                *membership,
            ),
        )

        revision = connection.execute(
            """
            SELECT scope_artifact_id, scope_content_sha256, scope_size_bytes,
                   market_provider_product_id, classification_scheme,
                   classification_code
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """,
            (stack.universe_revision_id,),
        ).fetchone()
        assert revision is not None
        connection.execute(
            """
            INSERT INTO mra.universe (universe_id, universe_code, purpose)
            VALUES (%s, 'candidate_persistence_scope', 'Candidate persistence test')
            """,
            (universe_id,),
        )
        connection.execute(
            """
            INSERT INTO mra.universe_revision (
                universe_revision_id, universe_id, revision, decision_time,
                scope_artifact_id, scope_content_sha256, scope_size_bytes,
                market_provider_product_id, classification_scheme,
                classification_code, total_count, included_count,
                excluded_count, unknown_count
            )
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 2, 2, 0, 0)
            """,
            (universe_revision_id, universe_id, stack.decision_time.value, *revision),
        )
        for member_id, instrument_id, membership_revision_id, lineage_hash in (
            (
                member_ids[0],
                stack.instrument_id.value,
                member_lineage[1],
                "1" * 64,
            ),
            (
                member_ids[1],
                second_instrument_id,
                second_membership_revision_id,
                "2" * 64,
            ),
        ):
            connection.execute(
                """
                INSERT INTO mra.universe_member (
                    universe_member_id, universe_revision_id, instrument_id,
                    membership_status, evidence_status,
                    observed_membership_status, classification_id,
                    classification_membership_revision_id, source_gap_id,
                    market_capture_id, market_decision_visible_at,
                    reason_code, lineage_hash
                )
                VALUES (
                    %s, %s, %s, 'INCLUDED', 'AVAILABLE', 'MEMBER',
                    %s, %s, NULL, %s, %s, 'CLASSIFICATION_MEMBER', %s
                )
                """,
                (
                    member_id,
                    universe_revision_id,
                    instrument_id,
                    member_lineage[0],
                    membership_revision_id,
                    member_lineage[2],
                    member_lineage[3],
                    lineage_hash,
                ),
            )
        rule_count = connection.execute(
            """
            SELECT rule_count
            FROM mra.eligibility_policy
            WHERE eligibility_policy_id = %s
            """,
            (stack.eligibility_policy_id,),
        ).fetchone()
        assert rule_count is not None
        for assessment_id, member_id, instrument_id in zip(
            assessment_ids,
            member_ids,
            (stack.instrument_id.value, second_instrument_id),
            strict=True,
        ):
            connection.execute(
                """
                INSERT INTO mra.eligibility_assessment (
                    eligibility_assessment_id, universe_revision_id,
                    universe_member_id, eligibility_policy_id, instrument_id,
                    decision_time, result, rule_count, pass_count,
                    fail_count, unknown_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'ELIGIBLE', %s, %s, 0, 0)
                """,
                (
                    assessment_id,
                    universe_revision_id,
                    member_id,
                    stack.eligibility_policy_id,
                    instrument_id,
                    stack.decision_time.value,
                    int(rule_count[0]),
                    int(rule_count[0]),
                ),
            )

        connection.execute(
            """
            INSERT INTO mra.dataset (
                dataset_id, dataset_code, version, dataset_kind,
                decision_time, universe_revision_id, eligibility_policy_id,
                manifest_artifact_id, manifest_content_sha256,
                manifest_size_bytes, code_artifact_id, code_content_sha256,
                code_size_bytes, config_artifact_id, config_content_sha256,
                config_size_bytes, content_sha256, row_count, feature_count,
                source_count, cell_count, available_cell_count,
                missing_cell_count, unknown_cell_count, stale_cell_count,
                conflict_cell_count
            )
            VALUES (
                %s, 'candidate_persistence_dataset', 1, 'DECISION_INPUT',
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, 2, 1, 3, 2, 2, 0, 0, 0, 0
            )
            """,
            (
                dataset_id,
                stack.decision_time.value,
                universe_revision_id,
                stack.eligibility_policy_id,
                manifest.artifact_id,
                manifest.content_sha256,
                manifest.size_bytes,
                code.artifact_id,
                code.content_sha256,
                code.size_bytes,
                config.artifact_id,
                config.content_sha256,
                config.size_bytes,
                dataset_content_sha256,
            ),
        )
        connection.execute(
            """
            INSERT INTO mra.dataset_source (
                dataset_source_id, dataset_id, source_role,
                feature_definition_id
            )
            VALUES (%s, %s, 'FEATURE_DEFINITION', %s)
            """,
            (feature_source_id, dataset_id, feature.feature_definition_id),
        )
        for source_id, member_id, assessment_id, instrument_id in zip(
            population_source_ids,
            member_ids,
            assessment_ids,
            (stack.instrument_id.value, second_instrument_id),
            strict=True,
        ):
            connection.execute(
                """
                INSERT INTO mra.dataset_source (
                    dataset_source_id, dataset_id, source_role, instrument_id,
                    universe_revision_id, universe_member_id,
                    eligibility_policy_id, eligibility_assessment_id,
                    decision_time, membership_status, eligibility_result
                )
                VALUES (
                    %s, %s, 'POPULATION', %s, %s, %s, %s, %s, %s,
                    'INCLUDED', 'ELIGIBLE'
                )
                """,
                (
                    source_id,
                    dataset_id,
                    instrument_id,
                    universe_revision_id,
                    member_id,
                    stack.eligibility_policy_id,
                    assessment_id,
                    stack.decision_time.value,
                ),
            )
        connection.commit()

    return _SeededDataset(
        dataset_id=dataset_id,
        dataset_content_sha256=dataset_content_sha256,
        universe_revision_id=universe_revision_id,
        population=tuple(
            zip(
                population_source_ids,
                (stack.instrument_id.value, second_instrument_id),
                strict=True,
            )
        ),
    )


def _seed_empty_dataset(stack, *, feature) -> _SeededDataset:
    code = stack.artifacts.publish(
        b"candidate-persistence-empty-dataset-builder\n",
        media_type="text/plain",
        context=_context("candidate-empty-code", "REGISTER_DATASET_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"population":"EMPTY"}\n',
        media_type="application/json",
        context=_context("candidate-empty-config", "REGISTER_DATASET_CONFIG"),
    )
    universe_id = uuid4()
    universe_revision_id = uuid4()
    dataset_id = uuid4()
    feature_source_id = uuid4()
    manifest_payload = {
        "schema": "mra-decision-input-dataset-v1",
        "dataset_id": str(dataset_id),
        "dataset_code": "candidate_empty_dataset",
        "dataset_version": 1,
        "decision_time": stack.decision_time.value.isoformat(),
        "universe_revision_id": str(universe_revision_id),
        "eligibility_policy_id": str(stack.eligibility_policy_id),
        "feature_definition_ids": [str(feature.feature_definition_id)],
        "code_artifact": {
            "artifact_id": str(code.artifact_id),
            "content_sha256": code.content_sha256,
            "size_bytes": code.size_bytes,
        },
        "config_artifact": {
            "artifact_id": str(config.artifact_id),
            "content_sha256": config.content_sha256,
            "size_bytes": config.size_bytes,
        },
        "sources": [
            {
                "dataset_source_id": str(feature_source_id),
                "role": "FEATURE_DEFINITION",
                "feature_definition_id": str(feature.feature_definition_id),
            }
        ],
        "rows": [],
    }
    manifest = stack.artifacts.publish(
        json.dumps(
            manifest_payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode(),
        media_type="application/json",
        context=_context("candidate-empty-manifest", "REGISTER_DATASET_MANIFEST"),
    )
    dataset_definition = _research_postgres.DecisionInputDatasetDefinition(
        dataset_id=dataset_id,
        dataset_code="candidate_empty_dataset",
        version=1,
        decision_time=stack.decision_time,
        universe_revision_id=universe_revision_id,
        eligibility_policy_id=stack.eligibility_policy_id,
        feature_definition_ids=(feature.feature_definition_id,),
        manifest_artifact=_research_postgres._binding(manifest),
        code_artifact=_research_postgres._binding(code),
        config_artifact=_research_postgres._binding(config),
    )
    dataset_content_sha256 = str(dataset_definition.content_sha256)
    with stack.pool.connection() as connection:
        revision = connection.execute(
            """
            SELECT scope_artifact_id, scope_content_sha256, scope_size_bytes,
                   market_provider_product_id, classification_scheme,
                   classification_code
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """,
            (stack.universe_revision_id,),
        ).fetchone()
        assert revision is not None
        connection.execute(
            """
            INSERT INTO mra.universe (universe_id, universe_code, purpose)
            VALUES (%s, 'candidate_empty_scope', 'Empty Candidate persistence test')
            """,
            (universe_id,),
        )
        connection.execute(
            """
            INSERT INTO mra.universe_revision (
                universe_revision_id, universe_id, revision, decision_time,
                scope_artifact_id, scope_content_sha256, scope_size_bytes,
                market_provider_product_id, classification_scheme,
                classification_code, total_count, included_count,
                excluded_count, unknown_count
            )
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0)
            """,
            (universe_revision_id, universe_id, stack.decision_time.value, *revision),
        )
        connection.execute(
            """
            INSERT INTO mra.dataset (
                dataset_id, dataset_code, version, dataset_kind,
                decision_time, universe_revision_id, eligibility_policy_id,
                manifest_artifact_id, manifest_content_sha256,
                manifest_size_bytes, code_artifact_id, code_content_sha256,
                code_size_bytes, config_artifact_id, config_content_sha256,
                config_size_bytes, content_sha256, row_count, feature_count,
                source_count, cell_count, available_cell_count,
                missing_cell_count, unknown_cell_count, stale_cell_count,
                conflict_cell_count
            )
            VALUES (
                %s, 'candidate_empty_dataset', 1, 'DECISION_INPUT',
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, 0, 1, 1, 0, 0, 0, 0, 0, 0
            )
            """,
            (
                dataset_id,
                stack.decision_time.value,
                universe_revision_id,
                stack.eligibility_policy_id,
                manifest.artifact_id,
                manifest.content_sha256,
                manifest.size_bytes,
                code.artifact_id,
                code.content_sha256,
                code.size_bytes,
                config.artifact_id,
                config.content_sha256,
                config.size_bytes,
                dataset_content_sha256,
            ),
        )
        connection.execute(
            """
            INSERT INTO mra.dataset_source (
                dataset_source_id, dataset_id, source_role,
                feature_definition_id
            )
            VALUES (%s, %s, 'FEATURE_DEFINITION', %s)
            """,
            (feature_source_id, dataset_id, feature.feature_definition_id),
        )
        connection.commit()
    return _SeededDataset(
        dataset_id=dataset_id,
        dataset_content_sha256=dataset_content_sha256,
        universe_revision_id=universe_revision_id,
        population=(),
    )


def test_policy_round_trips_exact_feature_artifact_and_decimal_bindings(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-persistence-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-persistence-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)

    with stack.pool.connection() as connection:
        repository = PostgresCandidateRepository(connection)
        repository.insert_policy(policy)
        assert repository.policy(policy.candidate_policy_id, lock=True) == policy
        connection.commit()

    with stack.pool.connection(read_only=True) as connection:
        persisted = PostgresCandidateRepository(connection).policy(
            policy.candidate_policy_id,
            lock=False,
        )

    assert persisted == policy
    assert persisted.components[0].declared_weight == Decimal(
        "1.23456789012345678901234567890123456789"
    )


def test_candidate_artifact_repository_requires_exact_foundation_identity(
    candidate_dataset_stack,
) -> None:
    artifact = candidate_dataset_stack.artifacts.publish(
        b"candidate-policy-code-exact-identity\n",
        media_type="text/plain",
        context=_context("candidate-artifact-exact", "REGISTER_CANDIDATE_POLICY_CODE"),
    )
    binding = _candidate_binding(artifact)

    with candidate_dataset_stack.pool.connection() as connection:
        repository = PostgresCandidateArtifactRepository(connection)
        record = repository.require_exact(binding, lock=True)
        with pytest.raises(ArtifactIntegrityError, match="identity"):
            repository.require_exact(
                CandidateArtifactBinding(
                    artifact_id=binding.artifact_id,
                    content_sha256="f" * 64,
                    size_bytes=binding.size_bytes,
                ),
                lock=False,
            )

    assert record.artifact_id == binding.artifact_id
    assert record.content_sha256 == str(binding.content_sha256)
    assert record.size_bytes == binding.size_bytes


def test_candidate_set_bulk_write_preserves_equal_rank_numeric_matrix_and_funnel(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-set-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-set-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)
    seeded = _seed_two_row_dataset(stack, feature=feature)
    population = CandidateDatasetPopulation(
        dataset_id=seeded.dataset_id,
        dataset_content_sha256=seeded.dataset_content_sha256,
        decision_time=stack.decision_time,
        universe_revision_id=seeded.universe_revision_id,
        eligibility_policy_id=stack.eligibility_policy_id,
        dependency_sha256="e" * 64,
        rows=tuple(
            CandidatePopulationRow(
                instrument_id=instrument_id,
                dataset_population_source_id=source_id,
                cells=(
                    CandidatePopulationCell(
                        feature_definition_id=feature.feature_definition_id,
                        status=CandidateCellStatus.AVAILABLE,
                        value=Decimal("1234567890.123456789012"),
                        reason_code="OBSERVED",
                        cell_source_lineage_hash=(
                            "a" * 64 if ordinal == 0 else "b" * 64
                        ),
                    ),
                ),
            )
            for ordinal, (source_id, instrument_id) in enumerate(seeded.population)
        ),
    )
    plan = build_candidate_set(policy=policy, dataset=population)

    drifted_scores = tuple(
        replace(score, contribution=Decimal("0.4"))
        if ordinal == 0
        else score
        for ordinal, score in enumerate(plan.score_components)
    )
    with stack.pool.connection() as drifted_connection:
        drifted_repository = PostgresCandidateRepository(drifted_connection)
        drifted_repository.insert_policy(policy)
        drifted_repository.insert_candidate_set(
            replace(plan, score_components=drifted_scores)
        )
        persisted_drift = drifted_repository.persisted_candidate_set(
            candidate_policy_id=policy.candidate_policy_id,
            dataset_id=seeded.dataset_id,
            lock=True,
        )
        assert persisted_drift == replace(
            plan,
            score_components=drifted_scores,
        )

    boundary_drift = replace(
        plan,
        candidate_set=replace(
            plan.candidate_set,
            boundary_score=Decimal("0.4"),
        ),
    )
    with stack.pool.connection() as boundary_connection:
        boundary_repository = PostgresCandidateRepository(boundary_connection)
        boundary_repository.insert_policy(policy)
        boundary_repository.insert_candidate_set(boundary_drift)
        boundary_reconciliation = boundary_repository.reconciliation(
            plan.candidate_set_id
        )
        assert boundary_reconciliation.ranking_reconciled is False

    with stack.pool.connection() as incomplete_connection:
        incomplete_repository = PostgresCandidateRepository(incomplete_connection)
        incomplete_repository.insert_policy(policy)
        incomplete_repository.insert_candidate_set(
            replace(plan, score_components=())
        )
        incomplete = incomplete_repository.reconciliation(plan.candidate_set_id)
        assert incomplete.component_matrix_reconciled is False
        assert incomplete.ranking_reconciled is False

    with stack.pool.connection() as connection:
        repository = PostgresCandidateRepository(connection)
        repository.insert_policy(policy)
        repository.insert_candidate_set(plan)
        persisted = repository.persisted_candidate_set(
            candidate_policy_id=policy.candidate_policy_id,
            dataset_id=seeded.dataset_id,
            lock=True,
        )
        binding = repository.candidate_set_binding(
            candidate_policy_id=policy.candidate_policy_id,
            dataset_id=seeded.dataset_id,
            lock=True,
        )
        reconciliation = repository.reconciliation(plan.candidate_set_id)
        stored_candidates = connection.execute(
            """
            SELECT composite_score, competition_rank, disposition
            FROM mra.candidate
            WHERE candidate_set_id = %s
            ORDER BY candidate_id
            """,
            (plan.candidate_set_id,),
        ).fetchall()
        stored_scores = connection.execute(
            """
            SELECT raw_decimal_value, normalized_weight, percentile,
                   contribution
            FROM mra.candidate_score_component
            WHERE candidate_set_id = %s
            ORDER BY candidate_score_component_id
            """,
            (plan.candidate_set_id,),
        ).fetchall()

        with stack.pool.connection(read_only=True) as observer:
            assert observer.execute(
                "SELECT count(*) FROM mra.candidate_set WHERE candidate_set_id = %s",
                (plan.candidate_set_id,),
            ).fetchone() == (0,)

        connection.commit()

    assert persisted == plan
    assert binding is not None
    assert binding.candidate_set_id == plan.candidate_set_id
    assert binding.candidate_policy_id == policy.candidate_policy_id
    assert binding.candidate_policy_content_sha256 == str(policy.content_sha256)
    assert binding.dataset_id == seeded.dataset_id
    assert binding.dataset_content_sha256 == seeded.dataset_content_sha256
    assert binding.dependency_sha256 == str(plan.candidate_set.dependency_sha256)
    assert binding.result_sha256 == str(plan.result_sha256)
    assert stored_candidates == [
        (Decimal("0.5"), 1, "SELECTED"),
        (Decimal("0.5"), 1, "SELECTED"),
    ]
    assert stored_scores == [
        (
            Decimal("1234567890.123456789012"),
            Decimal("1"),
            Decimal("0.5"),
            Decimal("0.5"),
        ),
        (
            Decimal("1234567890.123456789012"),
            Decimal("1"),
            Decimal("0.5"),
            Decimal("0.5"),
        ),
    ]
    assert reconciliation.population_count == 2
    assert reconciliation.selected_count == 2
    assert reconciliation.ranked_not_selected_count == 0
    assert reconciliation.unrankable_count == 0
    assert reconciliation.score_component_count == 2
    assert reconciliation.population_reconciled is True
    assert reconciliation.rankable_reconciled is True
    assert reconciliation.component_matrix_reconciled is True
    assert reconciliation.ranking_reconciled is True


def test_empty_candidate_set_persists_and_reconciles_without_child_rows(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-empty-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-empty-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)
    seeded = _seed_empty_dataset(stack, feature=feature)
    plan = build_candidate_set(
        policy=policy,
        dataset=CandidateDatasetPopulation(
            dataset_id=seeded.dataset_id,
            dataset_content_sha256=seeded.dataset_content_sha256,
            decision_time=stack.decision_time,
            universe_revision_id=seeded.universe_revision_id,
            eligibility_policy_id=stack.eligibility_policy_id,
            dependency_sha256="f" * 64,
            rows=(),
        ),
    )

    with stack.pool.connection() as connection:
        repository = PostgresCandidateRepository(connection)
        repository.insert_policy(policy)
        repository.insert_candidate_set(plan)
        persisted = repository.persisted_candidate_set(
            candidate_policy_id=policy.candidate_policy_id,
            dataset_id=seeded.dataset_id,
            lock=True,
        )
        reconciliation = repository.reconciliation(plan.candidate_set_id)
        connection.commit()

    assert persisted == plan
    assert reconciliation.population_count == 0
    assert reconciliation.selected_count == 0
    assert reconciliation.ranked_not_selected_count == 0
    assert reconciliation.unrankable_count == 0
    assert reconciliation.score_component_count == 0
    assert reconciliation.population_reconciled is True
    assert reconciliation.rankable_reconciled is True
    assert reconciliation.component_matrix_reconciled is True
    assert reconciliation.ranking_reconciled is True


def test_candidate_uow_exposes_only_candidate_dependencies_and_rolls_back_by_default(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-uow-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-uow-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)
    provider = PostgresCandidateUnitOfWorkProvider(stack.pool)

    with provider() as uow:
        uow.candidates.insert_policy(policy)
        assert uow.research_dependencies is not None
        assert uow.candidate_artifacts is not None
        assert uow.receipts is not None
        assert uow.audit is not None
        assert uow.runtime_finalization is not None

    with stack.pool.connection(read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM mra.candidate_policy WHERE candidate_policy_id = %s",
            (policy.candidate_policy_id,),
        ).fetchone()

    assert count == (0,)


def test_candidate_uow_commit_one_use_and_sql_rejection_translation(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-uow-commit-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-uow-commit-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)
    provider = PostgresCandidateUnitOfWorkProvider(stack.pool)
    committed = provider()

    with committed as uow:
        uow.candidates.insert_policy(policy)
        uow.commit()

    with stack.pool.connection(read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM mra.candidate_policy WHERE candidate_policy_id = %s",
            (policy.candidate_policy_id,),
        ).fetchone()
    assert count == (1,)

    with pytest.raises(RuntimeError, match="nested or reused"):
        with committed:
            pass
    with pytest.raises(RuntimeStateConflictError, match="Candidate"):
        with provider() as rejected:
            rejected.candidates.insert_policy(policy)
    with stack.pool.connection(read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_policy
                 WHERE candidate_policy_id = %s),
                (SELECT count(*) FROM mra.candidate_policy_component
                 WHERE candidate_policy_id = %s)
            """,
            (policy.candidate_policy_id, policy.candidate_policy_id),
        ).fetchone()
    assert counts == (1, 1)


def test_candidate_policy_artifacts_are_protected_from_foundation_gc(
    candidate_dataset_stack,
) -> None:
    stack = candidate_dataset_stack
    feature = _feature(stack.artifacts, key_prefix="candidate-gc-feature")
    stack.research.register_feature_definition(
        feature,
        _context("candidate-gc-feature", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _policy(stack, feature=feature)
    with stack.pool.connection() as connection:
        PostgresCandidateRepository(connection).insert_policy(policy)
        connection.commit()

    scan = stack.artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="candidate-artifact-scanner",
    )

    policy_hashes = {
        str(policy.code_artifact.content_sha256),
        str(policy.config_artifact.content_sha256),
    }
    assert policy_hashes <= set(scan.protected)
    assert not policy_hashes & set(scan.observed)
    assert not policy_hashes & set(scan.quarantined)
