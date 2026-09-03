from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import Lock
from uuid import UUID, uuid4

import psycopg
import pytest

from market_regime_alpha.decision_support.application import (
    PortfolioCommands,
    RiskCommands,
)
from market_regime_alpha.decision_support.domain import (
    OpenDecisionRunRequest,
    RequestedDecisionTarget,
    ResearchPurpose,
)
from market_regime_alpha.infrastructure.postgres.evaluation_uow import (
    PostgresEvaluationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.formal_campaign_uow import (
    PostgresFormalCampaignUnitOfWork,
    PostgresFormalCampaignUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.experiment_uow import (
    PostgresExperimentUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.partition_uow import (
    PostgresPartitionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.portfolio_uow import (
    PostgresPortfolioUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.provider_qualification_uow import (
    PostgresProviderQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_portfolio_inputs import (
    PostgresPortfolioInputPreparationProvider,
    PostgresPortfolioQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_risk_inputs import (
    PostgresRiskInputPreparationProvider,
    PostgresRiskQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.formal_campaigns import (
    PostgresFormalCampaignQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.formal_pit import (
    PostgresFormalPitSourceReadPort,
)
from market_regime_alpha.infrastructure.postgres.risk_uow import (
    PostgresRiskUnitOfWorkProvider,
)
from market_regime_alpha.market.application import ProviderQualificationCommands
from market_regime_alpha.market.domain import (
    BarTimeframe,
    PriceBasis,
    ProviderEvidenceClass,
    ProviderQualificationArtifact,
    ProviderQualificationProtocol,
    ProviderQualificationPurpose,
    ProviderQualificationRequirement,
    ProviderRequirementKind,
)
from market_regime_alpha.research_qualification.application import (
    EvaluationCommands,
    ExperimentCommands,
    FormalCampaignCommands,
    QualificationCommands,
    ResearchPartitionCommands,
    build_decision_proof_runtime_profile,
    build_due_proof_runtime_profile,
)
from market_regime_alpha.research_qualification.domain.assessment import (
    AssessmentStatus,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationProtocolPlan,
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    EvaluationFormulaDefinition,
    EvaluationFormulaParameter,
    FormulaParameterType,
)
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceOriginClass,
    EvidenceRole,
)
from market_regime_alpha.research_qualification.domain.formal_campaign import (
    CampaignClass,
    CampaignCostAssumption,
    CampaignCostKind,
    CampaignEvaluationProtocolBinding,
    FormalResearchCampaignDefinition,
    FormalDatasetScope,
)
from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationRunPlan,
)
from market_regime_alpha.research_qualification.domain.partition import (
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.qualification import (
    FloorMissingnessPolicy,
    QualificationOperator,
    QualificationPolicyFloorPlan,
    QualificationPurpose,
    ResearchQualificationPolicyPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    EvaluationReducer,
    EvaluationSliceKind,
    MetricDirection,
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.errors import (
    PartitionInputError,
    ResearchUnknownCommitResultError,
)
from market_regime_alpha.research_qualification.ports.formal_pit import (
    FormalPitSourceKind,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from tests.refoundation.decision_support import test_decision_postgres as _decision
from tests.refoundation.decision_support import (
    test_wp13_decision_closure_postgres as _closure,
)
from tests.refoundation.decision_support import (
    test_wp13_strategy_inference_postgres as _inference,
)
from tests.refoundation.decision_support.test_wp13_decision_closure_domain import (
    _portfolio_policy,
    _risk_policy,
)
from tests.refoundation.research_qualification import test_research_postgres as _research
from tests.refoundation.selection import (
    test_candidate_vertical_slice_postgres as _candidate,
)


class _UnknownCommitCampaignProvider:
    def __init__(self, pool) -> None:
        self._pool = pool
        self._lock = Lock()
        self._raised = False

    def __call__(self):
        provider = self

        class _UnknownCommitUow(PostgresFormalCampaignUnitOfWork):
            def commit(self) -> None:
                super().commit()
                with provider._lock:
                    if not provider._raised:
                        provider._raised = True
                        raise ResearchUnknownCommitResultError(
                            "injected lost Campaign commit acknowledgement"
                        )

        return _UnknownCommitUow(self._pool)


@pytest.fixture
def wp14_campaign_stack(target_database_url, tmp_path, request):
    return _decision.candidate_vertical_stack.__wrapped__(
        target_database_url, tmp_path, request
    )


def _context(key: str):
    return _research._context(f"wp14-{key}", "WP14_ENGINEERING_REHEARSAL")


def _decision_baseline(stack):
    ready = _candidate._ready_candidate(stack, key_prefix="wp14-campaign")
    target = _decision._register_target(stack)
    steps = (
        _candidate._step(
            key="build-candidate-set", kind="BUILD_CANDIDATE_SET", ordinal=1,
            request_character="1",
        ),
        _candidate._step(
            key="open-decision-run", kind="OPEN_DECISION_RUN", ordinal=2,
            request_character="2",
        ),
        _candidate._step(
            key="assess-context", kind="ASSESS_CONTEXT", ordinal=3,
            request_character="3",
        ),
        _candidate._step(
            key="signal-and-forecast", kind="SIGNAL_AND_FORECAST", ordinal=4,
            request_character="4",
        ),
        _candidate._step(
            key="decide-and-risk", kind="DECIDE_AND_RISK", ordinal=5,
            request_character="5",
        ),
    )
    runtime, _ = _candidate._schedule_run(
        stack, steps=steps, canonical_decision_time=stack.decision_time
    )
    candidate_set = ready.application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        _context("build-candidate"),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    decision = _decision._application(stack).open_decision_run(
        OpenDecisionRunRequest(
            candidate_set_id=UUID(candidate_set.aggregate_id),
            targets=(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=stack.product.provider_product_id,
                ),
            ),
            research_purpose=ResearchPurpose.DISCOVERY,
            research_qualifications=(),
        ),
        _context("open-decision"),
        runtime_claim=_candidate._claim(runtime, step_key="open-decision-run"),
    )
    context_policy = _inference._context_policy(
        stack, decision.decision_run_id, runtime
    )
    strategy = _inference._registered_strategy(
        stack, decision.decision_run_id, context_policy
    )
    portfolio = _closure._published_policy_artifacts(
        stack, _portfolio_policy(), "wp14_campaign_portfolio"
    )
    PortfolioCommands(
        PostgresPortfolioInputPreparationProvider(stack.pool),
        PostgresPortfolioUnitOfWorkProvider(stack.pool),
        PostgresPortfolioQueryProvider(stack.pool),
    ).register_policy(portfolio, _context("portfolio-policy"))
    risk = _closure._published_policy_artifacts(
        stack, _risk_policy(), "wp14_campaign_risk"
    )
    RiskCommands(
        PostgresRiskInputPreparationProvider(stack.pool),
        PostgresRiskUnitOfWorkProvider(stack.pool),
        PostgresRiskQueryProvider(stack.pool),
    ).register_policy(risk, _context("risk-policy"))
    return target, ready.policy, context_policy, strategy, portfolio, risk


def _provider_protocol(stack, target):
    with stack.pool.connection(read_only=True) as connection:
        window = connection.execute(
            """
            SELECT min(capture_started_at), max(capture_started_at), max(known_at)
            FROM mra.data_capture
            WHERE provider_product_id = %s
            """,
            (stack.product.provider_product_id,),
        ).fetchone()
    assert window is not None and window[0] is not None
    protocol_id = uuid4()
    protocol = ProviderQualificationProtocol(
        provider_qualification_protocol_id=protocol_id,
        protocol_code=f"wp14-campaign-provider-{uuid4().hex[:8]}",
        revision=1,
        supersedes_protocol_id=None,
        provider_product_id=stack.product.provider_product_id,
        purpose=ProviderQualificationPurpose.HISTORICAL_PIT,
        evidence_class=ProviderEvidenceClass.ENGINEERING_REHEARSAL,
        market_scope="A_SHARE",
        instrument_scope="SSE_EQUITY",
        exchange_code="SSE",
        timeframe=BarTimeframe.MINUTE_1,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        decision_time_rule="SESSION_10_30_ASIA_SHANGHAI",
        capture_window_start=window[0] - timedelta(seconds=1),
        capture_window_end=window[1] + timedelta(seconds=1),
        evidence_cutoff=window[2] + timedelta(seconds=2),
        outcome_path_sessions=1,
        requirements=tuple(
            ProviderQualificationRequirement(
                provider_qualification_requirement_id=uuid4(),
                provider_qualification_protocol_id=protocol_id,
                ordinal=ordinal,
                requirement_kind=kind,
                minimum_observation_count=1,
                minimum_ratio=Decimal("1"),
            )
            for ordinal, kind in enumerate(ProviderRequirementKind, start=1)
        ),
        code_artifact=ProviderQualificationArtifact(
            target.algorithm.code_artifact.artifact_id,
            target.algorithm.code_artifact.content_sha256,
            target.algorithm.code_artifact.size_bytes,
        ),
        config_artifact=ProviderQualificationArtifact(
            target.algorithm.config_artifact.artifact_id,
            target.algorithm.config_artifact.content_sha256,
            target.algorithm.config_artifact.size_bytes,
        ),
        provenance_sha256="1" * 64,
    )
    ProviderQualificationCommands(
        PostgresProviderQualificationUnitOfWorkProvider(
            stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    ).register_protocol(protocol, _context("provider-protocol"))
    return protocol


def _evaluation_protocols(stack, target):
    commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    protocols = []
    source_metric = target.metrics[0]
    for purpose in (
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
        PartitionPurpose.LOCKED_OOS,
    ):
        metric_id = uuid4()
        formula = EvaluationFormulaDefinition(
            evaluation_protocol_metric_id=metric_id,
            formula_code=BacktestFormulaCode.MEAN,
            formula_version=1,
            decimal_precision=28,
            rounding_mode="ROUND_HALF_EVEN",
            parameters=(
                EvaluationFormulaParameter(
                    formula_parameter_id=uuid4(),
                    ordinal=1,
                    parameter_code="minimum_observations",
                    value_type=FormulaParameterType.INTEGER,
                    integer_value=1,
                ),
            ),
            surface=BacktestMetricSurface.ECONOMICS,
        )
        protocol = EvaluationProtocolPlan(
            evaluation_protocol_id=uuid4(),
            protocol_code=f"wp14-{purpose.value.lower()}-{uuid4().hex[:8]}",
            protocol_version=1,
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            applicable_purpose=purpose,
            decision_rule="Apply the immutable declared descriptive reducer.",
            metrics=(
                ProtocolMetricDefinition(
                    evaluation_protocol_metric_id=metric_id,
                    metric_code="mean-return",
                    ordinal=1,
                    source_target_metric_definition_id=(
                        source_metric.target_metric_definition_id
                    ),
                    source_metric_code=source_metric.metric_code,
                    source_value_type=SourceMetricValueType.DECIMAL,
                    reducer=EvaluationReducer.MEAN_DECIMAL,
                    slice_kind=EvaluationSliceKind.ALL_MEMBERS,
                    candidate_disposition=None,
                    direction=MetricDirection.HIGHER,
                    minimum_estimable_count=1,
                    acceptance_operator=AcceptanceOperator.AT_LEAST,
                    acceptance_threshold=Decimal("0"),
                    formula=formula,
                ),
            ),
            code_artifact=target.algorithm.code_artifact,
            config_artifact=target.algorithm.config_artifact,
            provenance_sha256="2" * 64,
        )
        commands.register_protocol(protocol, _context(f"eval-{purpose.value}"))
        protocols.append(protocol)
    return tuple(protocols)


def _qualification_policy(stack, target, locked_protocol):
    metric = locked_protocol.metrics[0]
    floor = QualificationPolicyFloorPlan(
        research_qualification_policy_floor_id=uuid4(),
        floor_code="locked-oos-primary",
        ordinal=1,
        evaluation_protocol_id=locked_protocol.evaluation_protocol_id,
        evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id,
        evaluation_protocol_metric_sha256=metric.content_sha256,
        required_partition_purpose=PartitionPurpose.LOCKED_OOS,
        required_evaluation_status="COMPLETED",
        metric_code=metric.metric_code,
        source_value_type=metric.source_value_type,
        reducer=metric.reducer,
        slice_kind=metric.slice_kind,
        candidate_disposition=None,
        direction=metric.direction,
        operator=QualificationOperator.AT_LEAST,
        decimal_threshold=Decimal("0"),
        boolean_threshold=None,
        minimum_member_count=1,
        minimum_estimable_count=1,
        missingness_policy=FloorMissingnessPolicy.INCONCLUSIVE,
        required_evidence_class=EvidenceClass.RESEARCH_RESULT,
        required_origin_class=EvidenceOriginClass.DERIVED_CANONICAL,
        required_evidence_role=EvidenceRole.PRIMARY_RESULT,
        minimum_support_evidence_count=1,
        maximum_counter_evidence_count=0,
        required=True,
    )
    policy = ResearchQualificationPolicyPlan(
        research_qualification_policy_id=uuid4(),
        policy_code=f"wp14-locked-oos-{uuid4().hex[:8]}",
        version=1,
        supersedes_policy_id=None,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        qualification_purpose=QualificationPurpose.LOCKED_OOS,
        required_assessment_status=AssessmentStatus.SUPPORTED,
        require_preaccess_freeze=True,
        floors=(floor,),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="3" * 64,
    )
    QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    ).register_policy(policy, _context("qualification-policy"))
    return policy


def _campaign_definition(stack):
    target, candidate, context_policy, strategy, portfolio, risk = (
        _decision_baseline(stack)
    )
    provider_protocol = _provider_protocol(stack, target)
    evaluation_protocols = _evaluation_protocols(stack, target)
    qualification = _qualification_policy(stack, target, evaluation_protocols[2])
    purposes = (
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
        PartitionPurpose.LOCKED_OOS,
    )
    plans = tuple(
        ResearchPartitionPlan(
            research_partition_id=uuid4(),
            partition_code=f"wp14-{purpose.value.lower()}-{uuid4().hex[:8]}",
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=purpose,
            population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
            overlap_policy=(
                PartitionOverlapPolicy.ISOLATED_PROTECTED
                if purpose is PartitionPurpose.LOCKED_OOS
                else PartitionOverlapPolicy.DIAGNOSTIC_REUSE
            ),
            exchange_code="XSHG",
            decision_start_session_id=stack.market_session_id,
            decision_end_session_id=stack.market_session_id,
            purge_before_sessions=0,
            purge_after_sessions=0,
            embargo_sessions=0,
            series_code=f"wp14-{purpose.value.lower()}-series",
            fold_ordinal=1,
            code_artifact=target.algorithm.code_artifact,
            config_artifact=target.algorithm.config_artifact,
            provenance_sha256="4" * 64,
        )
        for purpose in purposes
    )
    return FormalResearchCampaignDefinition(
        formal_research_campaign_id=uuid4(),
        campaign_code=f"wp14-campaign-{uuid4().hex[:8]}",
        revision=1,
        supersedes_campaign_id=None,
        campaign_class=CampaignClass.ENGINEERING_REHEARSAL,
        hypothesis="One transparent rule baseline is mechanically testable.",
        experiment_code=f"wp14-experiment-{uuid4().hex[:8]}",
        research_question="Can the frozen baseline execute without authority drift?",
        primary_change="Freeze one transparent baseline without optimization.",
        protocol_identity="wp14-formal-readiness-v1",
        acceptance_semantics="Engineering mechanics only; no empirical admission.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        provider_product_id=stack.product.provider_product_id,
        provider_qualification_protocol_id=(
            provider_protocol.provider_qualification_protocol_id
        ),
        provider_qualification_protocol_sha256=provider_protocol.content_sha256,
        candidate_policy_id=candidate.candidate_policy_id,
        candidate_policy_sha256=candidate.content_sha256,
        context_policy_id=context_policy.context_policy_id,
        context_policy_sha256=context_policy.content_sha256,
        strategy_version_id=strategy.strategy_version_id,
        strategy_version_sha256=strategy.content_sha256,
        portfolio_policy_id=portfolio.portfolio_policy_id,
        portfolio_policy_sha256=portfolio.content_sha256,
        risk_policy_id=risk.risk_policy_id,
        risk_policy_sha256=risk.content_sha256,
        research_qualification_policy_id=(
            qualification.research_qualification_policy_id
        ),
        research_qualification_policy_sha256=qualification.content_sha256,
        partition_plans=plans,
        evaluation_protocol_bindings=tuple(
            CampaignEvaluationProtocolBinding(
                formal_campaign_evaluation_binding_id=uuid4(),
                ordinal=ordinal,
                purpose=purpose,
                evaluation_protocol_id=protocol.evaluation_protocol_id,
                evaluation_protocol_sha256=protocol.content_sha256,
            )
            for ordinal, (purpose, protocol) in enumerate(
                zip(purposes, evaluation_protocols, strict=True), start=1
            )
        ),
        cost_assumptions=tuple(
            CampaignCostAssumption(
                formal_campaign_cost_assumption_id=uuid4(),
                ordinal=ordinal,
                cost_kind=kind,
                amount_bps=Decimal("0"),
            )
            for ordinal, kind in enumerate(CampaignCostKind, start=1)
        ),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="5" * 64,
    )


def test_campaign_predeclaration_is_atomic_exact_and_replayable(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    commands = FormalCampaignCommands(
        PostgresFormalCampaignUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    runtime, _ = _candidate._schedule_run(
        wp14_campaign_stack,
        steps=(
            _candidate._step(
                key="wp14-stale-fence",
                kind="CAPTURE",
                ordinal=1,
                request_character="7",
            ),
        ),
    )
    claim = runtime.claim_next(
        worker_id="wp14-stale-fence-worker",
        lease_duration=timedelta(seconds=30),
        context=_context("claim-stale-fence"),
    )
    assert claim is not None
    runtime.start_attempt(claim, _context("start-stale-fence"))
    stale_claim = replace(claim, fence_token=claim.fence_token + 1)
    with pytest.raises(StaleFenceError):
        commands.predeclare(
            definition,
            _context("predeclare-stale-fence"),
            runtime_claim=stale_claim,
        )
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        stale_counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.formal_research_campaign
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'PREDECLARE_FORMAL_RESEARCH_CAMPAIGN'
                 AND idempotency_key = 'wp14-predeclare-stale-fence')
            """,
            (definition.formal_research_campaign_id,),
        ).fetchone()
    assert stale_counts == (0, 0)
    context = _context("predeclare-campaign")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda _: commands.predeclare(definition, context),
                range(2),
            )
        )
    first = results[0]
    replay = results[1]

    assert {item.replayed for item in results} == {False, True}
    assert replay.aggregate_id == first.aggregate_id
    assert replay.result_hash == first.result_hash
    with pytest.raises(IdempotencyKeyReusedError):
        commands.predeclare(
            replace(definition, hypothesis="A changed posterior hypothesis."),
            context,
        )

    verification = PostgresFormalCampaignQueryPort(
        wp14_campaign_stack.pool
    ).verify(definition.formal_research_campaign_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.formal_research_campaign
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_partition_plan
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_evaluation_protocol
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_cost_assumption
               WHERE formal_research_campaign_id = %s)
            """,
            (definition.formal_research_campaign_id,) * 4,
        ).fetchone()
    assert counts == (1, 3, 3, 3)


def test_campaign_unknown_commit_recovers_exact_authority(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    recovered = FormalCampaignCommands(
        _UnknownCommitCampaignProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    ).predeclare(
        definition,
        _context("campaign-unknown-commit"),
    )
    assert recovered.replayed is True
    assert recovered.aggregate_id == definition.formal_research_campaign_id
    verification = PostgresFormalCampaignQueryPort(
        wp14_campaign_stack.pool
    ).verify(definition.formal_research_campaign_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0


def test_campaign_mid_root_failure_leaves_no_partial_roster_and_recovers(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    commands = FormalCampaignCommands(
        PostgresFormalCampaignUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.test_fail_formal_campaign_root()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'injected Formal campaign root failure'
                USING ERRCODE = '23514';
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_fail_formal_campaign_root_trigger
            AFTER INSERT ON mra.formal_research_campaign
            FOR EACH ROW EXECUTE FUNCTION mra.test_fail_formal_campaign_root()
            """
        )
        connection.commit()
    with pytest.raises(RuntimeStateConflictError):
        commands.predeclare(definition, _context("campaign-mid-root-failure"))
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        partial = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.formal_research_campaign
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_partition_plan
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_evaluation_protocol
               WHERE formal_research_campaign_id = %s),
              (SELECT count(*) FROM mra.formal_research_campaign_cost_assumption
               WHERE formal_research_campaign_id = %s)
            """,
            (definition.formal_research_campaign_id,) * 4,
        ).fetchone()
        connection.execute(
            "DROP TRIGGER test_fail_formal_campaign_root_trigger "
            "ON mra.formal_research_campaign"
        )
        connection.execute("DROP FUNCTION mra.test_fail_formal_campaign_root()")
        connection.commit()
    assert partial == (0, 0, 0, 0)
    recovered = commands.predeclare(
        definition,
        _context("campaign-mid-root-recovery"),
    )
    assert recovered.replayed is False
    assert PostgresFormalCampaignQueryPort(wp14_campaign_stack.pool).verify(
        definition.formal_research_campaign_id
    ).matched is True


def test_rehearsal_decision_can_bind_but_cannot_create_formal_visibility(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    campaign_commands = FormalCampaignCommands(
        PostgresFormalCampaignUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    campaign_commands.predeclare(definition, _context("predeclare-binding"))
    provider_commands = ProviderQualificationCommands(
        PostgresProviderQualificationUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    )
    decision = provider_commands.complete(
        provider_qualification_decision_id=uuid4(),
        decision_code=f"wp14-rehearsal-{uuid4().hex[:8]}",
        provider_qualification_protocol_id=(
            definition.provider_qualification_protocol_id
        ),
        context=_context("complete-provider"),
    )
    assert decision.evidence_class == "ENGINEERING_REHEARSAL"
    assert decision.decision_status != "ADMITTED"
    first = campaign_commands.bind_provider_decision(
        definition.formal_research_campaign_id,
        decision.provider_qualification_decision_id,
        _context("bind-provider"),
    )
    replay = campaign_commands.bind_provider_decision(
        definition.formal_research_campaign_id,
        decision.provider_qualification_decision_id,
        _context("bind-provider"),
    )
    assert replay.replayed is True
    assert replay.result_hash == first.result_hash

    with pytest.raises(RuntimeStateConflictError):
        provider_commands.admit_trading_session_visibility(
            provider_qualification_decision_id=(
                decision.provider_qualification_decision_id
            ),
            session_id=wp14_campaign_stack.market_session_id,
            context=_context("forbidden-visibility"),
        )
    inspection = PostgresFormalCampaignQueryPort(
        wp14_campaign_stack.pool
    ).inspect(definition.formal_research_campaign_id)
    assert inspection.state == "PROVIDER_BOUND"
    assert "PROVIDER_NOT_ADMITTED" in inspection.blockers
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.qualified_trading_session_visibility"
        ).fetchone() == (0,)


def test_campaign_materializes_exact_rosters_and_opens_protected_before_access(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name,
                open_at, break_start_at, break_end_at, close_at,
                decision_reference_at, source_capture_id,
                recorded_at, known_at, decision_visible_at
            )
            SELECT %s, exchange, session_date + 1, timezone_name,
                   open_at + interval '1 day',
                   break_start_at + interval '1 day',
                   break_end_at + interval '1 day',
                   close_at + interval '1 day',
                   decision_reference_at + interval '1 day',
                   source_capture_id,
                   recorded_at, known_at, decision_visible_at
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (uuid4(), wp14_campaign_stack.market_session_id),
        )
        connection.commit()
    campaign_commands = FormalCampaignCommands(
        PostgresFormalCampaignUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    campaign_commands.predeclare(definition, _context("predeclare-materialize"))
    provider_commands = ProviderQualificationCommands(
        PostgresProviderQualificationUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    )
    provider_decision = provider_commands.complete(
        provider_qualification_decision_id=uuid4(),
        decision_code=f"wp14-materialize-{uuid4().hex[:8]}",
        provider_qualification_protocol_id=(
            definition.provider_qualification_protocol_id
        ),
        context=_context("complete-materialize-provider"),
    )
    campaign_commands.bind_provider_decision(
        definition.formal_research_campaign_id,
        provider_decision.provider_qualification_decision_id,
        _context("bind-materialize-provider"),
    )
    for runtime_profile, builder in (
        ("DECISION_PROOF", build_decision_proof_runtime_profile),
        ("DUE_PROOF", build_due_proof_runtime_profile),
    ):
        steps, _ = builder(request_seed=f"wp14-{runtime_profile.lower()}")
        _, runtime_run_id = _candidate._schedule_run(
            wp14_campaign_stack,
            steps=steps,
            canonical_decision_time=wp14_campaign_stack.decision_time,
        )
        campaign_commands.bind_runtime_run(
            definition.formal_research_campaign_id,
            runtime_profile=runtime_profile,
            runtime_run_id=runtime_run_id,
            context=_context(f"bind-{runtime_profile.lower()}-runtime"),
        )

    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    )
    partitions = tuple(
        partition_commands.freeze(
            plan, _context(f"freeze-{plan.purpose.value.lower()}")
        )
        for plan in definition.partition_plans
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        partition_results = tuple(
            executor.map(
                lambda _: campaign_commands.bind_partition_roster(
                    definition.formal_research_campaign_id,
                    _context("bind-partition-roster"),
                ),
                range(2),
            )
        )
    assert {item.replayed for item in partition_results} == {False, True}
    assert len({item.result_hash for item in partition_results}) == 1

    experiment = ExperimentDefinition(
        experiment_id=uuid4(),
        experiment_code=definition.experiment_code,
        research_question=definition.research_question,
        primary_change=definition.primary_change,
        hypothesis=definition.hypothesis,
        target_definition_id=definition.target_definition_id,
        target_version=definition.target_version,
        target_definition_sha256=definition.target_definition_sha256,
        protocol_identity=definition.protocol_identity,
        acceptance_semantics=definition.acceptance_semantics,
        code_artifact=definition.code_artifact,
        config_artifact=definition.config_artifact,
        provenance_sha256=definition.provenance_sha256,
    )
    experiment_bindings = tuple(
        ExperimentPartitionBinding(
            experiment_partition_id=uuid4(),
            experiment_id=experiment.experiment_id,
            binding_ordinal=ordinal,
            research_partition_id=partition.research_partition_id,
            target_definition_id=definition.target_definition_id,
            target_version=definition.target_version,
            target_definition_sha256=definition.target_definition_sha256,
            purpose=plan.purpose,
            partition_content_sha256=partition.content_sha256,
        )
        for ordinal, (plan, partition) in enumerate(
            zip(definition.partition_plans, partitions, strict=True), start=1
        )
    )
    experiment_commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    experiment_commands.register(
        experiment,
        experiment_bindings,
        _context("register-experiment"),
    )
    campaign_commands.bind_experiment(
        definition.formal_research_campaign_id,
        experiment.experiment_id,
        _context("bind-experiment"),
    )
    locked_binding = next(
        binding
        for binding in experiment_bindings
        if binding.purpose is PartitionPurpose.LOCKED_OOS
    )
    experiment_run_id = uuid4()
    experiment_commands.open_run(
        ExperimentRunPlan(
            experiment_run_id=experiment_run_id,
            experiment_id=experiment.experiment_id,
            experiment_partition_id=locked_binding.experiment_partition_id,
            run_identity=f"wp14-locked-{uuid4().hex[:8]}",
        ),
        _context("open-experiment-run"),
    )
    locked_protocol = next(
        binding
        for binding in definition.evaluation_protocol_bindings
        if binding.purpose is PartitionPurpose.LOCKED_OOS
    )
    with wp14_campaign_stack.pool.connection(read_only=True) as connection:
        database_now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    evaluation_run_id = uuid4()
    EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    ).open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=locked_protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=database_now,
            request_identity=f"wp14-evaluation-{uuid4().hex[:8]}",
            code_artifact=definition.code_artifact,
            config_artifact=definition.config_artifact,
            provenance_sha256="6" * 64,
        ),
        _context("open-evaluation-run"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        opened_results = tuple(
            executor.map(
                lambda _: campaign_commands.open_protected(
                    definition.formal_research_campaign_id,
                    purpose=PartitionPurpose.LOCKED_OOS.value,
                    experiment_run_id=experiment_run_id,
                    evaluation_run_id=evaluation_run_id,
                    context=_context("open-protected"),
                ),
                range(2),
            )
        )
    assert {item.replayed for item in opened_results} == {False, True}
    assert {item.aggregate_id for item in opened_results} == {evaluation_run_id}
    inspection = PostgresFormalCampaignQueryPort(
        wp14_campaign_stack.pool
    ).inspect(definition.formal_research_campaign_id)
    assert inspection.state == "PROTECTED_OPEN"
    assert inspection.first_access_count == 0
    verification = PostgresFormalCampaignQueryPort(
        wp14_campaign_stack.pool
    ).verify(definition.formal_research_campaign_id)
    assert verification.matched is True

    with pytest.raises(RuntimeStateConflictError):
        campaign_commands.bind_provider_decision(
            definition.formal_research_campaign_id,
            provider_decision.provider_qualification_decision_id,
            _context("late-provider-binding"),
        )


def test_rehearsal_campaign_cannot_resolve_formal_pit_or_register_formal_dataset(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    campaign_commands = FormalCampaignCommands(
        PostgresFormalCampaignUnitOfWorkProvider(wp14_campaign_stack.pool),
        id_factory=uuid4,
    )
    campaign_commands.predeclare(definition, _context("predeclare-formal-pit"))
    provider_commands = ProviderQualificationCommands(
        PostgresProviderQualificationUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    )
    decision = provider_commands.complete(
        provider_qualification_decision_id=uuid4(),
        decision_code=f"wp14-formal-pit-{uuid4().hex[:8]}",
        provider_qualification_protocol_id=(
            definition.provider_qualification_protocol_id
        ),
        context=_context("complete-formal-pit-provider"),
    )
    campaign_commands.bind_provider_decision(
        definition.formal_research_campaign_id,
        decision.provider_qualification_decision_id,
        _context("bind-formal-pit-provider"),
    )

    with pytest.raises(RuntimeStateConflictError):
        PostgresFormalPitSourceReadPort(wp14_campaign_stack.pool).resolve_exact(
            formal_research_campaign_id=definition.formal_research_campaign_id,
            provider_qualification_decision_id=(
                decision.provider_qualification_decision_id
            ),
            source_kind=FormalPitSourceKind.INSTRUMENT_FACT_REVISION,
            source_identity=wp14_campaign_stack.market_fact_revision_id,
            requested_decision_time=wp14_campaign_stack.decision_time.value,
        )

    feature_suffix = uuid4().hex[:8]
    feature = replace(
        _research._dataset_feature(wp14_campaign_stack),
        feature_code=f"wp14_formal_feature_{feature_suffix}",
    )
    wp14_campaign_stack.research.register_feature_definition(
        feature,
        _context("register-formal-dataset-feature"),
    )
    dataset, _ = _research._dataset_input(
        wp14_campaign_stack,
        feature,
        key_prefix=f"wp14_formal_dataset_{uuid4().hex[:8]}",
    )
    scope = FormalDatasetScope(
        formal_research_campaign_id=definition.formal_research_campaign_id,
        provider_qualification_decision_id=(
            decision.provider_qualification_decision_id
        ),
    )
    with pytest.raises(RuntimeStateConflictError):
        wp14_campaign_stack.research.register_formal_dataset(
            dataset,
            scope,
            _context("register-formal-dataset"),
        )
    ordinary = wp14_campaign_stack.research.register_dataset(
        dataset,
        _context("register-ordinary-dataset"),
    )
    assert UUID(ordinary.aggregate_id) == dataset.dataset_id
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.formal_research_dataset),
              (SELECT count(*) FROM mra.qualified_market_bar_visibility)
                + (SELECT count(*) FROM mra.qualified_instrument_fact_visibility)
                + (SELECT count(*) FROM mra.qualified_classification_membership_visibility)
                + (SELECT count(*) FROM mra.qualified_trading_session_visibility)
                + (SELECT count(*) FROM mra.qualified_source_gap_visibility)
            """
        ).fetchone()
    assert counts == (0, 0)


def test_historical_fixture_shadow_commitment_cannot_masquerade_as_prospective(
    wp14_campaign_stack,
) -> None:
    definition = _campaign_definition(wp14_campaign_stack)
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name,
                open_at, break_start_at, break_end_at, close_at,
                decision_reference_at, source_capture_id,
                recorded_at, known_at, decision_visible_at
            )
            SELECT %s, exchange, session_date + 1, timezone_name,
                   open_at + interval '1 day',
                   break_start_at + interval '1 day',
                   break_end_at + interval '1 day',
                   close_at + interval '1 day',
                   decision_reference_at + interval '1 day',
                   source_capture_id,
                   recorded_at, known_at, decision_visible_at
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (uuid4(), wp14_campaign_stack.market_session_id),
        )
        connection.commit()
    prospective_plan = replace(
        definition.partition_plans[2],
        research_partition_id=uuid4(),
        partition_code=f"wp14-prospective-{uuid4().hex[:8]}",
        purpose=PartitionPurpose.PROSPECTIVE,
        overlap_policy=PartitionOverlapPolicy.ISOLATED_PROTECTED,
        series_code=f"wp14-prospective-{uuid4().hex[:8]}",
    )
    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(
            wp14_campaign_stack.pool, id_factory=uuid4
        ),
        id_factory=uuid4,
    )
    with pytest.raises(PartitionInputError):
        partition_commands.freeze(
            prospective_plan,
            _context("freeze-prospective-live-clock"),
        )
    with psycopg.connect(wp14_campaign_stack.database_url) as connection:
        count = connection.execute(
            """
            SELECT count(*) FROM mra.research_partition
            WHERE research_partition_id = %s
            """,
            (prospective_plan.research_partition_id,),
        ).fetchone()[0]
    assert count == 0
