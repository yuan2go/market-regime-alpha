from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from market_regime_alpha.application.continuous_research.composition import (
    CONTINUOUS_CHILD_ORDER,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
)
from market_regime_alpha.application.decision_system.contracts import (
    DecisionModelQualification,
    DecisionWindowState,
    bind_decision_candidate_evidence,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.runtime import (
    DECISION_RUNTIME_STAGE_ORDER,
    DecisionRuntimeInputs,
    DecisionRuntimeReceipt,
    DecisionRuntimeStage,
    DecisionStageReceipt,
    DecisionSystemDelegate,
    DecisionSystemRuntimeService as _DecisionSystemRuntimeService,
)
from market_regime_alpha.application.state_system.bundles import (
    scoped_state_stage_bundle_identity,
    state_research_pipeline_identity,
)
from market_regime_alpha.core.identity import ArtifactId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    RuntimeModelLineage,
)
from tests.application.decision_system.support import (
    AS_OF,
    HASH_A,
    HASH_B,
    active_claim,
    candidate,
    lineage,
    observation,
    risk_configuration,
    tolerance,
)
from tests.application.decision_system.governance_fixture import (
    FIXTURE_PRODUCTION_SELECTOR,
    runtime_model_lineage,
)
from tests.persistence.postgres.conftest import (
    postgres_factory as postgres_factory,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    _command,
    _tick,
)


UTC = timezone.utc


class DecisionSystemRuntimeService(_DecisionSystemRuntimeService):
    """Unit-test composition with explicit engineering governance fixture."""

    def __init__(self, repository, **kwargs):
        kwargs.setdefault("model_selector", FIXTURE_PRODUCTION_SELECTOR)
        super().__init__(repository, **kwargs)


def test_scoped_state_bundle_binds_exact_multi_scope_members() -> None:
    full = scoped_state_stage_bundle_identity(
        stage="ETF_ROTATION",
        members=(
            (ArtifactId("etf-state-a"), HASH_A, "510300.SH"),
            (ArtifactId("etf-state-b"), HASH_B, "510500.SH"),
        ),
    )
    reordered = scoped_state_stage_bundle_identity(
        stage="ETF_ROTATION",
        members=(
            (ArtifactId("etf-state-b"), HASH_B, "510500.SH"),
            (ArtifactId("etf-state-a"), HASH_A, "510300.SH"),
        ),
    )
    subset = scoped_state_stage_bundle_identity(
        stage="ETF_ROTATION",
        members=((ArtifactId("etf-state-a"), HASH_A, "510300.SH"),),
    )

    assert full == reordered
    assert full != subset


def test_runtime_receipt_producer_rejects_noncanonical_unicode() -> None:
    with pytest.raises(ValueError, match="Unicode NFC"):
        DecisionStageReceipt(
            stage=DecisionRuntimeStage.ACCOUNT_OBSERVATION_LOOKUP,
            status="BLOCKED",
            artifact_id=None,
            artifact_hash=None,
            reason_codes=("Cafe\u0301",),
        )

    stage = DecisionStageReceipt(
        stage=DecisionRuntimeStage.ACCOUNT_OBSERVATION_LOOKUP,
        status="BLOCKED",
        artifact_id=None,
        artifact_hash=None,
        reason_codes=("INPUT_BLOCKED",),
    )
    with pytest.raises(ValueError, match="Unicode NFC"):
        DecisionRuntimeReceipt.create(
            run_id=ArtifactId("run-a"),
            tick_id=ArtifactId("tick-a"),
            claim_id="Cafe\u0301",
            fencing_token=1,
            tick_version=1,
            lease_expires_at=AS_OF + timedelta(minutes=1),
            state_receipt_id=ArtifactId("state-receipt-a"),
            state_receipt_hash=HASH_A,
            reconciliation_id=None,
            summary_id=None,
            proposal_id=None,
            risk_decision_id=None,
            status="BLOCKED",
            stage_receipts=(stage,),
            created_at=AS_OF,
        )


def _scoped_hash(label: str, claim) -> str:
    return canonical_hash({"label": label, "run_id": str(claim.run_id), "tick_id": str(claim.tick_id)})


def _scoped_id(label: str, claim) -> ArtifactId:
    return ArtifactId(f"{label}-{_scoped_hash(label, claim)[7:31]}")


def _runtime_lineage(
    claim,
    *,
    has_candidates: bool = True,
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY,
):
    base = replace(
        lineage(
            claim,
            position_snapshot_ids=(),
            has_candidates=has_candidates,
        ),
        state_receipt_id=_scoped_id("state-receipt", claim),
        state_receipt_hash=_scoped_hash("state-receipt", claim),
        market_state_id=_scoped_id("market-state", claim),
        etf_state_ids=(_scoped_id("etf-state", claim),),
        theme_state_ids=(_scoped_id("theme-state", claim),),
        capital_state_id=_scoped_id("capital-state", claim),
        dynamic_pool_id=_scoped_id("dynamic-pool", claim),
        data_eligibility=data_eligibility,
    )
    bound = bind_decision_candidate_evidence(
        base,
        ((candidate(dynamic_pool_id=base.dynamic_pool_id, current_quantity=0),) if has_candidates else ()),
    )
    pipeline_id, pipeline_hash = state_research_pipeline_identity(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        as_of_time=AS_OF,
        stages=tuple(
            (stage, artifact_id, artifact_hash, AS_OF)
            for stage, artifact_id, artifact_hash in _runtime_stage_specs(
                claim,
                bound,
            )
        ),
    )
    receipt_payload = _state_receipt_payload(
        pipeline_id=pipeline_id,
        pipeline_hash=pipeline_hash,
        stage_specs=_runtime_stage_specs(claim, bound),
        data_eligibility=bound.data_eligibility,
    )
    receipt_hash = canonical_hash(receipt_payload)
    return replace(
        bound,
        state_receipt_id=ArtifactId(f"state-system-receipt:{receipt_hash[7:]}"),
        state_receipt_hash=receipt_hash,
    )


def _runtime_stage_specs(claim, decision_lineage):
    state_values = (
        ("MARKET_REGIME", decision_lineage.market_state_id, "NEUTRAL"),
        ("ETF_ROTATION", decision_lineage.etf_state_ids[0], "LEADERSHIP_BROAD"),
        ("THEME_ROTATION", decision_lineage.theme_state_ids[0], "BROADENING"),
        ("CAPITAL_STATE", decision_lineage.capital_state_id, "NEUTRAL"),
    )
    state_hashes = {
        stage: canonical_hash(
            {
                "schema_version": "decision-test-state/v1",
                "state_id": str(state_id),
                "effective_state": effective,
            }
        )
        for stage, state_id, effective in state_values
    }
    return (
        (
            "OBSERVATION",
            _scoped_id("observation-bundle", claim),
            _scoped_hash("observation-bundle", claim),
        ),
        (
            "MARKET_REGIME",
            decision_lineage.market_state_id,
            state_hashes["MARKET_REGIME"],
        ),
        (
            "ETF_ROTATION",
            decision_lineage.etf_state_ids[0],
            state_hashes["ETF_ROTATION"],
        ),
        (
            "THEME_ROTATION",
            decision_lineage.theme_state_ids[0],
            state_hashes["THEME_ROTATION"],
        ),
        (
            "CAPITAL_STATE",
            decision_lineage.capital_state_id,
            state_hashes["CAPITAL_STATE"],
        ),
        (
            "DYNAMIC_POOL",
            decision_lineage.dynamic_pool_id,
            _scoped_hash("dynamic-pool-content", claim),
        ),
        (
            "CANDIDATE",
            decision_lineage.candidate_binding_id,
            decision_lineage.candidate_binding_hash,
        ),
        (
            "SIGNAL",
            decision_lineage.signal_bundle_id,
            decision_lineage.signal_bundle_hash,
        ),
        (
            "FORECAST",
            decision_lineage.forecast_bundle_id,
            decision_lineage.forecast_bundle_hash,
        ),
    )


def _state_receipt_payload(*, pipeline_id, pipeline_hash, stage_specs, data_eligibility):
    return {
        "schema": "state_system_runtime_receipt/v2",
        "request_idempotency_key": "decision-test-state-request",
        "pipeline_artifact_id": str(pipeline_id),
        "pipeline_artifact_hash": pipeline_hash,
        "stage_references": [
            {
                "reference_kind": f"STATE_RESEARCH_{stage}",
                "artifact_id": str(artifact_id),
                "content_hash": artifact_hash,
                "data_eligibility": data_eligibility.value,
            }
            for stage, artifact_id, artifact_hash in stage_specs
        ],
        "reason_codes": ["ENTRY_BLOCKED", "STATE_RESEARCH_CHAIN_COMPLETED"],
    }


def _request(
    claim,
    *,
    as_of: datetime = AS_OF,
    decision_lineage=None,
) -> ChildExecutionRequest:
    runtime_lineage = decision_lineage or _runtime_lineage(claim)
    return ChildExecutionRequest(
        trading_date=as_of.date(),
        as_of_time=as_of,
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        claim_id=claim.claim_id,
        fencing_token=claim.fencing_token,
        tick_version=claim.tick_version,
        lease_acquired_at=claim.lease_acquired_at,
        lease_expires_at=claim.lease_expires_at,
        heartbeat_at=claim.heartbeat_at,
        provider_attempt_id=1,
        source_manifest_id=ArtifactId("source-manifest-a"),
        source_manifest_hash=HASH_A,
        evidence_commit_id=ArtifactId("evidence-commit-a"),
        evidence_commit_hash=HASH_B,
        decision_id=ArtifactId("change-decision-a"),
        decision_hash=HASH_A,
        input_references=(
            RuntimeArtifactReference(
                "EVIDENCE",
                ArtifactId("evidence-commit-a"),
                HASH_B,
            ),
            RuntimeArtifactReference(
                "STATE_SYSTEM_OUTPUT",
                runtime_lineage.state_receipt_id,
                runtime_lineage.state_receipt_hash,
            ),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "CONFIGURATION",
                ArtifactId("decision-config-a"),
                HASH_A,
            ),
            RuntimeArtifactReference(
                "CONFIGURATION",
                ArtifactId("strategy-config-a"),
                HASH_A,
            ),
        ),
    )


def _inputs(
    claim,
    account_id: ArtifactId,
    *,
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY,
) -> DecisionRuntimeInputs:
    runtime_lineage = _runtime_lineage(claim, data_eligibility=data_eligibility)
    candidates = (
        candidate(
            dynamic_pool_id=runtime_lineage.dynamic_pool_id,
            current_quantity=0,
        ),
    )
    return DecisionRuntimeInputs(
        manual_observation_id=account_id,
        reconciliation_tolerance=tolerance(),
        reconciliation_revision=1,
        previous_reconciliation_id=None,
        strategy_configuration_id=ArtifactId("strategy-config-a"),
        strategy_configuration_hash=HASH_A,
        lineage=runtime_lineage,
        candidates=candidates,
        summary_revision=1,
        previous_summary_id=None,
        correction_of_summary_id=None,
        risk_configuration=risk_configuration(),
        model_runtime_lineages=tuple(
            runtime_model_lineage(
                model_id,
                dataset=(
                    ArtifactLineageReference(
                        "DECISION_SIGNAL_BUNDLE",
                        runtime_lineage.signal_bundle_id,
                        runtime_lineage.signal_bundle_hash,
                    )
                    if model_id in {str(item.signal_model_id) for item in candidates}
                    else ArtifactLineageReference(
                        "DECISION_FORECAST_BUNDLE",
                        runtime_lineage.forecast_bundle_id,
                        runtime_lineage.forecast_bundle_hash,
                    )
                ),
                universe_id=UniverseId(str(runtime_lineage.dynamic_pool_id)),
                data_eligibility=data_eligibility,
            )
            for model_id in sorted(
                {str(item.signal_model_id) for item in candidates} | {str(item.forecast_model_id) for item in candidates}
            )
        ),
        finalize=True,
    )


def _seed_state_authority(
    factory: PostgresConnectionFactory,
    claim,
    *,
    decision_lineage=None,
) -> None:
    decision_lineage = decision_lineage or _runtime_lineage(claim)
    state_specs = (
        (
            "market_regime_state",
            "market_regime_state_observation",
            decision_lineage.market_state_id,
            _scoped_id("market-observation", claim),
            "NEUTRAL",
            "A_SHARE",
        ),
        (
            "etf_rotation_state",
            "etf_rotation_state_observation",
            decision_lineage.etf_state_ids[0],
            _scoped_id("etf-observation", claim),
            "LEADERSHIP_BROAD",
            "510300.SH",
        ),
        (
            "theme_rotation_state",
            "theme_rotation_state_observation",
            decision_lineage.theme_state_ids[0],
            _scoped_id("theme-observation", claim),
            "BROADENING",
            "BANK",
        ),
        (
            "capital_state",
            "capital_state_observation",
            decision_lineage.capital_state_id,
            _scoped_id("capital-observation", claim),
            "NEUTRAL",
            "A_SHARE",
        ),
    )
    state_hashes: dict[str, str] = {}
    with factory.connection() as connection:
        for (
            state_table,
            observation_table,
            state_id,
            observation_id,
            effective,
            scope_key,
        ) in state_specs:
            observation_payload = {
                "schema_version": "decision-test-state-observation/v1",
                "observation_id": str(observation_id),
            }
            observation_hash = canonical_hash(observation_payload)
            state_payload = {
                "schema_version": "decision-test-state/v1",
                "state_id": str(state_id),
                "effective_state": effective,
            }
            state_hash = canonical_hash(state_payload)
            state_hashes[state_table] = state_hash
            connection.execute(  # noqa: S608 - fixed test table allowlist
                f"""
                INSERT INTO {observation_table}(
                    observation_id, observation_hash, run_id, tick_id,
                    as_of_time, available_at, artifact_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(observation_id),
                    observation_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    AS_OF,
                    AS_OF,
                    json.dumps(observation_payload, sort_keys=True),
                    AS_OF,
                ),
            )
            connection.execute(  # noqa: S608 - fixed test table allowlist
                f"""
                INSERT INTO {state_table}(
                    state_id, state_hash, observation_id, previous_state_id,
                    scope_key, effective_state, artifact_json, created_at
                ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)
                """,
                (
                    str(state_id),
                    state_hash,
                    str(observation_id),
                    scope_key,
                    effective,
                    json.dumps(state_payload, sort_keys=True),
                    AS_OF,
                ),
            )
        pool_hash = _scoped_hash("dynamic-pool-content", claim)
        stage_specs = _runtime_stage_specs(claim, decision_lineage)
        pipeline_id, pipeline_hash = state_research_pipeline_identity(
            run_id=claim.run_id,
            tick_id=claim.tick_id,
            as_of_time=AS_OF,
            stages=tuple((stage, artifact_id, artifact_hash, AS_OF) for stage, artifact_id, artifact_hash in stage_specs),
        )
        receipt_payload = _state_receipt_payload(
            pipeline_id=pipeline_id,
            pipeline_hash=pipeline_hash,
            stage_specs=stage_specs,
            data_eligibility=decision_lineage.data_eligibility,
        )
        assert canonical_hash(receipt_payload) == decision_lineage.state_receipt_hash
        receipt_json = {
            "schema": "state_runtime_child_receipt/v2",
            "child_kind": "STATE_SYSTEM",
            "child_run_id": f"state-test-run:{claim.tick_id}",
            "child_receipt_id": str(decision_lineage.state_receipt_id),
            "child_receipt_hash": decision_lineage.state_receipt_hash,
            "child_artifact_id": str(pipeline_id),
            "child_artifact_hash": pipeline_hash,
            "input_references": [],
            "configuration_references": [],
            "receipt_payload": receipt_payload,
        }
        connection.execute(
            """
            INSERT INTO dynamic_stock_pool(
                pool_id, pool_hash, previous_pool_id, pool_version, run_id,
                tick_id, claim_id, fencing_token, tick_version, effective_at,
                available_at, decision_time, material_state_hash,
                configuration_id, configuration_hash, pool_json, created_at
            ) VALUES (
                %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                str(decision_lineage.dynamic_pool_id),
                pool_hash,
                claim.tick_sequence,
                str(claim.run_id),
                str(claim.tick_id),
                claim.claim_id,
                claim.fencing_token,
                claim.tick_version,
                AS_OF,
                AS_OF,
                AS_OF,
                _scoped_hash("material-state", claim),
                "state-config-a",
                HASH_A,
                json.dumps({"schema_version": "decision-test-pool/v1"}),
                AS_OF,
            ),
        )
        connection.execute(
            """
            INSERT INTO dynamic_stock_pool_member(
                pool_id, symbol, included, rank, member_json
            ) VALUES (%s, %s, TRUE, 1, %s)
            """,
            (
                str(decision_lineage.dynamic_pool_id),
                "600000.SH",
                json.dumps({"symbol": "600000.SH", "included": True, "rank": 1}),
            ),
        )
        connection.execute(
            """
            INSERT INTO state_runtime_receipt(
                receipt_id, receipt_hash, run_id, tick_id, pool_id, status,
                receipt_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, 'COMPLETED', %s, %s)
            """,
            (
                str(decision_lineage.state_receipt_id),
                decision_lineage.state_receipt_hash,
                str(claim.run_id),
                str(claim.tick_id),
                str(decision_lineage.dynamic_pool_id),
                json.dumps(receipt_json, sort_keys=True),
                AS_OF,
            ),
        )
        for stage, artifact_id, artifact_hash in stage_specs:
            connection.execute(
                """
                INSERT INTO state_research_stage_authority(
                    run_id, tick_id, state_receipt_id, stage, artifact_id,
                    artifact_hash, data_eligibility, available_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    str(decision_lineage.state_receipt_id),
                    stage,
                    str(artifact_id),
                    artifact_hash,
                    decision_lineage.data_eligibility.value,
                    AS_OF,
                    AS_OF,
                ),
            )
        connection.commit()


def _execution_authority_counts(
    postgres_factory: PostgresConnectionFactory,
) -> tuple[int, ...]:
    with postgres_factory.connection(read_only=True) as connection:
        return tuple(
            int(
                connection.execute(
                    f"SELECT count(*) FROM {table}"  # noqa: S608 - fixed test allowlist
                ).fetchone()[0]
            )
            for table in (
                "execution_commands",
                "manual_trade_records",
                "manual_fills",
                "position_book_events",
                "trading_opportunities",
            )
        )


def test_decision_system_precedes_strategy_and_daily_alpha_projection() -> None:
    assert tuple(ContinuousChildKind).count(ContinuousChildKind.DECISION_SYSTEM) == 1
    assert CONTINUOUS_CHILD_ORDER[-3:] == (
        ContinuousChildKind.DECISION_SYSTEM,
        ContinuousChildKind.STRATEGY_RUNTIME,
        ContinuousChildKind.DAILY_ALPHA_SNAPSHOT,
    )


def test_runtime_executes_ordered_decision_stages_with_explicit_fixture_selector(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    inputs = _inputs(
        claim,
        account.observation_id,
        data_eligibility=DataEligibility.FORMAL_RESEARCH,
    )
    _seed_state_authority(postgres_factory, claim, decision_lineage=inputs.lineage)
    request = _request(claim, decision_lineage=inputs.lineage)
    delegate = DecisionSystemDelegate(
        _DecisionSystemRuntimeService(
            repository,
            model_selector=FIXTURE_PRODUCTION_SELECTOR,
        ),
        input_loader=lambda _: inputs,
    )
    before = _execution_authority_counts(postgres_factory)

    result = delegate.execute(request)
    replay = delegate.lookup(request)
    receipt = repository.get_runtime_receipt(
        run_id=request.run_id,
        tick_id=request.tick_id,
    )

    assert replay == result
    assert receipt.risk_decision_id is not None, tuple((item.stage, item.status, item.reason_codes) for item in receipt.stage_receipts)
    persisted_risk = repository.get_risk_decision(receipt.risk_decision_id)
    assert receipt.status == "BLOCKED", (
        persisted_risk.result,
        persisted_risk.reason_codes,
        tuple((item.stage, item.status, item.reason_codes) for item in receipt.stage_receipts),
    )
    assert tuple(item.stage for item in receipt.stage_receipts) == (DECISION_RUNTIME_STAGE_ORDER)
    assert receipt.summary_id is not None
    final = repository.get_summary(receipt.summary_id)
    assert final.lifecycle_state is DecisionWindowState.BLOCKED
    assert final.revision == 2
    assert final.previous_summary_id is not None
    assert _execution_authority_counts(postgres_factory) == before


def test_runtime_ignores_forged_candidate_qualification_and_fails_closed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    _seed_state_authority(postgres_factory, claim)
    inputs = _inputs(claim, account.observation_id)
    assert all(item.model_qualification.value == "QUALIFIED" for item in inputs.candidates)

    receipt = _DecisionSystemRuntimeService(
        repository,
        model_selector=PostgresModelGovernanceRepository(postgres_factory),
    ).execute(
        request=_request(claim),
        inputs=inputs,
    )

    assert receipt.status == "BLOCKED"
    assert receipt.reconciliation_id is None
    assert receipt.proposal_id is None
    assert receipt.risk_decision_id is None
    assert receipt.stage_receipts[-1].stage is DecisionRuntimeStage.MODEL_GOVERNANCE
    assert "CHAMPION_AUTHORITY_MISSING" in (receipt.stage_receipts[-1].reason_codes)
    with postgres_factory.connection(read_only=True) as connection:
        statuses = connection.execute("SELECT selection_status FROM model_selection_receipt ORDER BY model_slot").fetchall()
    assert statuses == [("REJECTED",), ("REJECTED",)]


def test_runtime_derives_qualified_output_when_caller_claims_unqualified(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    inputs = _inputs(claim, account.observation_id)
    inputs = replace(
        inputs,
        candidates=tuple(
            replace(
                item,
                model_qualification=DecisionModelQualification.UNQUALIFIED,
            )
            for item in inputs.candidates
        ),
    )
    _seed_state_authority(postgres_factory, claim, decision_lineage=inputs.lineage)

    receipt = DecisionSystemRuntimeService(repository).execute(
        request=_request(claim, decision_lineage=inputs.lineage),
        inputs=inputs,
    )

    assert receipt.summary_id is not None
    summary = repository.get_summary(receipt.summary_id)
    assert all(item.model_qualification.value == "QUALIFIED" for item in summary.candidates)


def test_runtime_persists_rejection_for_caller_forged_dynamic_model_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    _seed_state_authority(postgres_factory, claim)
    inputs = _inputs(claim, account.observation_id)
    first = inputs.model_runtime_lineages[0]
    forged = runtime_model_lineage(str(first.model_id))
    inputs = replace(
        inputs,
        model_runtime_lineages=(forged, *inputs.model_runtime_lineages[1:]),
    )

    receipt = _DecisionSystemRuntimeService(
        repository,
        model_selector=PostgresModelGovernanceRepository(postgres_factory),
    ).execute(request=_request(claim), inputs=inputs)

    assert receipt.status == "BLOCKED"
    with postgres_factory.connection(read_only=True) as connection:
        payloads = connection.execute("SELECT payload_json FROM model_selection_receipt").fetchall()
    assert any("RUNTIME_LINEAGE_AUTHORITY_MISMATCH" in row[0]["reason_codes"] for row in payloads)


def test_runtime_cannot_uplift_persisted_exploratory_data_to_formal(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    inputs = _inputs(claim, account.observation_id)
    _seed_state_authority(postgres_factory, claim, decision_lineage=inputs.lineage)
    original = inputs.model_runtime_lineages[0]
    forged = RuntimeModelLineage.create(
        model_id=original.model_id,
        definition_hash=original.definition_hash,
        dataset=original.dataset,
        universe_id=original.universe_id,
        feature_definition_ids=original.feature_definition_ids,
        feature_materializations=original.feature_materializations,
        configuration=original.configuration,
        code_revision=original.code_revision,
        code_hash=original.code_hash,
        validation_protocol_refs=original.validation_protocol_refs,
        data_eligibility=DataEligibility.FORMAL_RESEARCH,
    )
    inputs = replace(
        inputs,
        model_runtime_lineages=(forged, *inputs.model_runtime_lineages[1:]),
    )

    receipt = _DecisionSystemRuntimeService(
        repository,
        model_selector=PostgresModelGovernanceRepository(postgres_factory),
    ).execute(
        request=_request(claim, decision_lineage=inputs.lineage),
        inputs=inputs,
    )

    assert receipt.status == "BLOCKED"
    with postgres_factory.connection(read_only=True) as connection:
        reasons = connection.execute("SELECT payload_json->'reason_codes' FROM model_selection_receipt").fetchall()
    assert any("RUNTIME_LINEAGE_AUTHORITY_MISMATCH" in row[0] for row in reasons)


def test_runtime_cannot_complete_formal_decision_without_model_selection(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    empty_lineage = _runtime_lineage(claim, has_candidates=False)
    _seed_state_authority(
        postgres_factory,
        claim,
        decision_lineage=empty_lineage,
    )
    inputs = replace(
        _inputs(claim, account.observation_id),
        lineage=empty_lineage,
        candidates=(),
        model_runtime_lineages=(),
    )

    receipt = _DecisionSystemRuntimeService(
        repository,
        model_selector=FIXTURE_PRODUCTION_SELECTOR,
    ).execute(
        request=_request(claim, decision_lineage=empty_lineage),
        inputs=inputs,
    )

    assert receipt.status == "BLOCKED"
    assert receipt.reconciliation_id is None
    assert receipt.stage_receipts[-1].stage is DecisionRuntimeStage.MODEL_GOVERNANCE
    assert receipt.stage_receipts[-1].reason_codes == ("MODEL_SELECTION_REQUIRED",)


def test_runtime_records_window_not_open_as_fail_closed_receipt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    before_window = datetime(2026, 8, 6, 6, 29, tzinfo=UTC)
    clock = MutableClock(before_window)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    request = _request(claim, as_of=before_window)
    delegate = DecisionSystemDelegate(
        DecisionSystemRuntimeService(repository),
        input_loader=lambda _: _inputs(claim, ArtifactId("missing-observation")),
    )

    result = delegate.execute(request)
    receipt = repository.get_runtime_receipt(
        run_id=request.run_id,
        tick_id=request.tick_id,
    )

    assert result.child_artifact_id is None
    assert receipt.status == "BLOCKED"
    assert receipt.stage_receipts[0].reason_codes == ("WINDOW_NOT_OPEN",)
    assert repository.authority_counts()["daily_decision_summary"] == 0


def test_concurrent_finalize_keeps_one_terminal_and_blocks_loser(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    journal, first_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    _seed_state_authority(postgres_factory, first_claim)
    first_request = _request(first_claim)
    first_receipt = DecisionSystemRuntimeService(repository).execute(
        request=first_request,
        inputs=_inputs(first_claim, account.observation_id),
    )
    assert first_receipt.reconciliation_id is not None
    assert first_receipt.summary_id is not None

    command = _command()
    second_tick = journal.admit_tick(
        _tick(command, minute=44),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    second_claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=second_tick.command.tick_id,
    )
    _seed_state_authority(postgres_factory, second_claim)
    second_request = _request(second_claim)
    second_inputs = replace(
        _inputs(second_claim, account.observation_id),
        reconciliation_revision=2,
        previous_reconciliation_id=first_receipt.reconciliation_id,
        summary_revision=3,
        previous_summary_id=first_receipt.summary_id,
    )

    second_receipt = DecisionSystemRuntimeService(repository).execute(
        request=second_request,
        inputs=second_inputs,
    )

    assert second_receipt.status == "BLOCKED"
    assert second_receipt.stage_receipts[-1].reason_codes == ("FINAL_ALREADY_EXISTS_OR_SUMMARY_CAS_REJECTED",)
    with postgres_factory.connection(read_only=True) as connection:
        terminal_count = connection.execute(
            """
            SELECT count(*) FROM daily_decision_summary
            WHERE lifecycle_state IN ('FINALIZED', 'BLOCKED')
            """
        ).fetchone()[0]
    assert terminal_count == 1


def test_correction_appends_version_without_overwriting_original_final(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    journal, first_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation(positions=()))
    _seed_state_authority(postgres_factory, first_claim)
    first = DecisionSystemRuntimeService(repository).execute(
        request=_request(first_claim),
        inputs=_inputs(first_claim, account.observation_id),
    )
    assert first.reconciliation_id is not None
    assert first.summary_id is not None
    original = repository.get_summary(first.summary_id)

    command = _command()
    second_tick = journal.admit_tick(
        _tick(command, minute=44),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    second_claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=second_tick.command.tick_id,
    )
    _seed_state_authority(postgres_factory, second_claim)
    corrected_inputs = replace(
        _inputs(second_claim, account.observation_id),
        reconciliation_revision=2,
        previous_reconciliation_id=first.reconciliation_id,
        summary_revision=3,
        previous_summary_id=first.summary_id,
        correction_of_summary_id=first.summary_id,
    )

    corrected_receipt = DecisionSystemRuntimeService(repository).execute(
        request=_request(second_claim),
        inputs=corrected_inputs,
    )

    assert corrected_receipt.status == "COMPLETED"
    assert corrected_receipt.summary_id is not None
    correction = repository.get_summary(corrected_receipt.summary_id)
    assert correction.lifecycle_state is DecisionWindowState.CORRECTED
    assert correction.correction_of_summary_id == original.summary_id
    assert correction.revision == 4
    assert repository.get_summary(original.summary_id) == original
