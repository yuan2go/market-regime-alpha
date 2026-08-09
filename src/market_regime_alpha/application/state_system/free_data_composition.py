"""Canonical FreeData adapters for the existing PostgreSQL State authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from statistics import fmean
from typing import Any, Callable, Mapping

from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledOperationPreparation,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    VerifiedControlledResearchArtifact,
    discover_controlled_candidates,
)
from market_regime_alpha.application.decision_system.research_summary import (
    GOVERNED_RESEARCH_MODEL_SLOTS,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateDomain,
)
from market_regime_alpha.application.state_system.runtime import (
    OrderedStateResearchPipeline,
    StateResearchStage,
    StateResearchStageArtifact,
    StateResearchStageContext,
    StateResearchStageService,
    StateResearchStageStatus,
    StateSystemRuntimeDelegate,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.platform.runtime_governance import (
    ModelSelectionReceipt,
    SelectionStatus,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.state_system.capital import (
    CapitalObservation,
    CapitalState,
    CapitalStateEvaluation,
    StatefulCapitalState,
    evaluate_capital_state,
)
from market_regime_alpha.research.state_system.common import (
    StateLineage,
    parse_canonical_datetime,
)
from market_regime_alpha.research.state_system.configuration import (
    CapitalStateConfiguration,
    DynamicPoolConfiguration,
    EtfRotationConfiguration,
    MarketStateConfiguration,
    MissingDataPolicy,
    ThemeRotationConfiguration,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.etf_rotation import (
    EtfRotationEvaluation,
    EtfRotationObservation,
    EtfRotationState,
    StatefulEtfRotation,
    evaluate_etf_rotation,
)
from market_regime_alpha.research.state_system.market import (
    MarketRegimeObservation,
    MarketRegimeState,
    MarketStateEvaluation,
    StatefulMarketRegime,
    evaluate_market_state,
)
from market_regime_alpha.research.state_system.pool import (
    DynamicPoolEvaluationStatus,
    DynamicPoolMember,
    DynamicPoolStateContext,
    DynamicStockPoolVersion,
    PoolEligibilityObservation,
    evaluate_dynamic_pool,
)
from market_regime_alpha.research.state_system.research_integration import (
    StateBoundCandidateSet,
    bind_candidate_set,
)
from market_regime_alpha.research.state_system.theme_rotation import (
    StatefulThemeRotation,
    ThemeRotationEvaluation,
    ThemeRotationObservation,
    ThemeRotationState,
    evaluate_theme_rotation,
)
from market_regime_alpha.universe.operational import STStatus, SuspensionStatus


Clock = Callable[[], datetime]


@dataclass(slots=True)
class _StateWork:
    request: ChildExecutionRequest
    preparation: ControlledOperationPreparation
    research: VerifiedControlledResearchArtifact
    candidates: CandidateSet
    receipts: dict[StateResearchStage, ModelSelectionReceipt]
    repository: PostgresStateSystemRepository
    clock: Clock
    market: MarketStateEvaluation | None = None
    etfs: tuple[EtfRotationEvaluation, ...] = ()
    themes: tuple[ThemeRotationEvaluation, ...] = ()
    capital: CapitalStateEvaluation | None = None
    pool: DynamicStockPoolVersion | None = None
    bound_candidates: StateBoundCandidateSet | None = None
    final_candidates: CandidateSet | None = None
    stage_artifacts: dict[StateResearchStage, StateResearchStageArtifact] | None = None
    stage_completed_at: dict[StateResearchStage, datetime] | None = None


@dataclass(frozen=True, slots=True)
class _StageService(StateResearchStageService):
    stage: StateResearchStage
    operation: Callable[[StateResearchStageContext], StateResearchStageArtifact]
    work: _StateWork

    def execute(
        self, context: StateResearchStageContext
    ) -> StateResearchStageArtifact:
        result = self.operation(context)
        if self.work.stage_artifacts is None:
            self.work.stage_artifacts = {}
        self.work.stage_artifacts[self.stage] = result
        if self.work.stage_completed_at is None:
            self.work.stage_completed_at = {}
        self.work.stage_completed_at[self.stage] = self.work.clock()
        return result


@dataclass(frozen=True, slots=True)
class _FixedStageService(StateResearchStageService):
    stage: StateResearchStage
    artifact: StateResearchStageArtifact

    def execute(
        self, context: StateResearchStageContext
    ) -> StateResearchStageArtifact:
        return self.artifact


class CanonicalFreeDataStateCoordinator:
    """Run/persist WP-STATE-01 before candidate-scoped minute acquisition."""

    def __init__(
        self,
        *,
        request: ChildExecutionRequest,
        repository: PostgresStateSystemRepository,
        selection_receipts: tuple[
            tuple[StateResearchStage, ModelSelectionReceipt], ...
        ],
        clock: Clock,
    ) -> None:
        self._request = request
        self._repository = repository
        self._receipts = dict(selection_receipts)
        self._clock = clock
        self.child_result: ChildExecutionResult | None = None
        self.work: _StateWork | None = None
        self._blocked_artifacts: dict[
            StateResearchStage, StateResearchStageArtifact
        ] = {}
        self._blocked_completed_at: dict[StateResearchStage, datetime] = {}

    @property
    def stage_artifacts(self) -> dict[StateResearchStage, StateResearchStageArtifact]:
        if self.work is None or self.work.stage_artifacts is None:
            return dict(self._blocked_artifacts)
        return dict(self.work.stage_artifacts)

    @property
    def stage_completed_at(self) -> dict[StateResearchStage, datetime]:
        if self.work is None or self.work.stage_completed_at is None:
            return dict(self._blocked_completed_at)
        return dict(self.work.stage_completed_at)

    @property
    def final_candidates(self) -> CandidateSet | None:
        return None if self.work is None else self.work.final_candidates

    def record_model_blocked(
        self,
        *,
        reason_codes: tuple[str, ...],
    ) -> None:
        """Persist an owner receipt without executing an unselected model."""

        services: dict[StateResearchStage, StateResearchStageService] = {}
        artifacts: dict[StateResearchStage, StateResearchStageArtifact] = {}
        completed_at = self._clock()
        for stage in tuple(StateResearchStage)[:7]:
            reasons = tuple(
                sorted(
                    {
                        *reason_codes,
                        "MODEL_NOT_QUALIFIED_FOR_MODE",
                        f"{stage.value}_NOT_EXECUTED",
                    }
                )
            )
            digest = canonical_hash(
                {
                    "schema": "state-stage-model-blocked/v1",
                    "stage": stage.value,
                    "evidence_commit_id": str(self._request.evidence_commit_id),
                    "reason_codes": list(reasons),
                }
            )
            artifact = StateResearchStageArtifact(
                stage=stage,
                artifact_id=ArtifactId(
                    f"state-stage-model-blocked:{digest[7:]}"
                ),
                artifact_hash=digest,
                available_at=min(self._request.as_of_time, completed_at),
                data_eligibility=DataEligibility.EXPLORATORY,
                reason_codes=reasons,
                status=StateResearchStageStatus.DATA_INSUFFICIENT,
            )
            artifacts[stage] = artifact
            services[stage] = _FixedStageService(stage, artifact)
        delegate = StateSystemRuntimeDelegate(
            pipeline=OrderedStateResearchPipeline(services=services),
            repository=self._repository,
        )
        self.child_result = delegate.execute(self._request)
        self._blocked_artifacts = artifacts
        self._blocked_completed_at = {
            stage: completed_at for stage in artifacts
        }

    def __call__(
        self,
        preparation: ControlledOperationPreparation,
        research: VerifiedControlledResearchArtifact,
        candidates: CandidateSet,
    ) -> CandidateSet:
        work = _StateWork(
            request=self._request,
            preparation=preparation,
            research=research,
            candidates=candidates,
            receipts=self._receipts,
            repository=self._repository,
            clock=self._clock,
        )
        self.work = work
        existing = self._repository.lookup_runtime_child(self._request)
        if existing is not None:
            stages, completed_at = self._repository.read_runtime_stages(self._request)
            work.stage_artifacts = {item.stage: item for item in stages}
            work.stage_completed_at = completed_at
            work.final_candidates = self._repository.read_runtime_candidate(
                self._request
            )
            self.child_result = existing
            return work.final_candidates
        services: dict[StateResearchStage, StateResearchStageService] = {
            StateResearchStage.OBSERVATION: _StageService(
                StateResearchStage.OBSERVATION,
                lambda context: _observation_stage(work, context),
                work,
            ),
            StateResearchStage.MARKET_REGIME: _StageService(
                StateResearchStage.MARKET_REGIME,
                lambda context: _market_stage(work, context),
                work,
            ),
            StateResearchStage.ETF_ROTATION: _StageService(
                StateResearchStage.ETF_ROTATION,
                lambda context: _etf_stage(work, context),
                work,
            ),
            StateResearchStage.THEME_ROTATION: _StageService(
                StateResearchStage.THEME_ROTATION,
                lambda context: _theme_stage(work, context),
                work,
            ),
            StateResearchStage.CAPITAL_STATE: _StageService(
                StateResearchStage.CAPITAL_STATE,
                lambda context: _capital_stage(work, context),
                work,
            ),
            StateResearchStage.DYNAMIC_POOL: _StageService(
                StateResearchStage.DYNAMIC_POOL,
                lambda context: _pool_stage(work, context),
                work,
            ),
            StateResearchStage.CANDIDATE: _StageService(
                StateResearchStage.CANDIDATE,
                lambda context: _candidate_stage(work, context),
                work,
            ),
        }
        delegate = StateSystemRuntimeDelegate(
            pipeline=OrderedStateResearchPipeline(services=services),
            repository=self._repository,
        )
        self.child_result = delegate.execute(self._request)
        stages, completed_at = self._repository.read_runtime_stages(self._request)
        work.stage_artifacts = {item.stage: item for item in stages}
        work.stage_completed_at = completed_at
        work.final_candidates = self._repository.read_runtime_candidate(
            self._request
        )
        return work.final_candidates


def _observation_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    bundle = work.research.artifact.inputs.supplemental_evidence
    return StateResearchStageArtifact(
        stage=StateResearchStage.OBSERVATION,
        artifact_id=bundle.bundle_id,
        artifact_hash=bundle.content_hash,
        available_at=_evidence_available_at(work),
        data_eligibility=DataEligibility.EXPLORATORY,
        reason_codes=("FREE_DATA_OBSERVATION_FROZEN",),
    )


def _market_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    snapshot = work.research.artifact.market_regime
    _assert_selected_execution(
        work,
        StateResearchStage.MARKET_REGIME,
        snapshot.envelope.model_id,
        snapshot.envelope.model_version,
        snapshot.envelope.configuration_id,
        snapshot.envelope.configuration_hash,
    )
    config = _state_configuration(
        MarketStateConfiguration,
        work,
        StateResearchStage.MARKET_REGIME,
    )
    components = tuple(
        value
        for value in (
            snapshot.direction_score,
            snapshot.breadth_score,
            snapshot.liquidity_score,
            snapshot.volatility_score,
            snapshot.limit_structure_score,
        )
        if value is not None
    )
    score = Decimal(str(fmean(components))) if components else Decimal("0")
    missing = () if components else ("MARKET_REGIME_COMPONENTS",)
    lineage = _lineage(work, config.model_id, config.model_version, config)
    observation = MarketRegimeObservation.create(
        v0_snapshot_id=snapshot.envelope.artifact_id,
        regime_score=score,
        data_coverage=Decimal(str(snapshot.confidence)),
        missing_evidence=missing,
        counter_evidence=(),
        reason_codes=tuple(sorted({*snapshot.reason_codes, "V0_MARKET_BOUND"})),
        lineage=lineage,
    )
    evaluation = evaluate_market_state(
        observation,
        previous=_previous_market(work, "A_SHARE_MARKET"),
        configuration=config,
    )
    _append_evaluation(
        work,
        StateDomain.MARKET_REGIME,
        "A_SHARE_MARKET",
        evaluation,
    )
    work.market = evaluation
    return _state_artifact(
        StateResearchStage.MARKET_REGIME,
        evaluation.state.state_id,
        evaluation.state.state_hash,
        lineage.available_at,
        evaluation.state.reason_codes,
    )


def _etf_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    values = work.research.artifact.inputs.supplemental_evidence.stateful_etf_observations
    if not values:
        return _insufficient_stage(
            work,
            StateResearchStage.ETF_ROTATION,
            ("STATEFUL_ETF_OBSERVATION",),
        )
    config = _deterministic_state_configuration(
        EtfRotationConfiguration,
        "free-data-etf-rotation-policy-v1",
    )
    evaluations = []
    for value in values:
        lineage = _lineage(
            work,
            config.model_id,
            config.model_version,
            config,
            available_at=value.available_at.value,
        )
        observation = EtfRotationObservation.create(
            etf_id=value.etf_id,
            benchmark_id=value.benchmark_id,
            relative_strength_1d=Decimal(str(value.relative_strength_1d)),
            relative_strength_3d=Decimal(str(value.relative_strength_3d)),
            relative_strength_5d=Decimal(str(value.relative_strength_5d)),
            relative_strength_10d=Decimal(str(value.relative_strength_10d)),
            benchmark_excess=Decimal(str(value.benchmark_excess)),
            amount_change=Decimal(str(value.amount_change)),
            amount_persistence=Decimal(str(value.amount_persistence)),
            volume_change=Decimal(str(value.volume_change)),
            drawdown=Decimal(str(value.drawdown)),
            volatility=Decimal(str(value.volatility)),
            diffusion=Decimal(str(value.diffusion)),
            liquidity=Decimal(str(value.liquidity)),
            data_coverage=Decimal(str(value.data_coverage)),
            missing_evidence=(),
            counter_evidence=(),
            reason_codes=tuple(
                sorted({*value.reason_codes, "STATEFUL_ETF_EVIDENCE_BOUND"})
            ),
            lineage=lineage,
        )
        evaluation = evaluate_etf_rotation(
            observation,
            previous=_previous_etf(work, value.etf_id),
            configuration=config,
        )
        _append_evaluation(
            work,
            StateDomain.ETF_ROTATION,
            value.etf_id,
            evaluation,
        )
        evaluations.append(evaluation)
    work.etfs = tuple(evaluations)
    return _bundle_artifact(
        StateResearchStage.ETF_ROTATION,
        tuple(
            (item.state.state_id, item.state.state_hash)
            for item in evaluations
        ),
        max(item.observation.lineage.available_at for item in evaluations),
        tuple(
            sorted(
                {reason for item in evaluations for reason in item.state.reason_codes}
            )
        ),
    )


def _theme_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    inputs = work.research.artifact.inputs.supplemental_evidence
    if not inputs.theme_observations or not work.etfs:
        return _insufficient_stage(
            work,
            StateResearchStage.THEME_ROTATION,
            ("THEME_OBSERVATION", "ETF_ROTATION"),
        )
    snapshot = work.research.artifact.theme_rotation
    _assert_selected_execution(
        work,
        StateResearchStage.THEME_ROTATION,
        snapshot.envelope.model_id,
        snapshot.envelope.model_version,
        snapshot.envelope.configuration_id,
        snapshot.envelope.configuration_hash,
    )
    config = _state_configuration(
        ThemeRotationConfiguration,
        work,
        StateResearchStage.THEME_ROTATION,
    )
    capital = {item.theme_id: item for item in inputs.capital_observations}
    mappings = {item.etf_id: item for item in inputs.etf_theme_mappings}
    etf_by_id = {item.state.etf_id: item for item in work.etfs}
    evaluations = []
    for value in inputs.theme_observations:
        related = tuple(
            etf_by_id[item]
            for item in value.proxy_etf_ids
            if item in etf_by_id
        )
        mapping_complete = bool(related) and all(
            item in mappings and mappings[item].theme_id == value.theme_id
            for item in value.proxy_etf_ids
        )
        if not related:
            continue
        related_ids = tuple(
            sorted((item.state.state_id for item in related), key=str)
        )
        mapping_hash = canonical_hash(
            {
                "theme_id": value.theme_id,
                "mappings": [
                    mappings[item].to_canonical_dict()
                    for item in sorted(value.proxy_etf_ids)
                    if item in mappings
                ],
            }
        )
        capital_value = capital.get(value.theme_id)
        lineage = _lineage(
            work,
            config.model_id,
            config.model_version,
            config,
            available_at=value.available_at.value,
        )
        observation = ThemeRotationObservation.create(
            theme_id=value.theme_id,
            theme_mapping_id=ArtifactId(f"theme-mapping:{mapping_hash[7:]}"),
            theme_mapping_version="free-supplemental-v1",
            mapping_complete=mapping_complete,
            proxy_etf_ids=value.proxy_etf_ids,
            etf_rotation_state_ids=related_ids,
            verified_etf_strength=_signed_to_unit_decimal(
                fmean(float(item.state.rotation_score) for item in related)
            ),
            stock_breadth=_unit_decimal(value.breadth),
            participation_rate=_unit_decimal(value.participation_change),
            leader_resonance=_unit_decimal(value.leader_strength),
            internal_concentration=_unit_decimal(
                None
                if capital_value is None
                else capital_value.capital_concentration
            ),
            amount_persistence=_unit_decimal(
                None
                if capital_value is None
                else capital_value.amount_persistence
            ),
            data_coverage=Decimal(str(value.confidence)),
            missing_evidence=(),
            counter_evidence=(),
            reason_codes=tuple(sorted({*value.reason_codes, "THEME_EVIDENCE_BOUND"})),
            lineage=lineage,
        )
        evaluation = evaluate_theme_rotation(
            observation,
            previous=_previous_theme(work, value.theme_id),
            configuration=config,
        )
        _append_evaluation(
            work,
            StateDomain.THEME_ROTATION,
            value.theme_id,
            evaluation,
        )
        evaluations.append(evaluation)
    if not evaluations:
        return _insufficient_stage(
            work,
            StateResearchStage.THEME_ROTATION,
            ("THEME_ETF_MAPPING",),
        )
    work.themes = tuple(evaluations)
    return _bundle_artifact(
        StateResearchStage.THEME_ROTATION,
        tuple((item.state.state_id, item.state.state_hash) for item in evaluations),
        max(item.observation.lineage.available_at for item in evaluations),
        tuple(sorted({reason for item in evaluations for reason in item.state.reason_codes})),
    )


def _capital_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    inputs = work.research.artifact.inputs.supplemental_evidence
    if not inputs.capital_observations or not work.themes:
        return _insufficient_stage(
            work,
            StateResearchStage.CAPITAL_STATE,
            ("CAPITAL_OBSERVATION", "THEME_ROTATION"),
        )
    snapshot = work.research.artifact.capital_evolution
    _assert_selected_execution(
        work,
        StateResearchStage.CAPITAL_STATE,
        snapshot.envelope.model_id,
        snapshot.envelope.model_version,
        snapshot.envelope.configuration_id,
        snapshot.envelope.configuration_hash,
    )
    config = _state_configuration(
        CapitalStateConfiguration,
        work,
        StateResearchStage.CAPITAL_STATE,
    )
    theme_values = inputs.theme_observations
    capital_values = inputs.capital_observations
    coverage = min((item.confidence for item in theme_values), default=0.0)
    lineage = _lineage(
        work,
        config.model_id,
        config.model_version,
        config,
        available_at=max(item.available_at.value for item in capital_values),
    )
    observation = CapitalObservation.create(
        scope_id="A_SHARE_RESEARCH",
        price_change=_signed_mean(item.relative_strength_1d for item in theme_values),
        volume_change=_signed_mean(item.etf_amount_expansion for item in capital_values),
        amount_change=_signed_mean(item.etf_amount_expansion for item in capital_values),
        breadth_change=_signed_mean(item.breadth for item in theme_values),
        participation_change=_signed_mean(item.participation_change for item in theme_values),
        concentration=_unit_mean(item.capital_concentration for item in capital_values),
        etf_strength=_signed_mean(float(item.state.rotation_score) for item in work.etfs),
        data_coverage=Decimal(str(coverage)),
        uncertainty=Decimal("1") - Decimal(str(coverage)),
        missing_evidence=(),
        counter_evidence=(),
        reason_codes=("OBSERVABLE_CAPITAL_PROXIES_BOUND",),
        lineage=lineage,
    )
    evaluation = evaluate_capital_state(
        observation,
        previous=_previous_capital(work, "A_SHARE_RESEARCH"),
        configuration=config,
    )
    _append_evaluation(
        work,
        StateDomain.CAPITAL_STATE,
        "A_SHARE_RESEARCH",
        evaluation,
    )
    work.capital = evaluation
    return _state_artifact(
        StateResearchStage.CAPITAL_STATE,
        evaluation.state.state_id,
        evaluation.state.state_hash,
        lineage.available_at,
        evaluation.state.reason_codes,
    )


def _pool_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    if work.market is None or not work.etfs or not work.themes or work.capital is None:
        return _insufficient_stage(
            work,
            StateResearchStage.DYNAMIC_POOL,
            ("MARKET_ETF_THEME_CAPITAL_STATE",),
        )
    config = _pool_configuration()
    lineage = _lineage(
        work,
        ModelId("deterministic-dynamic-pool-policy-v1"),
        "v1",
        config,
    )
    universe = work.preparation.universe
    memberships = {
        item.symbol: item
        for item in work.research.artifact.inputs.supplemental_evidence.theme_memberships
    }
    eligibility = tuple(
        PoolEligibilityObservation(
            symbol=item.symbol,
            eligible=item.included,
            eligibility_reason=(
                "OPERATIONAL_UNIVERSE_ELIGIBLE"
                if item.included
                else item.exclusion_reasons[0]
            ),
            liquidity=(
                Decimal("1")
                if item.liquidity_evidence.median_daily_amount is not None
                else Decimal("0")
            ),
            board=item.exchange.value,
            is_st=item.st_status is STStatus.ST,
            suspended=item.suspension_status is SuspensionStatus.SUSPENDED,
            listing_age_days=item.history_sessions_observed,
            theme_overlap=(
                ()
                if item.symbol not in memberships
                else tuple(
                    sorted(
                        {
                            memberships[item.symbol].primary_theme_id,
                            *memberships[item.symbol].supporting_theme_ids,
                        }
                    )
                )
            ),
            data_coverage=Decimal("1") if item.included else Decimal("0"),
            missing_evidence=(),
        )
        for item in universe.records
    )
    state_context = DynamicPoolStateContext(
        market_regime_state_id=work.market.state.state_id,
        market_regime_state=work.market.state.effective_state.value,
        etf_rotation_states=tuple(
            sorted(
                (
                    item.state.state_id,
                    item.state.effective_state.value,
                    item.state.state_duration_seconds,
                )
                for item in work.etfs
            )
        ),
        theme_rotation_states=tuple(
            sorted(
                (
                    item.state.state_id,
                    item.state.effective_state.value,
                    item.state.state_duration_seconds,
                )
                for item in work.themes
            )
        ),
        capital_state_id=work.capital.state.state_id,
        capital_state=work.capital.state.effective_state.value,
        data_coverage=min(
            work.market.state.data_coverage,
            work.capital.state.data_coverage,
            *(item.state.data_coverage for item in work.etfs),
            *(item.state.data_coverage for item in work.themes),
        ),
        available_at=max(
            work.market.observation.lineage.available_at,
            work.capital.observation.lineage.available_at,
            *(item.observation.lineage.available_at for item in work.etfs),
            *(item.observation.lineage.available_at for item in work.themes),
        ),
    )
    previous_pool = _previous_pool(work)
    result = evaluate_dynamic_pool(
        state_context=state_context,
        eligibility=eligibility,
        previous=previous_pool,
        configuration=config,
        lineage=lineage,
    )
    pool = result.pool
    if result.status is DynamicPoolEvaluationStatus.CREATED:
        work.repository.append_pool(
            pool,
            claim=_claim(work.request),
            expected_previous_pool_id=(
                None if previous_pool is None else previous_pool.pool_id
            ),
        )
    work.pool = pool
    return _state_artifact(
        StateResearchStage.DYNAMIC_POOL,
        pool.pool_id,
        pool.pool_hash,
        pool.available_at,
        pool.reason_codes,
    )


def _candidate_stage(
    work: _StateWork, context: StateResearchStageContext
) -> StateResearchStageArtifact:
    if work.pool is None or work.market is None or work.capital is None:
        work.final_candidates = _block_candidates_without_pool(work.candidates)
        artifact = _insufficient_stage(
            work,
            StateResearchStage.CANDIDATE,
            ("DYNAMIC_POOL",),
        )
        work.repository.append_runtime_candidate(
            request=work.request,
            candidate_set=work.final_candidates,
            candidate_stage=artifact,
        )
        return artifact
    final = discover_controlled_candidates(
        inputs=work.research.artifact.inputs,
        static_feature_bundle=work.preparation.static_feature_bundle,
        market_regime=work.research.artifact.market_regime,
        theme_rotation=work.research.artifact.theme_rotation,
        capital_evolution=work.research.artifact.capital_evolution,
        configuration=work.research.artifact.configuration.candidate_discovery,
        code_revision=work.research.artifact.envelope.code_revision,
        dynamic_pool_membership={
            item.symbol: item.included for item in work.pool.members
        },
        dynamic_pool_reference=(work.pool.pool_id, work.pool.pool_hash),
    )
    _assert_selected_execution(
        work,
        StateResearchStage.CANDIDATE,
        final.envelope.model_id,
        final.envelope.model_version,
        final.envelope.configuration_id,
        final.envelope.configuration_hash,
    )
    work.final_candidates = final
    binding = bind_candidate_set(
        candidate_set=final,
        dynamic_pool=work.pool,
        market_regime_state_id=work.market.state.state_id,
        etf_rotation_state_ids=tuple(
            sorted((item.state.state_id for item in work.etfs), key=str)
        ),
        theme_rotation_state_ids=tuple(
            sorted((item.state.state_id for item in work.themes), key=str)
        ),
        capital_state_id=work.capital.state.state_id,
        feature_bundle_id=work.preparation.static_bundle.artifact_id,
        runtime_tick_id=work.request.tick_id,
        available_at=work.pool.available_at,
        as_of_time=work.request.as_of_time,
        rule_version="dynamic-pool-candidate-binding-v1",
        configuration_version="v1",
    )
    work.bound_candidates = binding
    artifact = _state_artifact(
        StateResearchStage.CANDIDATE,
        binding.binding_id,
        binding.binding_hash,
        binding.available_at,
        (
            "DYNAMIC_POOL_APPLIED_TO_CANDIDATE",
            "STATE_BOUND_CANDIDATE_COMPLETED",
        ),
    )
    work.repository.append_runtime_candidate(
        request=work.request,
        candidate_set=final,
        candidate_stage=artifact,
    )
    return artifact


def _constrain_candidates(
    candidates: CandidateSet,
    pool: DynamicStockPoolVersion,
) -> CandidateSet:
    pool_by_symbol = {item.symbol: item for item in pool.members}
    prepared: list[CandidateRecord] = []
    for item in candidates.records:
        member = pool_by_symbol[item.symbol]
        if member.included:
            prepared.append(item)
        else:
            prepared.append(
                replace(
                    item,
                    rank=None,
                    selection_status=CandidateSelectionStatus.REJECTED,
                    reason_codes=tuple(
                        sorted(
                            {
                                *item.reason_codes,
                                *member.exclusion_reasons,
                                "DYNAMIC_POOL_EXCLUDED",
                            }
                        )
                    ),
                )
            )
    ranked = sorted(
        (item for item in prepared if item.rank is not None),
        key=lambda item: item.rank or 0,
    )
    ranks = {item.symbol: index for index, item in enumerate(ranked, start=1)}
    records = tuple(
        sorted(
            (
                replace(item, rank=ranks[item.symbol])
                if item.symbol in ranks
                else item
                for item in prepared
            ),
            key=lambda item: item.symbol,
        )
    )
    reasons = tuple(
        sorted({*candidates.reason_codes, "DYNAMIC_POOL_CANDIDATE_GATE_APPLIED"})
    )
    payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": candidates.minimum_candidate_population,
        "reason_codes": list(reasons),
    }
    envelope = candidates.envelope
    lineage = {
        item_id: item_hash
        for item_id, item_hash in zip(
            envelope.input_artifact_ids,
            envelope.input_content_hashes,
            strict=True,
        )
    }
    lineage[pool.pool_id] = pool.pool_hash
    result_envelope = ArtifactEnvelope.create(
        # Preserve the Controlled Candidate contract consumed by the canonical
        # intraday overlay while adding the Dynamic Pool to immutable inputs.
        artifact_type="CONTROLLED_CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=envelope.decision_date,
        decision_time=envelope.decision_time,
        created_at=envelope.created_at,
        code_revision=envelope.code_revision,
        configuration_id=envelope.configuration_id,
        configuration_hash=envelope.configuration_hash,
        source_manifest_id=envelope.source_manifest_id,
        source_manifest_hash=envelope.source_manifest_hash,
        input_artifact_ids=tuple(lineage),
        input_content_hashes=tuple(lineage.values()),
        model_id=envelope.model_id,
        model_version=envelope.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=(
            "RESEARCH_READY"
            if any(
                item.selection_status is CandidateSelectionStatus.SELECTED
                for item in records
            )
            else "RESEARCH_BLOCKED"
        ),
        reason_codes=reasons,
        limitations=envelope.limitations,
    )
    return CandidateSet(
        envelope=result_envelope,
        records=records,
        minimum_candidate_population=candidates.minimum_candidate_population,
        reason_codes=reasons,
    )


def _block_candidates_without_pool(candidates: CandidateSet) -> CandidateSet:
    records = tuple(
        replace(
            item,
            rank=None,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=tuple(
                sorted(
                    {
                        *item.reason_codes,
                        "DYNAMIC_POOL_DATA_INSUFFICIENT",
                        "UPSTREAM_STATE_DATA_INSUFFICIENT",
                    }
                )
            ),
        )
        for item in candidates.records
    )
    reasons = tuple(
        sorted(
            {
                *candidates.reason_codes,
                "DYNAMIC_POOL_DATA_INSUFFICIENT",
                "UPSTREAM_STATE_DATA_INSUFFICIENT",
            }
        )
    )
    payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": candidates.minimum_candidate_population,
        "reason_codes": list(reasons),
    }
    envelope = candidates.envelope
    blocked_envelope = ArtifactEnvelope.create(
        artifact_type="STATE_BLOCKED_CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=envelope.decision_date,
        decision_time=envelope.decision_time,
        created_at=envelope.created_at,
        code_revision=envelope.code_revision,
        configuration_id=envelope.configuration_id,
        configuration_hash=envelope.configuration_hash,
        source_manifest_id=envelope.source_manifest_id,
        source_manifest_hash=envelope.source_manifest_hash,
        input_artifact_ids=envelope.input_artifact_ids,
        input_content_hashes=envelope.input_content_hashes,
        model_id=envelope.model_id,
        model_version=envelope.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_BLOCKED",
        reason_codes=reasons,
        limitations=envelope.limitations,
    )
    return CandidateSet(
        envelope=blocked_envelope,
        records=records,
        minimum_candidate_population=candidates.minimum_candidate_population,
        reason_codes=reasons,
    )


def _state_scope(work: _StateWork, logical_scope: str) -> str:
    """Partition mutable State heads by the owning Continuous Operation."""

    return f"{work.request.run_id}:{logical_scope}"


def _state_lineage(
    payload: Mapping[str, Any],
    created_at: datetime,
) -> StateLineage:
    lineage = _mapping(payload, "lineage")
    return StateLineage.from_canonical_dict(
        {**lineage, "created_at": canonical_datetime(created_at)}
    )


def _previous_market(
    work: _StateWork,
    logical_scope: str,
) -> StatefulMarketRegime | None:
    stored = work.repository.read_current_state(
        StateDomain.MARKET_REGIME,
        _state_scope(work, logical_scope),
    )
    if stored is None:
        return None
    state_id, state_hash, payload, created_at = stored
    _schema(payload, "stateful_market_regime_state/v1")
    return StatefulMarketRegime(
        state_id=state_id,
        state_hash=state_hash,
        previous_state_id=_optional_artifact_id(payload["previous_state_id"]),
        previous_state=_optional_enum(MarketRegimeState, payload["previous_state"]),
        proposed_state=MarketRegimeState(str(payload["proposed_state"])),
        effective_state=MarketRegimeState(str(payload["effective_state"])),
        state_entered_at=parse_canonical_datetime(
            "state_entered_at", payload["state_entered_at"]
        ),
        state_duration_seconds=_integer(payload["state_duration_seconds"]),
        observation_count=_integer(payload["observation_count"]),
        confirmation_count=_integer(payload["confirmation_count"]),
        enter_threshold=Decimal(str(payload["enter_threshold"])),
        exit_threshold=Decimal(str(payload["exit_threshold"])),
        minimum_dwell_seconds=_integer(payload["minimum_dwell_seconds"]),
        hysteresis=Decimal(str(payload["hysteresis"])),
        data_coverage=Decimal(str(payload["data_coverage"])),
        missing_evidence=_strings(payload["missing_evidence"]),
        counter_evidence=_strings(payload["counter_evidence"]),
        reason_codes=_strings(payload["reason_codes"]),
        observation_id=ArtifactId(str(payload["observation_id"])),
        lineage=_state_lineage(payload, created_at),
        transitioned=_boolean(payload["transitioned"]),
    )


def _previous_etf(
    work: _StateWork,
    etf_id: str,
) -> StatefulEtfRotation | None:
    stored = work.repository.read_current_state(
        StateDomain.ETF_ROTATION,
        _state_scope(work, etf_id),
    )
    if stored is None:
        return None
    state_id, state_hash, payload, created_at = stored
    _schema(payload, "etf_rotation_state/v1")
    return StatefulEtfRotation(
        state_id=state_id,
        state_hash=state_hash,
        etf_id=str(payload["etf_id"]),
        previous_state_id=_optional_artifact_id(payload["previous_state_id"]),
        previous_state=_optional_enum(EtfRotationState, payload["previous_state"]),
        proposed_state=EtfRotationState(str(payload["proposed_state"])),
        effective_state=EtfRotationState(str(payload["effective_state"])),
        state_entered_at=parse_canonical_datetime(
            "state_entered_at", payload["state_entered_at"]
        ),
        state_duration_seconds=_integer(payload["state_duration_seconds"]),
        observation_count=_integer(payload["observation_count"]),
        confirmation_count=_integer(payload["confirmation_count"]),
        enter_threshold=Decimal(str(payload["enter_threshold"])),
        exit_threshold=Decimal(str(payload["exit_threshold"])),
        minimum_dwell_seconds=_integer(payload["minimum_dwell_seconds"]),
        hysteresis=Decimal(str(payload["hysteresis"])),
        rotation_score=Decimal(str(payload["rotation_score"])),
        data_coverage=Decimal(str(payload["data_coverage"])),
        missing_evidence=_strings(payload["missing_evidence"]),
        counter_evidence=_strings(payload["counter_evidence"]),
        reason_codes=_strings(payload["reason_codes"]),
        observation_id=ArtifactId(str(payload["observation_id"])),
        lineage=_state_lineage(payload, created_at),
        transitioned=_boolean(payload["transitioned"]),
    )


def _previous_theme(
    work: _StateWork,
    theme_id: str,
) -> StatefulThemeRotation | None:
    stored = work.repository.read_current_state(
        StateDomain.THEME_ROTATION,
        _state_scope(work, theme_id),
    )
    if stored is None:
        return None
    state_id, state_hash, payload, created_at = stored
    _schema(payload, "theme_rotation_state/v1")
    return StatefulThemeRotation(
        state_id=state_id,
        state_hash=state_hash,
        theme_id=str(payload["theme_id"]),
        theme_mapping_id=ArtifactId(str(payload["theme_mapping_id"])),
        theme_mapping_version=str(payload["theme_mapping_version"]),
        proxy_etf_ids=_strings(payload["proxy_etf_ids"]),
        etf_rotation_state_ids=_artifact_ids(payload["etf_rotation_state_ids"]),
        previous_state_id=_optional_artifact_id(payload["previous_state_id"]),
        previous_state=_optional_enum(ThemeRotationState, payload["previous_state"]),
        proposed_state=ThemeRotationState(str(payload["proposed_state"])),
        effective_state=ThemeRotationState(str(payload["effective_state"])),
        state_entered_at=parse_canonical_datetime(
            "state_entered_at", payload["state_entered_at"]
        ),
        state_duration_seconds=_integer(payload["state_duration_seconds"]),
        observation_count=_integer(payload["observation_count"]),
        confirmation_count=_integer(payload["confirmation_count"]),
        enter_threshold=Decimal(str(payload["enter_threshold"])),
        exit_threshold=Decimal(str(payload["exit_threshold"])),
        minimum_dwell_seconds=_integer(payload["minimum_dwell_seconds"]),
        hysteresis=Decimal(str(payload["hysteresis"])),
        rotation_score=Decimal(str(payload["rotation_score"])),
        data_coverage=Decimal(str(payload["data_coverage"])),
        missing_evidence=_strings(payload["missing_evidence"]),
        counter_evidence=_strings(payload["counter_evidence"]),
        reason_codes=_strings(payload["reason_codes"]),
        observation_id=ArtifactId(str(payload["observation_id"])),
        lineage=_state_lineage(payload, created_at),
        transitioned=_boolean(payload["transitioned"]),
    )


def _previous_capital(
    work: _StateWork,
    logical_scope: str,
) -> StatefulCapitalState | None:
    stored = work.repository.read_current_state(
        StateDomain.CAPITAL_STATE,
        _state_scope(work, logical_scope),
    )
    if stored is None:
        return None
    state_id, state_hash, payload, created_at = stored
    _schema(payload, "capital_state/v1")
    return StatefulCapitalState(
        state_id=state_id,
        state_hash=state_hash,
        scope_id=str(payload["scope_id"]),
        previous_state_id=_optional_artifact_id(payload["previous_state_id"]),
        previous_state=_optional_enum(CapitalState, payload["previous_state"]),
        proposed_state=CapitalState(str(payload["proposed_state"])),
        effective_state=CapitalState(str(payload["effective_state"])),
        state_entered_at=parse_canonical_datetime(
            "state_entered_at", payload["state_entered_at"]
        ),
        state_duration_seconds=_integer(payload["state_duration_seconds"]),
        observation_count=_integer(payload["observation_count"]),
        confirmation_count=_integer(payload["confirmation_count"]),
        enter_threshold=Decimal(str(payload["enter_threshold"])),
        exit_threshold=Decimal(str(payload["exit_threshold"])),
        minimum_dwell_seconds=_integer(payload["minimum_dwell_seconds"]),
        hysteresis=Decimal(str(payload["hysteresis"])),
        data_coverage=Decimal(str(payload["data_coverage"])),
        uncertainty=Decimal(str(payload["uncertainty"])),
        missing_evidence=_strings(payload["missing_evidence"]),
        counter_evidence=_strings(payload["counter_evidence"]),
        reason_codes=_strings(payload["reason_codes"]),
        observation_id=ArtifactId(str(payload["observation_id"])),
        lineage=_state_lineage(payload, created_at),
        transitioned=_boolean(payload["transitioned"]),
    )


def _previous_pool(work: _StateWork) -> DynamicStockPoolVersion | None:
    pool_id = work.repository.latest_pool_id(work.request.run_id)
    if pool_id is None:
        return None
    payload = work.repository.read_pool(pool_id)
    _schema(payload, "dynamic_stock_pool/v1")
    created_at = parse_canonical_datetime("created_at", payload["created_at"])
    return DynamicStockPoolVersion(
        pool_id=pool_id,
        pool_hash=str(payload["pool_hash"]),
        previous_pool_id=_optional_artifact_id(payload["previous_pool_id"]),
        pool_version=_integer(payload["pool_version"]),
        effective_at=parse_canonical_datetime("effective_at", payload["effective_at"]),
        available_at=parse_canonical_datetime("available_at", payload["available_at"]),
        decision_time=parse_canonical_datetime("decision_time", payload["decision_time"]),
        market_regime_state_id=ArtifactId(str(payload["market_regime_state_id"])),
        etf_rotation_state_ids=_artifact_ids(payload["etf_rotation_state_ids"]),
        theme_rotation_state_ids=_artifact_ids(payload["theme_rotation_state_ids"]),
        capital_state_id=ArtifactId(str(payload["capital_state_id"])),
        included_symbols=_strings(payload["included_symbols"]),
        excluded_symbols=_strings(payload["excluded_symbols"]),
        added_symbols=_strings(payload["added_symbols"]),
        removed_symbols=_strings(payload["removed_symbols"]),
        members=tuple(
            _pool_member(_mapping(item, "member"))
            for item in _sequence(payload["members"], "members")
        ),
        missing_evidence=_strings(payload["missing_evidence"]),
        reason_codes=_strings(payload["reason_codes"]),
        configuration_version=str(payload["configuration_version"]),
        configuration_hash=str(payload["configuration_hash"]),
        source_artifact_ids=_artifact_ids(payload["source_artifact_ids"]),
        runtime_tick_id=ArtifactId(str(payload["runtime_tick_id"])),
        material_state_hash=str(payload["material_state_hash"]),
        lineage=_state_lineage(payload, created_at),
    )


def _pool_member(payload: Mapping[str, Any]) -> DynamicPoolMember:
    rank = payload["rank"]
    return DynamicPoolMember(
        symbol=str(payload["symbol"]),
        included=_boolean(payload["included"]),
        gate_result=str(payload["gate_result"]),
        score=Decimal(str(payload["score"])),
        rank=None if rank is None else _integer(rank),
        exclusion_reasons=_strings(payload["exclusion_reasons"]),
        eligibility=_boolean(payload["eligibility"]),
        liquidity=Decimal(str(payload["liquidity"])),
        board=str(payload["board"]),
        is_st=_boolean(payload["is_st"]),
        suspended=_boolean(payload["suspended"]),
        listing_age_days=_integer(payload["listing_age_days"]),
        theme_overlap=_strings(payload["theme_overlap"]),
        data_coverage=Decimal(str(payload["data_coverage"])),
        missing_evidence=_strings(payload["missing_evidence"]),
    )


def _schema(payload: Mapping[str, Any], expected: str) -> None:
    if payload.get("schema") != expected:
        raise ValueError(f"unsupported persisted State schema: {payload.get('schema')}")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    values = _sequence(value, "string values")
    if any(not isinstance(item, str) for item in values):
        raise ValueError("string values must contain only text")
    return tuple(values)  # type: ignore[arg-type]


def _artifact_ids(value: object) -> tuple[ArtifactId, ...]:
    return tuple(ArtifactId(item) for item in _strings(value))


def _optional_artifact_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(str(value))


def _optional_enum(enum_type: Any, value: object) -> Any:
    return None if value is None else enum_type(str(value))


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("integer State value is invalid")
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("boolean State value is invalid")
    return value


def _append_evaluation(
    work: _StateWork,
    domain: StateDomain,
    scope_key: str,
    evaluation: object,
) -> None:
    observation = evaluation.observation  # type: ignore[attr-defined]
    state = evaluation.state  # type: ignore[attr-defined]
    transition = evaluation.transition  # type: ignore[attr-defined]
    work.repository.append_state(
        StateArtifactWrite(
            domain=domain,
            scope_key=_state_scope(work, scope_key),
            observation_id=observation.observation_id,
            observation_hash=observation.observation_hash,
            observation_payload=observation.identity_payload(),
            state_id=state.state_id,
            state_hash=state.state_hash,
            previous_state_id=state.previous_state_id,
            effective_state=state.effective_state.value,
            state_payload=state.identity_payload(),
            transition_id=transition.transition_id,
            transition_hash=transition.transition_hash,
            transition_payload=transition.identity_payload(),
            lineage=observation.lineage,
        ),
        claim=_claim(work.request),
        expected_previous_state_id=state.previous_state_id,
    )


def _claim(request: ChildExecutionRequest):
    from market_regime_alpha.application.continuous_research.journal import (
        ClaimedRuntimeTick,
    )

    return ClaimedRuntimeTick(
        run_id=request.run_id,
        tick_id=request.tick_id,
        tick_sequence=request.tick_sequence,
        claim_id=request.claim_id,
        fencing_token=request.fencing_token,
        tick_version=request.tick_version,
        lease_acquired_at=request.lease_acquired_at,
        lease_expires_at=request.lease_expires_at,
        heartbeat_at=request.heartbeat_at,
    )


def _lineage(
    work: _StateWork,
    model_id: ModelId,
    model_version: str,
    configuration: object,
    *,
    available_at: datetime | None = None,
) -> StateLineage:
    config_id = configuration.configuration_id  # type: ignore[attr-defined]
    config_hash = configuration.configuration_hash  # type: ignore[attr-defined]
    source_ids = tuple(
        sorted(
            (
                item.artifact_id
                for item in work.research.artifact.inputs.supplemental_evidence.source_manifest.source_artifacts
            ),
            key=str,
        )
    )
    return StateLineage(
        continuous_operation_id=work.request.run_id,
        runtime_tick_id=work.request.tick_id,
        provider_attempt_ids=(
            ArtifactId(f"provider-attempt:{work.request.provider_attempt_id}"),
        ),
        evidence_ids=(work.request.evidence_commit_id,),
        dataset_id=DatasetId(
            str(work.preparation.daily_dataset.artifact.dataset_id)
        ),
        feature_id=work.preparation.static_bundle.artifact_id,
        source_artifact_ids=source_ids,
        model_id=model_id,
        model_version=model_version,
        configuration_id=config_id,
        configuration_hash=config_hash,
        as_of_time=work.request.as_of_time,
        available_at=available_at or _evidence_available_at(work),
        created_at=work.clock(),
    )


def _state_configuration(cls, work: _StateWork, stage: StateResearchStage):
    receipt = work.receipts[stage]
    if (
        receipt.status is not SelectionStatus.SELECTED
        or receipt.selected_model_id is None
        or receipt.model_slot != GOVERNED_RESEARCH_MODEL_SLOTS[stage]
    ):
        raise ValueError("State model was not selected by Governance")
    # Governance selects and executes the upstream snapshot model.  The
    # hysteresis transition is a separate deterministic, versioned State
    # policy and must not impersonate the selected model configuration.
    policy_name = f"free-data-{stage.value.lower()}-state-transition-v1"
    return cls.create(
        model_id=ModelId(policy_name),
        model_version="v1",
        configuration_id=ArtifactId(
            f"{policy_name}-configuration"
        ),
        configuration_version="v1",
        thresholds=_thresholds(),
    )


def _assert_selected_execution(
    work: _StateWork,
    stage: StateResearchStage,
    model_id: ModelId | None,
    model_version: str | None,
    configuration_id: ArtifactId,
    configuration_hash: str,
) -> None:
    receipt = work.receipts[stage]
    configured: Any = {
        StateResearchStage.MARKET_REGIME: work.research.artifact.configuration.market_regime,
        StateResearchStage.THEME_ROTATION: work.research.artifact.configuration.theme_rotation,
        StateResearchStage.CAPITAL_STATE: work.research.artifact.configuration.capital_evolution,
        StateResearchStage.CANDIDATE: work.research.artifact.configuration.candidate_discovery,
    }[stage]
    if (
        receipt.status is not SelectionStatus.SELECTED
        or receipt.model_slot != GOVERNED_RESEARCH_MODEL_SLOTS[stage]
        or receipt.selected_model_id != model_id
        or configured.model_id != model_id
        or configured.model_version != model_version
        or configured.configuration_id != configuration_id
        or configured.configuration_hash != configuration_hash
    ):
        raise ValueError("State input was not executed by the selected Model/configuration")


def _deterministic_state_configuration(cls, name: str):
    return cls.create(
        model_id=ModelId(name),
        model_version="v1",
        configuration_id=ArtifactId(f"{name}-configuration"),
        configuration_version="v1",
        thresholds=_thresholds(),
    )


def _thresholds() -> TransitionThresholds:
    return TransitionThresholds(
        enter_threshold=Decimal("0.60"),
        exit_threshold=Decimal("0.40"),
        hysteresis=Decimal("0.20"),
        confirmation_count=1,
        minimum_dwell_seconds=0,
        minimum_coverage=Decimal("0.50"),
        missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
    )


def _pool_configuration() -> DynamicPoolConfiguration:
    return DynamicPoolConfiguration.create(
        configuration_id=ArtifactId("free-data-dynamic-pool-policy-v1"),
        configuration_version="v1",
        allowed_etf_states=("LEADING", "STARTING", "STRENGTHENING"),
        allowed_theme_states=("LEADING", "STARTING", "STRENGTHENING"),
        minimum_state_dwell_seconds=0,
        minimum_evidence_coverage=Decimal("0.50"),
        material_change_threshold=Decimal("0.05"),
    )


def _evidence_available_at(work: _StateWork) -> datetime:
    bundle = work.research.artifact.inputs.supplemental_evidence
    return max(
        work.preparation.universe.available_at,
        work.preparation.daily_dataset.artifact.available_at,
        *(item.retrieved_at.value for item in bundle.source_manifest.source_artifacts),
    )


def _state_artifact(
    stage: StateResearchStage,
    artifact_id: ArtifactId,
    artifact_hash: str,
    available_at: datetime,
    reasons: tuple[str, ...],
    *,
    status: StateResearchStageStatus = StateResearchStageStatus.COMPLETED,
) -> StateResearchStageArtifact:
    return StateResearchStageArtifact(
        stage=stage,
        artifact_id=artifact_id,
        artifact_hash=artifact_hash,
        available_at=available_at,
        data_eligibility=DataEligibility.EXPLORATORY,
        reason_codes=tuple(sorted(set(reasons))),
        status=status,
    )


def _bundle_artifact(
    stage: StateResearchStage,
    items: tuple[tuple[ArtifactId, str], ...],
    available_at: datetime,
    reasons: tuple[str, ...],
) -> StateResearchStageArtifact:
    digest = canonical_hash(
        {
            "stage": stage.value,
            "artifacts": [
                {"artifact_id": str(item), "content_hash": item_hash}
                for item, item_hash in sorted(items, key=lambda value: str(value[0]))
            ],
        }
    )
    return _state_artifact(
        stage,
        ArtifactId(f"state-stage-{stage.value.lower()}:{digest[7:]}"),
        digest,
        available_at,
        reasons,
    )


def _insufficient_stage(
    work: _StateWork,
    stage: StateResearchStage,
    missing: tuple[str, ...],
) -> StateResearchStageArtifact:
    digest = canonical_hash(
        {
            "stage": stage.value,
            "status": "DATA_INSUFFICIENT",
            "missing_evidence": sorted(set(missing)),
            "evidence_commit_id": str(work.request.evidence_commit_id),
        }
    )
    return _state_artifact(
        stage,
        ArtifactId(f"state-stage-insufficient:{digest[7:]}"),
        digest,
        _evidence_available_at(work),
        tuple(
            sorted(
                {
                    f"{stage.value}_DATA_INSUFFICIENT",
                    *(f"MISSING_{item}" for item in missing),
                }
            )
        ),
        status=StateResearchStageStatus.DATA_INSUFFICIENT,
    )


def _unit_decimal(value: float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return max(Decimal("0"), min(Decimal("1"), Decimal(str(value))))


def _signed_to_unit_decimal(value: float) -> Decimal:
    return _unit_decimal((value + 1.0) / 2.0)


def _signed_mean(values) -> Decimal:
    present = tuple(float(value) for value in values if value is not None)
    if not present:
        return Decimal("0")
    return max(Decimal("-1"), min(Decimal("1"), Decimal(str(fmean(present)))))


def _unit_mean(values) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), _signed_mean(values)))


__all__ = ["CanonicalFreeDataStateCoordinator"]
