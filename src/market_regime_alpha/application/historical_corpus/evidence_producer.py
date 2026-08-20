"""Owner-resolved corpus aggregation over the existing Ablation runtime."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
)
from market_regime_alpha.application.historical_corpus.decision_materializer import (
    NORMALIZED_DATASET_KIND,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    EvidenceMetricStatus,
    HistoricalEvidenceKind,
    HistoricalEvidenceMetric,
    HistoricalResearchEvidence,
    MetricAssumptionStatus,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GOLDEN_LOOP_SCORING_CONTRACT,
    GoldenLoopScoringContract,
    GoldenLoopSessionEvaluation,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_validation.ablation import (
    AblationMetrics,
    AblationObservation,
    AblationProtocol,
    AblationVariant,
    AblationVariantKind,
    AlphaAblationSuite,
    PrecomputedAblationObservation,
    run_precomputed_alpha_ablation_suite,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


_SEQUENCE = (
    AblationVariantKind.PRICE_ONLY,
    AblationVariantKind.PRICE_VOLUME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL,
    AblationVariantKind.THROUGH_DYNAMIC_POOL,
    AblationVariantKind.THROUGH_CANDIDATE_RANKING,
    AblationVariantKind.THROUGH_SIGNAL,
    AblationVariantKind.THROUGH_FORECAST,
)
_FACTOR_MAP = {
    "price": FactorFamily.PRICE,
    "volume": FactorFamily.VOLUME,
    "market_regime": FactorFamily.MARKET_REGIME,
    "etf": FactorFamily.ETF,
    "theme": FactorFamily.THEME,
    "capital": FactorFamily.CAPITAL,
    "dynamic_pool": FactorFamily.DYNAMIC_POOL,
    "candidate": FactorFamily.CANDIDATE,
    "signal": FactorFamily.SIGNAL,
    "forecast": FactorFamily.FORECAST,
}
_INCREMENTAL_FACTOR_BY_VARIANT = {
    kind.value.lower(): family
    for kind, family in (
        (AblationVariantKind.PRICE_ONLY, FactorFamily.PRICE),
        (AblationVariantKind.PRICE_VOLUME, FactorFamily.VOLUME),
        (
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME,
            FactorFamily.MARKET_REGIME,
        ),
        (AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF, FactorFamily.ETF),
        (
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME,
            FactorFamily.THEME,
        ),
        (
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL,
            FactorFamily.CAPITAL,
        ),
        (AblationVariantKind.THROUGH_DYNAMIC_POOL, FactorFamily.DYNAMIC_POOL),
        (AblationVariantKind.THROUGH_CANDIDATE_RANKING, FactorFamily.CANDIDATE),
        (AblationVariantKind.THROUGH_SIGNAL, FactorFamily.SIGNAL),
        (AblationVariantKind.THROUGH_FORECAST, FactorFamily.FORECAST),
    )
}


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceProductionResult:
    run_id: ArtifactId
    observation_count: int
    suite: AlphaAblationSuite
    evidence: tuple[HistoricalResearchEvidence, ...]


@dataclass(frozen=True, slots=True)
class _StreamingPanelSummary:
    observation_count: int
    missing_target_count: int
    session_count: int
    symbol_count: int
    maximum_session_observations: int
    component_batch_size: int
    factor_coverage: Mapping[FactorFamily, int]
    target_status_counts: Mapping[str, int]
    signal_state_counts: Mapping[str, int]
    signal_confirmation_counts: Mapping[str, int]
    signal_reason_counts: Mapping[str, int]
    forecast_status_counts: Mapping[str, int]
    forecast_reason_counts: Mapping[str, int]
    forecast_usable_sample_total: int
    forecast_usable_sample_maximum: int
    forecast_excluded_sample_total: int
    period_observation_counts: Mapping[str, int]


class HistoricalEvidenceProducer:
    """Resolve immutable owners, run frozen research science, persist findings."""

    def __init__(
        self,
        *,
        journal: PostgresHistoricalResearchJournal,
        corpus_repository: PostgresHistoricalCorpusRepository,
        component_repository: PostgresHistoricalMaterializationRepository,
        evidence_repository: PostgresHistoricalEvidenceRepository,
    ) -> None:
        self._journal = journal
        self._corpus = corpus_repository
        self._components = component_repository
        self._evidence = evidence_repository

    def produce(self, *, run_id: ArtifactId) -> HistoricalEvidenceProductionResult:
        snapshot = self._journal.get_run(run_id)
        if snapshot.status not in {
            HistoricalRunStatus.COMPLETE,
            HistoricalRunStatus.COMPLETE_WITH_BLOCKS,
        }:
            raise ValueError("Historical Evidence requires a terminal corpus run")
        panel_references = self._components.list_references_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        )
        evaluation_references = self._components.list_references_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.RESEARCH_EVALUATION,
        )
        outcome_references = self._components.list_references_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.OUTCOME,
        )
        if not panel_references:
            raise ValueError("Historical Evidence requires Research Panel owners")
        if not evaluation_references:
            raise ValueError(
                "Historical Evidence V2 requires canonical Research Evaluation owners; "
                "legacy V1 Evidence remains immutable and cannot be regenerated"
            )
        owner = self._normalized_owner(snapshot.command.configuration_references)
        created_at = max(
            owner.created_at,
            self._components.maximum_materialized_at(
                run_id=run_id,
                component_kinds=tuple(
                    sorted(
                        (
                            HistoricalComponentKind.OUTCOME,
                            HistoricalComponentKind.RESEARCH_PANEL,
                            HistoricalComponentKind.RESEARCH_EVALUATION,
                        ),
                        key=lambda item: item.value,
                    )
                ),
            ),
        )
        panel_summary = _streaming_panel_summary(
            self._components,
            run_id=run_id,
            component_batch_size=4,
        )
        if panel_summary.observation_count == 0:
            raise ValueError("Historical Evidence has no estimable Target observations")
        factor_coverage = panel_summary.factor_coverage
        variants = tuple(AblationVariant.standard(item) for item in _SEQUENCE)
        contract = GoldenLoopScoringContract.create_v2()
        protocol = AblationProtocol.create(
            protocol_version="golden-loop-cumulative-chain-v2",
            variants=variants,
            comparison_sequence=tuple(item.value.lower() for item in _SEQUENCE),
            top_k=contract.top_k,
            scoring_contract=contract.scoring_contract,
            created_at=created_at,
        )
        evaluation_components = tuple(
            component
            for batch in self._components.iter_for_run(
                run_id=run_id,
                component_kind=HistoricalComponentKind.RESEARCH_EVALUATION,
                batch_size=4,
            )
            for component in batch
        )
        evaluations = tuple(
            GoldenLoopSessionEvaluation.from_canonical_dict(component.payload)
            for component in evaluation_components
        )
        if len(evaluation_components) != panel_summary.session_count:
            raise ValueError(
                "Historical Evidence requires one canonical Evaluation per session"
            )
        if any(
            evaluation.scoring_contract != contract
            or evaluation.source_references != component.source_references
            for component, evaluation in zip(
                evaluation_components,
                evaluations,
                strict=True,
            )
        ):
            raise ValueError("Historical Evaluation contract/source projection mismatch")
        evaluation_reference = _evaluation_set_reference(evaluation_references)
        suite = run_precomputed_alpha_ablation_suite(
            protocol=protocol,
            panel_reference=evaluation_reference,
            evaluation_sessions=(
                _precomputed_evaluation_session(component, evaluation)
                for component, evaluation in zip(
                    evaluation_components,
                    evaluations,
                    strict=True,
                )
            ),
            created_at=created_at,
        )
        sources = tuple(
            sorted(
                {
                    *panel_references,
                    *evaluation_references,
                    *outcome_references,
                    owner.reference,
                    *(source for item in evaluations for source in item.source_references),
                },
                key=_reference_key,
            )
        )
        experiment = snapshot.command.experiment_definition_reference
        ablation_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.ALPHA_ABLATION,
            research_question=("Under the frozen tie-aware V2 scorer, which research layers add incremental T+1 10:30 explanatory value?"),
            classification=_ablation_finding(suite),
            rationale=_ablation_rationale(suite),
            source_references=sources,
            metrics=_ablation_metrics(suite, factor_coverage),
            payload={
                **_suite_payload(
                    suite,
                    panel_summary.missing_target_count,
                    factor_coverage,
                ),
                "aggregation_runtime": {
                    "mode": "CANONICAL_RESEARCH_EVALUATION_AGGREGATION_V2",
                    "component_batch_size": panel_summary.component_batch_size,
                    "maximum_session_observations": panel_summary.maximum_session_observations,
                    "whole_run_panel_materialized": False,
                    "whole_run_observation_graph_materialized": False,
                    "ranking_recomputed_by_evidence_producer": False,
                    "portfolio_recomputed_by_evidence_producer": False,
                },
            },
            created_at=created_at,
            limitations=(
                "CUMULATIVE_SCORING_CONTRACT_FROZEN_NOT_TUNED",
                "MARKET_CAP_AND_INDUSTRY_NOT_ESTIMABLE_WHEN_PROVIDER_OMITS_FACTS",
                "UNOBSERVED_LAYER_LIFT_NOT_ESTIMABLE",
            ),
        )
        strategy_metrics = _canonical_strategy_metrics(evaluations)
        strategy_status_counts = dict(
            sorted(Counter(item.portfolio_status for item in evaluations).items())
        )
        strategy_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.STRATEGY_ECONOMICS,
            research_question=(
                "Do canonical Strategy proposals admitted by Cross-Strategy Portfolio "
                "retain attributable net economic value?"
            ),
            classification=ResearchFinding.NOT_ESTIMABLE,
            rationale=(
                "Canonical Portfolio sessions were owner-resolved, but no Strategy "
                "Path Outcome supplied attributable gross/cost/net economics."
            ),
            source_references=sources,
            metrics=strategy_metrics,
            payload={
                "portfolio_status_counts": strategy_status_counts,
                "canonical_cycle_portfolio_outcome_bound": True,
                "strategy_path_outcome_count": 0,
                "actual_fill_authority": False,
            },
            created_at=created_at,
            limitations=(
                "CANONICAL_STRATEGY_ECONOMICS_NOT_ESTIMABLE",
                "HISTORICAL_SHADOW_SIMULATION_NOT_OBSERVED_FILL",
            ),
        )
        performance_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.PORTFOLIO_PERFORMANCE,
            research_question=("Does the canonical Cross-Strategy Portfolio retain attributable net value after cost?"),
            classification=ResearchFinding.NOT_ESTIMABLE,
            rationale=(
                "Research top-k diagnostics are not Portfolio Authority; canonical "
                "Portfolio performance remains NOT_ESTIMABLE without Strategy Path Outcomes."
            ),
            source_references=sources,
            metrics=strategy_metrics,
            payload={
                "portfolio_status_counts": strategy_status_counts,
                "research_top_k_is_portfolio_authority": False,
                "actual_fill_authority": False,
            },
            created_at=created_at,
            limitations=("CANONICAL_PORTFOLIO_PERFORMANCE_NOT_ESTIMABLE",),
        )
        summary_metrics = _summary_metrics(
            owner=owner,
            panel_owner_count=len(panel_references),
            observation_count=panel_summary.observation_count,
            symbol_count=panel_summary.symbol_count,
            panel_missing=panel_summary.missing_target_count,
            panel_summary=panel_summary,
        )
        corpus_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.CORPUS_SUMMARY,
            research_question="What exact coverage and missingness does this corpus contain?",
            classification=ResearchFinding.INCONCLUSIVE,
            rationale=("Corpus summary is descriptive evidence and does not classify Alpha."),
            source_references=sources,
            metrics=summary_metrics,
            payload={
                "owner": dict(owner.manifest),
                "panel_owner_count": len(panel_references),
                "outcome_owner_count": len(outcome_references),
                "evaluation_owner_count": len(evaluation_references),
                "excluded_missing_target_rows": panel_summary.missing_target_count,
                "diagnostics": _diagnostic_payload(panel_summary),
                "aggregation_runtime": {
                    "component_batch_size": panel_summary.component_batch_size,
                    "maximum_session_observations": panel_summary.maximum_session_observations,
                    "whole_run_panel_materialized": False,
                },
            },
            created_at=created_at,
        )
        superseded = tuple(
            item
            for item in snapshot.command.configuration_references
            if (
                item.artifact_kind.startswith("METHODOLOGY_INVALIDATED_")
                or (
                    item.artifact_kind.startswith("HISTORICAL_")
                    and item.artifact_kind.endswith("_EVIDENCE")
                )
            )
        )
        methodology_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.METHODOLOGY_ASSESSMENT,
            research_question=(
                "Which V1 Phase E2/E3 findings are invalidated by identity-based tie handling?"
            ),
            classification=ResearchFinding.INCONCLUSIVE,
            rationale=(
                "V1 factor ranks used observation identity inside equal-value ties; "
                "affected ranking and incremental-lift claims are methodology-invalidated, "
                "while immutable V1 Evidence is retained for audit."
            ),
            source_references=tuple(
                sorted({*sources, *superseded}, key=_reference_key)
            ),
            metrics=(
                HistoricalEvidenceMetric(
                    variant_id="methodology_v1",
                    slice_kind="ALL",
                    slice_value="ALL",
                    metric_name="superseded_evidence_count",
                    metric_value=Decimal(len(superseded)),
                    metric_status=EvidenceMetricStatus.AVAILABLE,
                    assumption_status=MetricAssumptionStatus.NOT_APPLICABLE,
                ),
            ),
            payload={
                "status": "METHODOLOGY_INVALIDATED",
                "invalidated_scoring_contract": "WITHIN_SESSION_FACTOR_PERCENTILE_MEAN_V1",
                "replacement_scoring_contract": GOLDEN_LOOP_SCORING_CONTRACT,
                "superseded_references": [
                    item.to_canonical_dict() for item in superseded
                ],
                "v1_evidence_mutated": False,
                "scope": (
                    "Only conclusions dependent on identity-broken ranking, top-k "
                    "selection, or incremental lift are superseded."
                ),
            },
            created_at=created_at,
            limitations=(
                "METHODOLOGY_INVALIDATION_IS_NOT_NEW_ALPHA_EVIDENCE",
                "V1_EVIDENCE_RETAINED_IMMUTABLY",
            ),
        )
        evidence = tuple(
            self._evidence.put(item)
            for item in (
                corpus_evidence,
                ablation_evidence,
                strategy_evidence,
                performance_evidence,
                methodology_evidence,
            )
        )
        return HistoricalEvidenceProductionResult(
            run_id=run_id,
            observation_count=panel_summary.observation_count,
            suite=suite,
            evidence=evidence,
        )

    def _normalized_owner(
        self,
        references: tuple[ValidationArtifactReference, ...],
    ) -> HistoricalPackageIndex:
        matches = tuple(item for item in references if item.artifact_kind == NORMALIZED_DATASET_KIND)
        if len(matches) != 1:
            raise ValueError("Historical Evidence requires one normalized Dataset owner")
        return self._corpus.open_index(matches[0])


def _precomputed_evaluation_session(
    component: HistoricalSessionComponent,
    evaluation: GoldenLoopSessionEvaluation,
) -> Mapping[str, tuple[PrecomputedAblationObservation, ...]]:
    result: dict[str, tuple[PrecomputedAblationObservation, ...]] = {}
    for variant in evaluation.variants:
        variant_id = str(variant["variant_id"])
        rows = _objects(variant.get("rows"), "evaluation variant rows")
        result[variant_id] = tuple(
            PrecomputedAblationObservation(
                observation=_evaluation_observation(component, row),
                score=Decimal(str(row["score"])),
                top_weight=Decimal(str(row["top_weight"])),
                bottom_weight=Decimal(str(row["bottom_weight"])),
            )
            for row in rows
        )
    return result


def _evaluation_observation(
    component: HistoricalSessionComponent,
    row: Mapping[str, Any],
) -> AblationObservation:
    slices = _mapping(row.get("slices"), "evaluation slices")
    return AblationObservation(
        observation_id=str(row["observation_id"]),
        session_key=component.trading_date.isoformat(),
        symbol=str(row["symbol"]),
        score=Decimal(str(row["score"])),
        realized_return=Decimal(str(row["realized_return"])),
        mfe=_optional_decimal(row.get("mfe")),
        mae=_optional_decimal(row.get("mae")),
        selected=bool(row.get("selected")),
        previous_selected=False,
        factor_values=(),
        cost_return=Decimal(str(row["cost_return"])),
        market_regime=str(slices.get("market_regime", "NOT_ESTIMABLE")),
        liquidity_bucket=str(slices.get("liquidity", "NOT_ESTIMABLE")),
        market_cap_bucket=str(slices.get("market_cap", "NOT_ESTIMABLE")),
        volatility_bucket=str(slices.get("volatility", "NOT_ESTIMABLE")),
        theme=str(slices.get("theme", "NOT_ESTIMABLE")),
        industry=str(slices.get("industry", "NOT_ESTIMABLE")),
        trading_date=component.trading_date,
    )


def _canonical_strategy_metrics(
    evaluations: tuple[GoldenLoopSessionEvaluation, ...],
) -> tuple[HistoricalEvidenceMetric, ...]:
    session_count = len(evaluations)
    no_action_count = sum(
        item.portfolio_status == "NO_ACTION" for item in evaluations
    )
    line_count = sum(item.portfolio_line_count for item in evaluations)
    available = (
        ("session_count", Decimal(session_count)),
        ("no_action_session_count", Decimal(no_action_count)),
        ("portfolio_line_count", Decimal(line_count)),
    )
    metrics = [
        HistoricalEvidenceMetric(
            variant_id="canonical_cross_strategy_portfolio",
            slice_kind="ALL",
            slice_value="ALL",
            metric_name=name,
            metric_value=value,
            metric_status=EvidenceMetricStatus.AVAILABLE,
            assumption_status=MetricAssumptionStatus.EMPIRICAL,
        )
        for name, value in available
    ]
    metrics.extend(
        HistoricalEvidenceMetric(
            variant_id="canonical_cross_strategy_portfolio",
            slice_kind="ALL",
            slice_value="ALL",
            metric_name=name,
            metric_value=None,
            metric_status=EvidenceMetricStatus.NOT_ESTIMABLE,
            assumption_status=(
                MetricAssumptionStatus.ENGINEERING_ASSUMPTION
                if name in {"cost_return", "net_return"}
                else MetricAssumptionStatus.EMPIRICAL
            ),
        )
        for name in (
            "gross_return",
            "cost_return",
            "net_return",
            "turnover",
            "max_drawdown",
        )
    )
    return tuple(metrics)


def _streaming_panel_summary(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    component_batch_size: int,
) -> _StreamingPanelSummary:
    observation_count = 0
    missing = 0
    session_count = 0
    maximum_session_observations = 0
    symbols: set[str] = set()
    coverage = {family: 0 for family in _INCREMENTAL_FACTOR_BY_VARIANT.values()}
    target_status_counts: Counter[str] = Counter()
    signal_state_counts: Counter[str] = Counter()
    signal_confirmation_counts: Counter[str] = Counter()
    signal_reason_counts: Counter[str] = Counter()
    forecast_status_counts: Counter[str] = Counter()
    forecast_reason_counts: Counter[str] = Counter()
    forecast_usable_sample_total = 0
    forecast_usable_sample_maximum = 0
    forecast_excluded_sample_total = 0
    period_observation_counts: Counter[str] = Counter()
    for batch in repository.iter_for_run(
        run_id=run_id,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        batch_size=component_batch_size,
    ):
        for panel in batch:
            rows = _objects(panel.payload.get("rows"), "panel rows")
            estimable_rows = tuple(
                row
                for row in rows
                if _optional_decimal(row.get("target_return")) is not None
            )
            session_count += 1
            observation_count += len(estimable_rows)
            missing += len(rows) - len(estimable_rows)
            maximum_session_observations = max(
                maximum_session_observations,
                len(estimable_rows),
            )
            for row in rows:
                target_status_counts[str(row.get("target_status", "UNKNOWN"))] += 1
                signal_diagnostic = _mapping(
                    row.get(
                        "signal_diagnostic",
                        {
                            "state": "NOT_RECORDED_LEGACY_PANEL",
                            "confirmation_states": {},
                            "reason_codes": ["SIGNAL_DIAGNOSTIC_NOT_RECORDED"],
                        },
                    ),
                    "signal diagnostic",
                )
                signal_state_counts[str(signal_diagnostic["state"])] += 1
                for name, state in _mapping(
                    signal_diagnostic.get("confirmation_states"),
                    "signal confirmation states",
                ).items():
                    signal_confirmation_counts[f"{name}:{state}"] += 1
                for reason in signal_diagnostic.get("reason_codes", []):
                    signal_reason_counts[str(reason)] += 1
                forecast_diagnostic = _mapping(
                    row.get(
                        "forecast_diagnostic",
                        {
                            "status": "NOT_RECORDED_LEGACY_PANEL",
                            "usable_sample_count": 0,
                            "excluded_sample_count": 0,
                            "reason_codes": ["FORECAST_DIAGNOSTIC_NOT_RECORDED"],
                        },
                    ),
                    "forecast diagnostic",
                )
                forecast_status_counts[str(forecast_diagnostic["status"])] += 1
                usable = int(forecast_diagnostic["usable_sample_count"])
                excluded = int(forecast_diagnostic["excluded_sample_count"])
                forecast_usable_sample_total += usable
                forecast_usable_sample_maximum = max(forecast_usable_sample_maximum, usable)
                forecast_excluded_sample_total += excluded
                for reason in forecast_diagnostic.get("reason_codes", []):
                    forecast_reason_counts[str(reason)] += 1
                period_observation_counts[panel.trading_date.strftime("%Y-%m")] += 1
            for row in estimable_rows:
                symbols.add(str(row["symbol"]))
                factors = _mapping(row.get("factor_values"), "factor values")
                for name, family in _FACTOR_MAP.items():
                    if (
                        family in coverage
                        and _optional_decimal(factors.get(name)) is not None
                    ):
                        coverage[family] += 1
    return _StreamingPanelSummary(
        observation_count=observation_count,
        missing_target_count=missing,
        session_count=session_count,
        symbol_count=len(symbols),
        maximum_session_observations=maximum_session_observations,
        component_batch_size=component_batch_size,
        factor_coverage=coverage,
        target_status_counts=dict(sorted(target_status_counts.items())),
        signal_state_counts=dict(sorted(signal_state_counts.items())),
        signal_confirmation_counts=dict(sorted(signal_confirmation_counts.items())),
        signal_reason_counts=dict(sorted(signal_reason_counts.items())),
        forecast_status_counts=dict(sorted(forecast_status_counts.items())),
        forecast_reason_counts=dict(sorted(forecast_reason_counts.items())),
        forecast_usable_sample_total=forecast_usable_sample_total,
        forecast_usable_sample_maximum=forecast_usable_sample_maximum,
        forecast_excluded_sample_total=forecast_excluded_sample_total,
        period_observation_counts=dict(sorted(period_observation_counts.items())),
    )


def _evaluation_set_reference(
    evaluations: tuple[ValidationArtifactReference, ...],
) -> ValidationArtifactReference:
    payload = {"evaluations": [item.to_canonical_dict() for item in evaluations]}
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "HISTORICAL_RESEARCH_EVALUATION_SET_BINDING",
        ArtifactId(f"historical-evaluation-set-{digest[7:31]}"),
        digest,
    )


def _incremental_is_estimable(
    variant_id: str,
    factor_coverage: Mapping[FactorFamily, int],
) -> bool:
    family = _INCREMENTAL_FACTOR_BY_VARIANT[variant_id]
    return factor_coverage.get(family, 0) > 0


def _metrics_payload(
    metrics: AblationMetrics,
    *,
    incremental_estimable: bool,
) -> dict[str, Any]:
    payload = metrics.to_canonical_dict()
    if not incremental_estimable:
        payload["incremental_lift"] = None
    payload["incremental_lift_status"] = (
        EvidenceMetricStatus.AVAILABLE.value
        if incremental_estimable and metrics.incremental_lift is not None
        else EvidenceMetricStatus.NOT_ESTIMABLE.value
    )
    return payload


def _suite_payload(
    suite: AlphaAblationSuite,
    missing: int,
    factor_coverage: Mapping[FactorFamily, int],
) -> dict[str, Any]:
    observation_count = suite.results[-1].metrics.sample_count
    return {
        "suite_id": str(suite.suite_id),
        "suite_hash": suite.suite_hash,
        "protocol_reference": suite.protocol_reference.to_canonical_dict(),
        "panel_reference": suite.panel_reference.to_canonical_dict(),
        "comparison_sequence": list(suite.comparison_sequence),
        "results": [
            {
                "result_id": str(item.result_id),
                "result_hash": item.result_hash,
                "variant_id": item.variant.variant_id,
                "metrics": _metrics_payload(
                    item.metrics,
                    incremental_estimable=_incremental_is_estimable(
                        item.variant.variant_id,
                        factor_coverage,
                    ),
                ),
            }
            for item in suite.results
        ],
        "slice_evaluations": [
            {
                "variant_id": item.variant_id,
                "dimension": item.dimension,
                "value": item.value,
                "metrics": _metrics_payload(
                    item.metrics,
                    incremental_estimable=_incremental_is_estimable(
                        item.variant_id,
                        factor_coverage,
                    ),
                ),
            }
            for item in suite.slice_evaluations
        ],
        "factor_coverage": {
            family.value: {
                "observation_count": factor_coverage.get(family, 0),
                "coverage_ratio": str(Decimal(factor_coverage.get(family, 0)) / Decimal(observation_count)),
            }
            for family in sorted(factor_coverage, key=lambda item: item.value)
        },
        "incremental_estimability": {
            variant_id: (
                EvidenceMetricStatus.AVAILABLE.value
                if _incremental_is_estimable(variant_id, factor_coverage)
                else EvidenceMetricStatus.NOT_ESTIMABLE.value
            )
            for variant_id in suite.comparison_sequence
        },
        "excluded_missing_target_rows": missing,
    }


def _ablation_metrics(
    suite: AlphaAblationSuite,
    factor_coverage: Mapping[FactorFamily, int],
) -> tuple[HistoricalEvidenceMetric, ...]:
    output: list[HistoricalEvidenceMetric] = []
    for result in suite.results:
        output.extend(
            _metric_set(
                result.variant.variant_id,
                "ALL",
                "ALL",
                result.metrics,
                incremental_estimable=_incremental_is_estimable(
                    result.variant.variant_id,
                    factor_coverage,
                ),
            )
        )
    for item in suite.slice_evaluations:
        output.extend(
            _metric_set(
                item.variant_id,
                item.dimension,
                item.value,
                item.metrics,
                incremental_estimable=_incremental_is_estimable(
                    item.variant_id,
                    factor_coverage,
                ),
            )
        )
    return tuple(output)


def _metric_set(
    variant_id: str,
    slice_kind: str,
    slice_value: str,
    metrics: AblationMetrics,
    *,
    incremental_estimable: bool = True,
) -> tuple[HistoricalEvidenceMetric, ...]:
    result = []
    for field in fields(metrics):
        value = getattr(metrics, field.name)
        if field.name == "incremental_lift" and not incremental_estimable:
            value = None
        decimal_value = Decimal(value) if isinstance(value, int) else value if isinstance(value, Decimal) else None
        assumption = (
            MetricAssumptionStatus.ENGINEERING_ASSUMPTION
            if field.name in {"cost_return", "net_return"}
            else MetricAssumptionStatus.EMPIRICAL
        )
        result.append(
            HistoricalEvidenceMetric(
                variant_id=variant_id,
                slice_kind=slice_kind,
                slice_value=slice_value,
                metric_name=field.name,
                metric_value=decimal_value,
                metric_status=(EvidenceMetricStatus.AVAILABLE if decimal_value is not None else EvidenceMetricStatus.NOT_ESTIMABLE),
                assumption_status=assumption,
            )
        )
    return tuple(result)


def _summary_metrics(
    *,
    owner: HistoricalPackageIndex,
    panel_owner_count: int,
    observation_count: int,
    symbol_count: int,
    panel_missing: int,
    panel_summary: _StreamingPanelSummary,
) -> tuple[HistoricalEvidenceMetric, ...]:
    values = {
        "session_count": Decimal(panel_owner_count),
        "symbol_count": Decimal(symbol_count),
        "sample_count": Decimal(observation_count),
        "missing_target_count": Decimal(panel_missing),
        "normalized_row_count": Decimal(owner.coverage.normalized_row_count),
        "source_row_count": Decimal(owner.coverage.source_row_count),
        "provider_failure_count": Decimal(sum(value for _key, value in owner.coverage.failure_counts)),
        "forecast_usable_sample_total": Decimal(panel_summary.forecast_usable_sample_total),
        "forecast_usable_sample_maximum": Decimal(panel_summary.forecast_usable_sample_maximum),
        "forecast_excluded_sample_total": Decimal(panel_summary.forecast_excluded_sample_total),
    }
    base = tuple(
        HistoricalEvidenceMetric(
            variant_id="corpus",
            slice_kind="ALL",
            slice_value="ALL",
            metric_name=name,
            metric_value=value,
            metric_status=EvidenceMetricStatus.AVAILABLE,
            assumption_status=MetricAssumptionStatus.EMPIRICAL,
        )
        for name, value in sorted(values.items())
    )
    diagnostics = tuple(
        HistoricalEvidenceMetric(
            variant_id="corpus",
            slice_kind=slice_kind,
            slice_value=slice_value,
            metric_name="observation_count",
            metric_value=Decimal(count),
            metric_status=EvidenceMetricStatus.AVAILABLE,
            assumption_status=MetricAssumptionStatus.EMPIRICAL,
        )
        for slice_kind, counts in (
            ("TARGET_STATUS", panel_summary.target_status_counts),
            ("SIGNAL_STATE", panel_summary.signal_state_counts),
            ("SIGNAL_CONFIRMATION", panel_summary.signal_confirmation_counts),
            ("SIGNAL_REASON", panel_summary.signal_reason_counts),
            ("FORECAST_STATUS", panel_summary.forecast_status_counts),
            ("FORECAST_REASON", panel_summary.forecast_reason_counts),
            ("MONTH", panel_summary.period_observation_counts),
        )
        for slice_value, count in sorted(counts.items())
    )
    return tuple(
        sorted(
            (*base, *diagnostics),
            key=lambda item: (
                item.variant_id,
                item.slice_kind,
                item.slice_value,
                item.metric_name,
            ),
        )
    )


def _diagnostic_payload(summary: _StreamingPanelSummary) -> dict[str, Any]:
    return {
        "target_status_counts": dict(summary.target_status_counts),
        "signal_state_counts": dict(summary.signal_state_counts),
        "signal_confirmation_counts": dict(summary.signal_confirmation_counts),
        "signal_reason_counts": dict(summary.signal_reason_counts),
        "forecast_status_counts": dict(summary.forecast_status_counts),
        "forecast_reason_counts": dict(summary.forecast_reason_counts),
        "forecast_usable_sample_total": summary.forecast_usable_sample_total,
        "forecast_usable_sample_maximum": summary.forecast_usable_sample_maximum,
        "forecast_excluded_sample_total": summary.forecast_excluded_sample_total,
        "period_observation_counts": dict(summary.period_observation_counts),
        "corporate_action_excluded_count": summary.target_status_counts.get("CORPORATE_ACTION_EXCLUDED", 0),
    }


def _ablation_finding(suite: AlphaAblationSuite) -> ResearchFinding:
    first = suite.results[0].metrics
    last = suite.results[-1].metrics
    if last.session_count < 20:
        return ResearchFinding.INCONCLUSIVE
    if first.net_return is None or last.net_return is None:
        return ResearchFinding.NOT_ESTIMABLE
    lift = last.net_return - first.net_return
    rank_lift = None if first.rank_ic is None or last.rank_ic is None else last.rank_ic - first.rank_ic
    if lift > 0 and rank_lift is not None and rank_lift > 0:
        return ResearchFinding.POSITIVE
    if lift <= 0 and (rank_lift is None or rank_lift <= 0):
        return ResearchFinding.NEGATIVE
    return ResearchFinding.INCONCLUSIVE


def _ablation_rationale(suite: AlphaAblationSuite) -> str:
    first = suite.results[0].metrics
    last = suite.results[-1].metrics
    return (
        f"Frozen chain evaluated {last.sample_count} samples across "
        f"{last.session_count} sessions; Price net={first.net_return}, "
        f"Forecast-chain net={last.net_return}, Price RankIC={first.rank_ic}, "
        f"Forecast-chain RankIC={last.rank_ic}."
    )


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Historical {label} must be an object")
    return value


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"Historical {label} must be an object array")
    return tuple(value)


def _reference_key(item: ValidationArtifactReference) -> tuple[str, str, str]:
    return item.artifact_kind, str(item.artifact_id), item.content_hash


__all__ = [
    "HistoricalEvidenceProducer",
    "HistoricalEvidenceProductionResult",
]
