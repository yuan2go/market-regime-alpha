"""Owner-resolved corpus aggregation over the existing Ablation runtime."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalDataOwner,
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
from market_regime_alpha.application.historical_corpus.exploratory_challenger import (
    ExploratoryChallengerResult,
    HistoricalExploratoryChallenger,
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
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.ablation import (
    AblationMetrics,
    AblationObservation,
    AblationProtocol,
    AblationVariant,
    AblationVariantKind,
    AlphaAblationSuite,
    run_incremental_alpha_ablation_suite,
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
        outcome_references = self._components.list_references_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.OUTCOME,
        )
        if not panel_references:
            raise ValueError("Historical Evidence requires Research Panel owners")
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
        symbol_count = panel_summary.symbol_count
        protocol = AblationProtocol.create(
            protocol_version="phase-e-cumulative-chain-v1",
            variants=variants,
            comparison_sequence=tuple(item.value.lower() for item in _SEQUENCE),
            top_k=max(1, min(10, symbol_count // 3)),
            scoring_contract="WITHIN_SESSION_FACTOR_PERCENTILE_MEAN_V1",
            created_at=created_at,
        )
        panel_reference = _panel_set_reference(panel_references)
        suite = run_incremental_alpha_ablation_suite(
            protocol=protocol,
            panel_reference=panel_reference,
            observation_sessions=_stream_observation_sessions(
                self._components,
                run_id=run_id,
                component_batch_size=panel_summary.component_batch_size,
            ),
            created_at=created_at,
        )
        sources = tuple(
            sorted(
                {
                    *panel_references,
                    *outcome_references,
                    owner.reference,
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
            research_question=("Price through Forecast: which canonical research layers add incremental T+1 10:30 explanatory value?"),
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
                    "mode": "KEYSET_COMPONENT_BATCH_PLUS_SESSION_ACCUMULATOR_V1",
                    "component_batch_size": panel_summary.component_batch_size,
                    "maximum_session_observations": panel_summary.maximum_session_observations,
                    "whole_run_panel_materialized": False,
                    "whole_run_observation_graph_materialized": False,
                },
            },
            created_at=created_at,
            limitations=(
                "CUMULATIVE_SCORING_CONTRACT_FROZEN_NOT_TUNED",
                "MARKET_CAP_AND_INDUSTRY_NOT_ESTIMABLE_WHEN_PROVIDER_OMITS_FACTS",
                "UNOBSERVED_LAYER_LIFT_NOT_ESTIMABLE",
            ),
        )
        strategy_metrics = _strategy_metrics(
            component
            for batch in self._components.iter_for_run(
                run_id=run_id,
                component_kind=HistoricalComponentKind.OUTCOME,
                batch_size=4,
            )
            for component in batch
        )
        strategy_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.STRATEGY_ECONOMICS,
            research_question=(
                "Do T+1 OPEN/09:45/10:00/10:30/11:30/CLOSE variants retain "
                "economic value after fill, lot, liquidity, cost and impact assumptions?"
            ),
            classification=_strategy_finding(strategy_metrics),
            rationale=_strategy_rationale(strategy_metrics),
            source_references=sources,
            metrics=strategy_metrics,
            payload={
                "checkpoint_count": len({item.variant_id for item in strategy_metrics}),
                "cost_calibration": "ENGINEERING_ASSUMPTION",
                "actual_fill_authority": False,
            },
            created_at=created_at,
            limitations=("COST_AND_FILLABILITY_ENGINEERING_ASSUMPTIONS",),
        )
        full = suite.results[-1].metrics
        performance_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.PORTFOLIO_PERFORMANCE,
            research_question=("Does the full exploratory chain retain net portfolio value after turnover and drawdown?"),
            classification=_performance_finding(full),
            rationale=_performance_rationale(full),
            source_references=sources,
            metrics=_metric_set("full", "ALL", "ALL", full),
            payload={
                "variant_id": suite.results[-1].variant.variant_id,
                "session_count": full.session_count,
                "sample_count": full.sample_count,
            },
            created_at=created_at,
            limitations=("PORTFOLIO_RETURNS_ARE_RESEARCH_SIMULATION",),
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
                "owner": owner.to_canonical_dict(),
                "panel_owner_count": len(panel_references),
                "outcome_owner_count": len(outcome_references),
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
        challenger = HistoricalExploratoryChallenger(self._components).train(run_id=run_id)
        model_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.EXPLORATORY_MODEL,
            research_question=(
                "Can an owner-resolved fixed regularized-linear challenger improve T+1 10:30 prediction over the training-mean baseline?"
            ),
            classification=_challenger_finding(challenger),
            rationale=_challenger_rationale(challenger),
            source_references=challenger.source_references,
            metrics=_challenger_metrics(challenger),
            payload=challenger.to_canonical_dict(),
            created_at=created_at,
            limitations=(
                "EXPLORATORY_TEMPORAL_VALIDATION_IS_NOT_FORMAL_OOS",
                "FIXED_REGULARIZATION_PENALTY_NOT_TUNED",
            ),
        )
        evidence = tuple(
            self._evidence.put(item)
            for item in (
                corpus_evidence,
                ablation_evidence,
                strategy_evidence,
                performance_evidence,
                model_evidence,
            )
        )
        return HistoricalEvidenceProductionResult(
            run_id=run_id,
            observation_count=panel_summary.observation_count,
            suite=suite,
            evidence=evidence,
        )

    def _normalized_owner(self, references: tuple[ValidationArtifactReference, ...]) -> HistoricalDataOwner:
        matches = tuple(item for item in references if item.artifact_kind == NORMALIZED_DATASET_KIND)
        if len(matches) != 1:
            raise ValueError("Historical Evidence requires one normalized Dataset owner")
        return self._corpus.load(matches[0]).owner


def _panel_observations(
    panel: HistoricalSessionComponent,
    previous_selected: set[str],
) -> tuple[tuple[AblationObservation, ...], int, set[str]]:
    result: list[AblationObservation] = []
    missing = 0
    rows = _objects(panel.payload.get("rows"), "panel rows")
    selected = {str(item["symbol"]) for item in rows if bool(item.get("selected"))}
    for row in rows:
        realized = _optional_decimal(row.get("target_return"))
        if realized is None:
            missing += 1
            continue
        factors = _mapping(row.get("factor_values"), "factor values")
        values = tuple(
            sorted(
                (
                    (_FACTOR_MAP[name], name, value)
                    for name, raw in factors.items()
                    if name in _FACTOR_MAP and (value := _optional_decimal(raw)) is not None
                ),
                key=lambda item: (item[0].value, item[1]),
            )
        )
        symbol = str(row["symbol"])
        cost = _optional_decimal(row.get("cost_return"))
        result.append(
            AblationObservation(
                observation_id=f"{panel.component_id}:{symbol}:t-plus-one-1030",
                session_key=panel.trading_date.isoformat(),
                symbol=symbol,
                score=_optional_decimal(row.get("score")) or Decimal("0"),
                realized_return=realized,
                mfe=_optional_decimal(row.get("mfe")),
                mae=_optional_decimal(row.get("mae")),
                selected=symbol in selected,
                previous_selected=symbol in previous_selected,
                factor_values=values,
                cost_return=cost or Decimal("0.0021"),
                market_regime=str(row.get("market_regime", "NOT_ESTIMABLE")),
                liquidity_bucket=str(row.get("liquidity_bucket", "NOT_ESTIMABLE")),
                market_cap_bucket=str(row.get("market_cap_bucket", "NOT_ESTIMABLE")),
                volatility_bucket=str(row.get("volatility_bucket", "NOT_ESTIMABLE")),
                theme=str(row.get("theme", "NOT_ESTIMABLE")),
                industry=str(row.get("industry", "NOT_ESTIMABLE")),
                trading_date=panel.trading_date,
            )
        )
    return tuple(result), missing, selected


def _stream_observation_sessions(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    component_batch_size: int,
):
    previous_selected: set[str] = set()
    for batch in repository.iter_for_run(
        run_id=run_id,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        batch_size=component_batch_size,
    ):
        for panel in batch:
            observations, _missing, selected = _panel_observations(panel, previous_selected)
            previous_selected = selected
            yield observations


def _streaming_panel_summary(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    component_batch_size: int,
) -> _StreamingPanelSummary:
    previous_selected: set[str] = set()
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
            observations, panel_missing, selected = _panel_observations(panel, previous_selected)
            previous_selected = selected
            session_count += 1
            observation_count += len(observations)
            missing += panel_missing
            maximum_session_observations = max(maximum_session_observations, len(observations))
            for row in _objects(panel.payload.get("rows"), "panel rows"):
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
            for observation in observations:
                symbols.add(observation.symbol)
                observed = {family for family, _factor_id, _value in observation.factor_values}
                for family in coverage:
                    if family in observed:
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


def _panel_set_reference(panels: tuple[ValidationArtifactReference, ...]) -> ValidationArtifactReference:
    payload = {"panels": [item.to_canonical_dict() for item in panels]}
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "HISTORICAL_RESEARCH_PANEL_SET_BINDING",
        ArtifactId(f"historical-panel-set-{digest[7:31]}"),
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


def _strategy_metrics(
    outcomes: Iterable[HistoricalSessionComponent],
) -> tuple[HistoricalEvidenceMetric, ...]:
    values: dict[str, dict[str, tuple[Decimal, int]]] = {}
    for component in outcomes:
        protocol = OutcomeTargetProtocol.from_canonical_dict(_mapping(component.payload.get("target_protocol"), "target protocol"))
        checkpoint_by_label: dict[str, str] = {}
        target_by_id = {str(item.target_id): item.checkpoint.value for item in protocol.targets}
        for raw in _objects(component.payload.get("labels"), "labels"):
            label = TargetOutcomeLabel.from_canonical_dict(raw)
            checkpoint_by_label[str(label.label_id)] = target_by_id[str(label.target.artifact_id)]
        for result in _objects(component.payload.get("strategy_economics"), "strategy economics"):
            reference = _mapping(result.get("target_label_reference"), "target label reference")
            checkpoint = checkpoint_by_label.get(str(reference.get("artifact_id")))
            if checkpoint is None:
                raise ValueError("Strategy Economics label owner is missing")
            bucket = values.setdefault(checkpoint, {})
            for name in (
                "gross_return",
                "cost_return",
                "net_return",
                "turnover",
                "capacity_ceiling",
                "mfe",
                "mae",
            ):
                value = _optional_decimal(result.get(name))
                if value is not None:
                    total, count = bucket.get(name, (Decimal("0"), 0))
                    bucket[name] = total + value, count + 1
    metrics: list[HistoricalEvidenceMetric] = []
    for checkpoint, names in sorted(values.items()):
        for name in (
            "gross_return",
            "cost_return",
            "net_return",
            "turnover",
            "capacity_ceiling",
            "mfe",
            "mae",
        ):
            observations = names.get(name)
            value = None if observations is None else observations[0] / Decimal(observations[1])
            metrics.append(
                HistoricalEvidenceMetric(
                    variant_id=checkpoint,
                    slice_kind="ALL",
                    slice_value="ALL",
                    metric_name=name,
                    metric_value=value,
                    metric_status=(EvidenceMetricStatus.AVAILABLE if value is not None else EvidenceMetricStatus.NOT_ESTIMABLE),
                    assumption_status=(
                        MetricAssumptionStatus.ENGINEERING_ASSUMPTION
                        if name in {"cost_return", "net_return", "capacity_ceiling"}
                        else MetricAssumptionStatus.EMPIRICAL
                    ),
                )
            )
    return tuple(metrics)


def _summary_metrics(
    *,
    owner: HistoricalDataOwner,
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


def _challenger_metrics(
    result: ExploratoryChallengerResult,
) -> tuple[HistoricalEvidenceMetric, ...]:
    values = {
        "training_session_count": Decimal(result.training_session_count),
        "validation_session_count": Decimal(result.validation_session_count),
        "training_sample_count": Decimal(result.training_sample_count),
        "validation_sample_count": Decimal(result.validation_sample_count),
        "excluded_missing_target_count": Decimal(result.excluded_missing_target_count),
        "validation_mse": result.validation_mse,
        "baseline_mse": result.baseline_mse,
        "validation_rank_ic": result.validation_rank_ic,
        "validation_hit_rate": result.validation_hit_rate,
    }
    return tuple(
        HistoricalEvidenceMetric(
            variant_id="fixed-ridge-challenger-v1",
            slice_kind="TEMPORAL_VALIDATION",
            slice_value="ALL",
            metric_name=name,
            metric_value=value,
            metric_status=(EvidenceMetricStatus.AVAILABLE if value is not None else EvidenceMetricStatus.NOT_ESTIMABLE),
            assumption_status=MetricAssumptionStatus.EMPIRICAL,
        )
        for name, value in sorted(values.items())
    )


def _challenger_finding(result: ExploratoryChallengerResult) -> ResearchFinding:
    if result.status != "AVAILABLE":
        return ResearchFinding.NOT_ESTIMABLE
    if result.validation_mse is None or result.baseline_mse is None:
        return ResearchFinding.NOT_ESTIMABLE
    if result.validation_mse < result.baseline_mse and result.validation_rank_ic is not None and result.validation_rank_ic > 0:
        return ResearchFinding.POSITIVE
    if result.validation_mse >= result.baseline_mse and (result.validation_rank_ic is None or result.validation_rank_ic <= 0):
        return ResearchFinding.NEGATIVE
    return ResearchFinding.INCONCLUSIVE


def _challenger_rationale(result: ExploratoryChallengerResult) -> str:
    if result.status != "AVAILABLE":
        return "Owner reload completed but the challenger was not estimable: " + ",".join(result.reason_codes) + "."
    return (
        f"Fixed ridge used {result.training_sample_count} training and "
        f"{result.validation_sample_count} later validation samples; "
        f"validation MSE={result.validation_mse}, baseline MSE="
        f"{result.baseline_mse}, RankIC={result.validation_rank_ic}."
    )


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


def _strategy_finding(metrics: tuple[HistoricalEvidenceMetric, ...]) -> ResearchFinding:
    nets = tuple(item.metric_value for item in metrics if item.metric_name == "net_return" and item.metric_value is not None)
    if not nets:
        return ResearchFinding.NOT_ESTIMABLE
    if all(item > 0 for item in nets):
        return ResearchFinding.POSITIVE
    if all(item <= 0 for item in nets):
        return ResearchFinding.NEGATIVE
    return ResearchFinding.INCONCLUSIVE


def _strategy_rationale(metrics: tuple[HistoricalEvidenceMetric, ...]) -> str:
    available = tuple(item for item in metrics if item.metric_name == "net_return" and item.metric_value is not None)
    if not available:
        return "No checkpoint had estimable net Strategy Economics."
    best = max(available, key=lambda item: item.metric_value or Decimal("-Infinity"))
    worst = min(available, key=lambda item: item.metric_value or Decimal("Infinity"))
    return (
        f"Checkpoint net returns range from {worst.variant_id}={worst.metric_value} "
        f"to {best.variant_id}={best.metric_value}; costs and capacity remain "
        "engineering assumptions."
    )


def _performance_finding(metrics: AblationMetrics) -> ResearchFinding:
    if metrics.net_return is None:
        return ResearchFinding.NOT_ESTIMABLE
    return ResearchFinding.POSITIVE if metrics.net_return > 0 else ResearchFinding.NEGATIVE


def _performance_rationale(metrics: AblationMetrics) -> str:
    return (
        f"Full-chain gross={metrics.gross_return}, cost={metrics.cost_return}, "
        f"net={metrics.net_return}, turnover={metrics.turnover}, "
        f"max_drawdown={metrics.max_drawdown}."
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
