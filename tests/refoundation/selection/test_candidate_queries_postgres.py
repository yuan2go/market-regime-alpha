from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import json
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.queries.candidate import (
    PostgresCandidateQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate import (
    PostgresCandidateRepository,
)
from market_regime_alpha.research_qualification.domain import (
    FeatureCellStatus,
    FeatureSourceRequirement,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.ports.candidate_queries import (
    CandidateDossierComponent,
    CandidateDossierRecord,
    CandidateFunnelComponentDiagnostic,
    CandidateFunnelRecord,
)
from tests.refoundation.research_qualification.test_research_postgres import (
    _binding,
    _context,
    _dataset_input,
    _feature,
)


pytest_plugins = (
    "tests.refoundation.research_qualification.test_research_postgres",
)


@dataclass(frozen=True, slots=True)
class _CandidateSeed:
    candidate_set_id: UUID
    candidate_id: UUID
    dataset_id: UUID
    dataset_content_sha256: str
    manifest_artifact_id: UUID
    manifest_content_sha256: str
    manifest_size_bytes: int
    population_source_id: UUID
    feature_source_id: UUID
    lineage_hash: str


def _artifact_binding(artifact: Any) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
    )


def _register_policy(stack: Any, *, feature: Any) -> CandidatePolicy:
    code = stack.artifacts.publish(
        b"candidate-query-policy-v1\n",
        media_type="text/plain",
        context=_context("candidate-query-policy-code", "REGISTER_CANDIDATE_POLICY_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"requested_top_k":1}\n',
        media_type="application/json",
        context=_context(
            "candidate-query-policy-config",
            "REGISTER_CANDIDATE_POLICY_CONFIG",
        ),
    )
    policy_id = uuid4()
    policy = CandidatePolicy(
        candidate_policy_id=policy_id,
        policy_code="candidate_query_policy",
        version=1,
        code_artifact=_artifact_binding(code),
        config_artifact=_artifact_binding(config),
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
                declared_weight=Decimal("3.5"),
            ),
        ),
    )
    with stack.pool.connection() as connection:
        PostgresCandidateRepository(connection).insert_policy(policy)
        connection.commit()
    return policy


def _register_dataset(
    stack: Any,
    *,
    feature: Any,
    key_prefix: str,
    status: FeatureCellStatus,
) -> tuple[Any, dict[str, object]]:
    definition, payload = _dataset_input(
        stack,
        feature,
        key_prefix=key_prefix,
        status=status,
    )
    if status is FeatureCellStatus.AVAILABLE:
        rows = cast(list[dict[str, object]], payload["rows"])
        cells = cast(list[dict[str, object]], rows[0]["cells"])
        cells[0]["value"] = "12.5"
        manifest_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        manifest = stack.artifacts.publish(
            manifest_bytes,
            media_type="application/json",
            context=_context(
                f"{key_prefix}-numeric-manifest",
                "REGISTER_DATASET_MANIFEST",
            ),
        )
        definition = replace(definition, manifest_artifact=_binding(manifest))
    stack.research.register_dataset(
        definition,
        _context(f"{key_prefix}-register", "REGISTER_DATASET"),
    )
    return definition, payload


def _insert_candidate_authority(
    stack: Any,
    *,
    policy: CandidatePolicy,
    definition: Any,
    payload: dict[str, object],
    status: FeatureCellStatus,
    hash_character: str,
    boundary_score: Decimal = Decimal("0.5"),
) -> _CandidateSeed:
    component = policy.components[0]
    rows = cast(list[dict[str, object]], payload["rows"])
    sources = cast(list[dict[str, str]], payload["sources"])
    population_source_id = UUID(str(rows[0]["population_source_id"]))
    feature_source_id = UUID(
        next(
            item["dataset_source_id"]
            for item in sources
            if item["role"] == "FEATURE_DEFINITION"
        )
    )
    candidate_set_id = uuid4()
    candidate_id = uuid4()
    rankable = status is FeatureCellStatus.AVAILABLE
    lineage_hash = hash_character * 64
    with stack.pool.connection() as connection:
        connection.execute(
            """
            INSERT INTO mra.candidate_set (
                candidate_set_id, candidate_policy_id,
                candidate_policy_content_sha256, dataset_id,
                dataset_content_sha256, universe_revision_id,
                eligibility_policy_id, decision_time, requested_top_k,
                component_count, decimal_projection_precision,
                population_count, rankable_count, unrankable_count,
                selected_count, ranked_not_selected_count,
                score_component_count, available_component_count,
                constant_component_count, not_estimable_component_count,
                ranking_status, composite_distinct_count, boundary_score,
                boundary_rank, strictly_above_boundary_count,
                boundary_group_count, selected_overflow_count,
                boundary_has_tie, boundary_tie_expanded, dependency_sha256,
                content_sha256
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, 64,
                1, %s, %s, %s, 0, 1, 0, %s, %s, %s, %s, %s, %s,
                0, %s, 0, false, false, %s, %s
            )
            """,
            (
                candidate_set_id,
                policy.candidate_policy_id,
                str(policy.content_sha256),
                definition.dataset_id,
                str(definition.content_sha256),
                stack.universe_revision_id,
                stack.eligibility_policy_id,
                stack.decision_time.value,
                1 if rankable else 0,
                0 if rankable else 1,
                1 if rankable else 0,
                1 if rankable else 0,
                0 if rankable else 1,
                "CONSTANT" if rankable else "NOT_ESTIMABLE",
                1 if rankable else 0,
                boundary_score if rankable else None,
                1 if rankable else None,
                1 if rankable else 0,
                "d" * 64,
                hash_character * 64,
            ),
        )
        connection.execute(
            """
            INSERT INTO mra.candidate (
                candidate_id, candidate_set_id, candidate_policy_id,
                dataset_id, dataset_population_source_id,
                dataset_source_role, instrument_id, disposition,
                composite_score, competition_rank, reason_code
            )
            VALUES (%s, %s, %s, %s, %s, 'POPULATION', %s, %s, %s, %s, %s)
            """,
            (
                candidate_id,
                candidate_set_id,
                policy.candidate_policy_id,
                definition.dataset_id,
                population_source_id,
                stack.instrument_id.value,
                "SELECTED" if rankable else "UNRANKABLE",
                Decimal("0.5") if rankable else None,
                1 if rankable else None,
                (
                    "ALL_RANKABLE_SELECTED"
                    if rankable
                    else "STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE"
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO mra.candidate_score_component (
                candidate_score_component_id, candidate_id,
                candidate_set_id, candidate_policy_id, dataset_id,
                instrument_id, candidate_disposition,
                candidate_policy_component_id, feature_definition_id,
                feature_content_sha256, feature_value_type, raw_status,
                raw_decimal_value, raw_integer_value, raw_reason_code,
                cell_source_lineage_hash, normalized_weight, percentile,
                contribution
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'DECIMAL',
                %s, %s, NULL, %s, %s, 1, %s, %s
            )
            """,
            (
                uuid4(),
                candidate_id,
                candidate_set_id,
                policy.candidate_policy_id,
                definition.dataset_id,
                stack.instrument_id.value,
                "SELECTED" if rankable else "UNRANKABLE",
                component.candidate_policy_component_id,
                component.feature_definition_id,
                str(component.feature_content_sha256),
                status.value,
                Decimal("12.5") if rankable else None,
                "OBSERVED" if rankable else "SOURCE_MISSING",
                lineage_hash,
                Decimal("0.5") if rankable else None,
                Decimal("0.5") if rankable else None,
            ),
        )
        connection.commit()
    return _CandidateSeed(
        candidate_set_id=candidate_set_id,
        candidate_id=candidate_id,
        dataset_id=definition.dataset_id,
        dataset_content_sha256=str(definition.content_sha256),
        manifest_artifact_id=definition.manifest_artifact.artifact_id,
        manifest_content_sha256=str(definition.manifest_artifact.content_sha256),
        manifest_size_bytes=definition.manifest_artifact.size_bytes,
        population_source_id=population_source_id,
        feature_source_id=feature_source_id,
        lineage_hash=lineage_hash,
    )


def _candidate_query_fixture(
    dataset_stack: Any,
) -> tuple[Any, CandidatePolicy, _CandidateSeed, _CandidateSeed, _CandidateSeed]:
    stack = dataset_stack
    feature = replace(
        _feature(stack.artifacts, key_prefix="candidate-query-feature"),
        source_requirements=(
            FeatureSourceRequirement.INSTRUMENT_FACT_REVISION,
        ),
    )
    stack.research.register_feature_definition(
        feature,
        _context("candidate-query-feature-register", "REGISTER_FEATURE_DEFINITION"),
    )
    policy = _register_policy(stack, feature=feature)
    available_definition, available_payload = _register_dataset(
        stack,
        feature=feature,
        key_prefix="candidate-query-available",
        status=FeatureCellStatus.AVAILABLE,
    )
    missing_definition, missing_payload = _register_dataset(
        stack,
        feature=feature,
        key_prefix="candidate-query-missing",
        status=FeatureCellStatus.MISSING,
    )
    inconsistent_definition, inconsistent_payload = _register_dataset(
        stack,
        feature=feature,
        key_prefix="candidate-query-inconsistent-ranking",
        status=FeatureCellStatus.AVAILABLE,
    )
    available = _insert_candidate_authority(
        stack,
        policy=policy,
        definition=available_definition,
        payload=available_payload,
        status=FeatureCellStatus.AVAILABLE,
        hash_character="a",
    )
    missing = _insert_candidate_authority(
        stack,
        policy=policy,
        definition=missing_definition,
        payload=missing_payload,
        status=FeatureCellStatus.MISSING,
        hash_character="b",
    )
    inconsistent = _insert_candidate_authority(
        stack,
        policy=policy,
        definition=inconsistent_definition,
        payload=inconsistent_payload,
        status=FeatureCellStatus.AVAILABLE,
        hash_character="c",
        boundary_score=Decimal("0.4"),
    )
    return stack, policy, available, missing, inconsistent


def test_funnel_and_dossier_explain_constant_and_unrankable_candidates(
    dataset_stack: Any,
) -> None:
    stack, policy, available, missing, inconsistent = _candidate_query_fixture(
        dataset_stack
    )
    component = policy.components[0]
    provider = PostgresCandidateQueryProvider(stack.pool)

    assert provider.funnel(available.candidate_set_id) == CandidateFunnelRecord(
        candidate_set_id=available.candidate_set_id,
        candidate_policy_id=policy.candidate_policy_id,
        dataset_id=available.dataset_id,
        dataset_population_count=1,
        population_count=1,
        rankable_count=1,
        unrankable_count=0,
        selected_count=1,
        ranked_not_selected_count=0,
        score_component_count=1,
        ranking_status="CONSTANT",
        composite_distinct_count=1,
        requested_top_k=1,
        boundary_score=Decimal("0.5"),
        boundary_rank=1,
        strictly_above_boundary_count=0,
        boundary_group_count=1,
        selected_overflow_count=0,
        boundary_has_tie=False,
        boundary_tie_expanded=False,
        actual_population_count=1,
        actual_selected_count=1,
        actual_ranked_not_selected_count=0,
        actual_unrankable_count=0,
        strict_complete_case_unrankable_count=0,
        actual_score_component_count=1,
        population_reconciled=True,
        rankable_reconciled=True,
        component_matrix_reconciled=True,
        ranking_reconciled=True,
        component_diagnostics=(
            CandidateFunnelComponentDiagnostic(
                candidate_policy_component_id=(
                    component.candidate_policy_component_id
                ),
                feature_definition_id=component.feature_definition_id,
                observed_count=1,
                distinct_count=1,
                raw_available_count=1,
                missing_count=0,
                unknown_count=0,
                stale_count=0,
                conflict_count=0,
                available_but_not_observed_count=0,
                rank_information_status="CONSTANT",
            ),
        ),
    )
    assert provider.dossier(
        candidate_set_id=available.candidate_set_id,
        instrument_id=stack.instrument_id.value,
    ) == CandidateDossierRecord(
        candidate_set_id=available.candidate_set_id,
        candidate_id=available.candidate_id,
        candidate_policy_id=policy.candidate_policy_id,
        dataset_id=available.dataset_id,
        dataset_content_sha256=available.dataset_content_sha256,
        dataset_manifest_artifact_id=available.manifest_artifact_id,
        dataset_manifest_content_sha256=available.manifest_content_sha256,
        dataset_manifest_size_bytes=available.manifest_size_bytes,
        instrument_id=stack.instrument_id.value,
        population_dataset_source_id=available.population_source_id,
        population_universe_member_id=stack.universe_member_id,
        population_eligibility_assessment_id=stack.eligibility_assessment_id,
        disposition="SELECTED",
        reason_code="ALL_RANKABLE_SELECTED",
        composite_score=Decimal("0.5"),
        competition_rank=1,
        components=(
            CandidateDossierComponent(
                candidate_policy_component_id=(
                    component.candidate_policy_component_id
                ),
                feature_definition_id=component.feature_definition_id,
                feature_content_sha256=str(component.feature_content_sha256),
                feature_value_type="DECIMAL",
                dataset_feature_source_id=available.feature_source_id,
                direction="HIGHER_IS_BETTER",
                declared_weight=Decimal("3.5"),
                raw_cell_status="AVAILABLE",
                raw_decimal_value=Decimal("12.5"),
                raw_integer_value=None,
                raw_reason_code="OBSERVED",
                percentile=Decimal("0.5"),
                projected_normalized_weight=Decimal("1"),
                contribution=Decimal("0.5"),
                cell_source_lineage_hash=available.lineage_hash,
                observed_count=1,
                distinct_count=1,
                missing_count=0,
                unknown_count=0,
                stale_count=0,
                conflict_count=0,
                raw_available_count=1,
                available_but_not_observed_count=0,
                rank_information_status="CONSTANT",
            ),
        ),
    )

    missing_funnel = provider.funnel(missing.candidate_set_id)
    assert (
        missing_funnel.population_count,
        missing_funnel.rankable_count,
        missing_funnel.unrankable_count,
        missing_funnel.selected_count,
        missing_funnel.strict_complete_case_unrankable_count,
        missing_funnel.ranking_status,
        missing_funnel.population_reconciled,
        missing_funnel.rankable_reconciled,
        missing_funnel.component_matrix_reconciled,
        missing_funnel.ranking_reconciled,
    ) == (1, 0, 1, 0, 1, "NOT_ESTIMABLE", True, True, True, True)
    assert missing_funnel.component_diagnostics == (
        CandidateFunnelComponentDiagnostic(
            candidate_policy_component_id=component.candidate_policy_component_id,
            feature_definition_id=component.feature_definition_id,
            observed_count=0,
            distinct_count=0,
            raw_available_count=0,
            missing_count=1,
            unknown_count=0,
            stale_count=0,
            conflict_count=0,
            available_but_not_observed_count=0,
            rank_information_status="NOT_ESTIMABLE",
        ),
    )
    missing_dossier = provider.dossier(
        candidate_set_id=missing.candidate_set_id,
        instrument_id=stack.instrument_id.value,
    )
    assert missing_dossier.population_dataset_source_id == missing.population_source_id
    assert missing_dossier.disposition == "UNRANKABLE"
    assert (
        missing_dossier.reason_code
        == "STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE"
    )
    assert missing_dossier.composite_score is None
    assert missing_dossier.competition_rank is None
    assert missing_dossier.components == (
        replace(
            provider.dossier(
                candidate_set_id=available.candidate_set_id,
                instrument_id=stack.instrument_id.value,
            ).components[0],
            dataset_feature_source_id=missing.feature_source_id,
            raw_cell_status="MISSING",
            raw_decimal_value=None,
            raw_reason_code="SOURCE_MISSING",
            percentile=None,
            contribution=None,
            cell_source_lineage_hash=missing.lineage_hash,
            observed_count=0,
            distinct_count=0,
            missing_count=1,
            raw_available_count=0,
            rank_information_status="NOT_ESTIMABLE",
        ),
    )
    assert provider.funnel(inconsistent.candidate_set_id).ranking_reconciled is False


def test_candidate_queries_fail_closed_for_unknown_identity(dataset_stack: Any) -> None:
    provider = PostgresCandidateQueryProvider(dataset_stack.pool)

    with pytest.raises(RuntimeNotFoundError, match="CandidateSet"):
        provider.funnel(uuid4())
    with pytest.raises(RuntimeNotFoundError, match="Candidate dossier"):
        provider.dossier(candidate_set_id=uuid4(), instrument_id=uuid4())


def _plan_facts(
    node: dict[str, Any],
) -> tuple[set[str], set[tuple[str, str]], tuple[str, ...]]:
    relations = {str(node["Relation Name"])} if "Relation Name" in node else set()
    indexes = (
        {(str(node.get("Relation Name", "")), str(node["Index Name"]))}
        if "Index Name" in node
        else set()
    )
    predicates = tuple(
        str(node[name])
        for name in ("Index Cond", "Filter", "Hash Cond", "Join Filter")
        if name in node
    )
    for child in node.get("Plans", ()):
        child_relations, child_indexes, child_predicates = _plan_facts(child)
        relations.update(child_relations)
        indexes.update(child_indexes)
        predicates += child_predicates
    return relations, indexes, predicates


def test_candidate_funnel_and_dossier_queries_have_bounded_index_coverage(
    dataset_stack: Any,
) -> None:
    stack, _, available, _, _ = _candidate_query_fixture(dataset_stack)
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ANALYZE mra.candidate_set, mra.candidate,
                    mra.candidate_score_component,
                    mra.candidate_policy_component, mra.dataset,
                    mra.dataset_source, mra.feature_definition,
                    mra.artifact
            """
        )
        plans = (
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT candidate_set_id
                FROM mra.candidate_funnel
                WHERE candidate_set_id = %s
                """,
                (available.candidate_set_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT candidate.candidate_id
                FROM mra.candidate AS candidate
                JOIN mra.candidate_set AS candidate_set
                  ON candidate_set.candidate_set_id = candidate.candidate_set_id
                 AND candidate_set.candidate_policy_id =
                     candidate.candidate_policy_id
                 AND candidate_set.dataset_id = candidate.dataset_id
                JOIN mra.dataset AS dataset
                  ON dataset.dataset_id = candidate_set.dataset_id
                 AND dataset.content_sha256 =
                     candidate_set.dataset_content_sha256
                JOIN mra.artifact AS manifest_artifact
                  ON manifest_artifact.artifact_id =
                     dataset.manifest_artifact_id
                 AND manifest_artifact.content_sha256 =
                     dataset.manifest_content_sha256
                 AND manifest_artifact.size_bytes =
                     dataset.manifest_size_bytes
                JOIN mra.dataset_source AS population_source
                  ON population_source.dataset_source_id =
                     candidate.dataset_population_source_id
                 AND population_source.dataset_id = candidate_set.dataset_id
                 AND population_source.instrument_id = candidate.instrument_id
                 AND population_source.source_role = 'POPULATION'
                WHERE candidate.candidate_set_id = %s
                  AND candidate.instrument_id = %s
                """,
                (available.candidate_set_id, stack.instrument_id.value),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT score.candidate_score_component_id
                FROM mra.candidate_score_component AS score
                JOIN mra.candidate_policy_component AS component
                  ON component.candidate_policy_component_id =
                     score.candidate_policy_component_id
                 AND component.candidate_policy_id =
                     score.candidate_policy_id
                 AND component.feature_definition_id =
                     score.feature_definition_id
                 AND component.feature_content_sha256 =
                     score.feature_content_sha256
                 AND component.feature_value_type = score.feature_value_type
                JOIN mra.feature_definition AS feature
                  ON feature.feature_definition_id =
                     score.feature_definition_id
                 AND feature.content_sha256 = score.feature_content_sha256
                 AND feature.value_type = score.feature_value_type
                JOIN mra.dataset_source AS feature_source
                  ON feature_source.dataset_id = score.dataset_id
                 AND feature_source.feature_definition_id =
                     score.feature_definition_id
                 AND feature_source.source_role = 'FEATURE_DEFINITION'
                JOIN mra.candidate_component_diagnostic AS diagnostic
                  ON diagnostic.candidate_set_id = score.candidate_set_id
                 AND diagnostic.candidate_policy_component_id =
                     score.candidate_policy_component_id
                 AND diagnostic.feature_definition_id =
                     score.feature_definition_id
                WHERE score.candidate_id = %s
                  AND score.candidate_set_id = %s
                """,
                (available.candidate_id, available.candidate_set_id),
            ).fetchone()[0][0]["Plan"],
        )
    facts = tuple(_plan_facts(plan) for plan in plans)
    relations = set().union(*(item[0] for item in facts))
    indexes = set().union(*(item[1] for item in facts))
    plan_predicates = tuple(" ".join(item[2]) for item in facts)
    assert {
        "candidate_set",
        "candidate",
        "candidate_score_component",
        "candidate_policy_component",
        "dataset",
        "dataset_source",
    } <= relations, relations
    assert all(str(available.candidate_set_id) in item for item in plan_predicates)
    assert str(stack.instrument_id.value) in plan_predicates[1]
    assert str(available.candidate_id) in plan_predicates[2]
    acceptable_owner_index_prefixes = {
        "artifact": "artifact_",
        "candidate": "candidate_",
        "candidate_policy_component": "candidate_policy_component_",
        "candidate_score_component": "candidate_score_component_",
        "candidate_set": "candidate_set_",
        "dataset": "dataset_",
        "dataset_source": "dataset_source_",
        "feature_definition": "feature_definition_",
    }
    assert relations <= set(acceptable_owner_index_prefixes), relations
    assert all(
        relation in acceptable_owner_index_prefixes
        and name.startswith(acceptable_owner_index_prefixes[relation])
        for relation, name in indexes
    ), indexes
