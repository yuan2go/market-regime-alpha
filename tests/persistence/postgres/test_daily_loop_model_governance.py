from __future__ import annotations

from datetime import timedelta

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    RunMode,
)
from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.runner import (
    DAILY_B0_B1_EVALUATION_PROTOCOL_ID,
    DAILY_B0_B1_EXPERIMENT_PROTOCOL_IDS,
    DAILY_B0_B1_MODEL_SET_ID,
    DAILY_MODEL_SLOTS,
    DailyLoopRunner,
    _configuration_hash,
)
from market_regime_alpha.application.daily_loop.state import DailyRunStatus
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    publish_source_archive,
)
from market_regime_alpha.daily_decision.target_adapter import (
    build_pending_mr1_candidate_dataset,
)
from market_regime_alpha.features.daily_pipeline import (
    materialize_public_daily_baseline_features,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    DAILY_B0_B1_MODEL_IDS,
    b0_b1_model_definitions,
    b0_b1_model_version_lineages,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import (
    AssignmentLane,
    SelectionStatus,
    RuntimePurpose,
)
from market_regime_alpha.universe.daily_exploratory import (
    reconcile_daily_universe,
    smoke_pool_policy_v1,
)
from tests.application.daily_loop.public_fixture import DECISION, public_fixture
from tests.platform.test_runtime_governance import _evidence, _research_policy


CODE_REVISION = "bd868b06df13c4a657a169e5039c91c1d69a5ef9"


def test_daily_loop_predictions_are_selected_by_postgres_governance(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    universe_policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(policy=universe_policy)
    archive = publish_source_archive(
        root=tmp_path / "archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.REPLAY,
        provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        universe_policy_id=str(universe_policy.policy_id),
        model_set_id=DAILY_B0_B1_MODEL_SET_ID,
        configuration_identity=ArtifactId("governed-daily-loop-config-v1"),
        output_root=tmp_path / "runtime",
        replay_source_manifest_id=source_manifest.source_manifest_id,
    )
    config_hash = _configuration_hash(command)
    reconciliation = reconcile_daily_universe(
        policy=universe_policy,
        source_manifest=source_manifest,
        provider_result=provider_result,
    )
    features = materialize_public_daily_baseline_features(
        reconciliation=reconciliation,
        provider_result=provider_result,
        code_revision=CODE_REVISION,
        config_hash=config_hash,
    )
    dataset = build_pending_mr1_candidate_dataset(
        reconciliation=reconciliation,
        feature_result=features,
        code_revision=CODE_REVISION,
        config_hash=config_hash,
    )
    definitions = b0_b1_model_definitions(dataset)
    governed_at = DECISION.value - timedelta(minutes=1)
    lineages = b0_b1_model_version_lineages(
        dataset,
        model_definitions=definitions,
        evaluation_protocol_id=DAILY_B0_B1_EVALUATION_PROTOCOL_ID,
        code_revision=CODE_REVISION,
        created_at=governed_at,
    )
    governance = PostgresModelGovernanceRepository(postgres_factory)
    registry = PersistentModelRegistry(governance)
    research_policy = _research_policy()
    governance.record_policy(
        research_policy,
        actor="governance-operator",
        reason="DailyLoop PostgreSQL integration policy",
        created_at=governed_at,
        idempotency_key="daily-loop-research-policy",
    )
    assignments = {}
    for model_id in DAILY_B0_B1_MODEL_IDS:
        registered = registry.register(
            definitions[model_id],
            idempotency_key=f"daily-loop-register:{model_id}",
        )
        research = registry.transition(
            model_id,
            expected_version=registered.version,
            idempotency_key=f"daily-loop-research:{model_id}",
            to_status=ModelLifecycleStatus.RESEARCH,
            changed_at=governed_at,
            reason="explicit DailyLoop Research lifecycle",
            evidence_refs=(f"daily-loop-lifecycle:{model_id}",),
            evidence_level=EvidenceLevel.EXPLORATORY,
        )
        lineage = governance.record_version_lineage(
            lineages[model_id],
            actor="governance-operator",
            reason="bind DailyLoop model lineage",
            idempotency_key=f"daily-loop-lineage:{model_id}",
        )
        for kind in research_policy.required_evidence_kinds:
            governance.record_evidence(
                _evidence(lineage, kind, at=governed_at),
                idempotency_key=f"daily-loop-evidence:{model_id}:{kind.value}",
            )
        governance.qualify(
            model_id=model_id,
            policy_id=research_policy.policy_id,
            actor="governance-reviewer",
            reason="explicit DailyLoop Research qualification",
            approval_ref=f"approval:daily-loop:{model_id}",
            decided_at=governed_at,
            expected_registry_version=research.version,
            idempotency_key=f"daily-loop-qualify:{model_id}",
        )
        assignments[model_id] = governance.assign(
            runtime_scope="DAILY_LOOP",
            model_slot=DAILY_MODEL_SLOTS[model_id],
            purpose=RuntimePurpose.RESEARCH,
            lane=AssignmentLane.CHAMPION,
            model_id=model_id,
            policy_id=research_policy.policy_id,
            expected_governance_revision=governance.current_revision(),
            effective_at=governed_at,
            actor="governance-operator",
            reason="explicit DailyLoop Research Champion",
            approval_ref=f"approval:daily-loop-champion:{model_id}",
            idempotency_key=f"daily-loop-champion:{model_id}",
        )
    first_model, second_model = DAILY_B0_B1_MODEL_IDS
    governance.replace_champion(
        assignments[first_model].assignment_id,
        new_model_id=second_model,
        policy_id=research_policy.policy_id,
        expected_version=assignments[first_model].version,
        expected_governance_revision=governance.current_revision(),
        effective_at=governed_at,
        actor="governance-operator",
        reason="swap Daily executable Champions",
        approval_ref="approval:daily-loop-swap-first",
        idempotency_key="daily-loop-swap-first",
    )
    governance.replace_champion(
        assignments[second_model].assignment_id,
        new_model_id=first_model,
        policy_id=research_policy.policy_id,
        expected_version=assignments[second_model].version,
        expected_governance_revision=governance.current_revision(),
        effective_at=governed_at,
        actor="governance-operator",
        reason="swap Daily executable Champions",
        approval_ref="approval:daily-loop-swap-second",
        idempotency_key="daily-loop-swap-second",
    )

    daily_repository = PostgresDailyRunRepository(postgres_factory)
    result = DailyLoopRunner(
        repository=daily_repository,
        code_revision=CODE_REVISION,
        policy=universe_policy,
        model_selector=governance,
        clock=lambda: DECISION.value + timedelta(minutes=5),
    ).run(command, replay_archive_path=archive)
    assert result.record.daily_run_id is not None
    replayed = DailyLoopRunner(
        repository=daily_repository,
        code_revision=CODE_REVISION,
        policy=universe_policy,
        model_selector=governance,
    ).replay_daily_run(result.record.daily_run_id)
    assert replayed.bundle == result.decision_artifact.bundle

    receipt = daily_repository.get_stage_receipt(
        command.run_request_id,
        DailyRunStatus.PREDICTIONS_PUBLISHED,
    )
    assert receipt is not None
    assert len(receipt.output_artifact_ids) == 4
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM model_selection_receipt ORDER BY model_slot"
        ).fetchall()
    assert len(rows) == 2
    assert all(row[0]["status"] == SelectionStatus.SELECTED.value for row in rows)
    assert {
        row[0]["model_slot"]: row[0]["selected_model_id"] for row in rows
    } == {
        DAILY_MODEL_SLOTS[first_model]: str(second_model),
        DAILY_MODEL_SLOTS[second_model]: str(first_model),
    }
    assert {
        item.model_id for item in result.decision_artifact.bundle.prediction_runs
    } == set(DAILY_B0_B1_MODEL_IDS)
    assert set(DAILY_B0_B1_EXPERIMENT_PROTOCOL_IDS) == set(DAILY_B0_B1_MODEL_IDS)
