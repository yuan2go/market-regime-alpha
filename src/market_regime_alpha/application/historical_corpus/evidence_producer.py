"""Owner-resolved corpus aggregation over the existing Ablation runtime."""

from __future__ import annotations

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
    ScoreFunction,
    run_alpha_ablation_suite,
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


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceProductionResult:
    run_id: ArtifactId
    observation_count: int
    suite: AlphaAblationSuite
    evidence: tuple[HistoricalResearchEvidence, ...]


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
        panels = self._components.list_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        )
        outcomes = self._components.list_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.OUTCOME,
        )
        if not panels:
            raise ValueError("Historical Evidence requires Research Panel owners")
        owner = self._normalized_owner(snapshot.command.configuration_references)
        created_at = max(
            owner.created_at,
            *(item.materialized_at for item in panels),
            *(item.materialized_at for item in outcomes),
        )
        observations, panel_missing = _observations(panels)
        if not observations:
            raise ValueError("Historical Evidence has no estimable Target observations")
        variants = tuple(AblationVariant.standard(item) for item in _SEQUENCE)
        symbol_count = len({item.symbol for item in observations})
        protocol = AblationProtocol.create(
            protocol_version="phase-e-cumulative-chain-v1",
            variants=variants,
            comparison_sequence=tuple(item.value.lower() for item in _SEQUENCE),
            top_k=max(1, min(10, symbol_count // 3)),
            scoring_contract="WITHIN_SESSION_FACTOR_PERCENTILE_MEAN_V1",
            created_at=created_at,
        )
        panel_reference = _panel_set_reference(panels)
        score_functions = _score_functions(protocol, observations)
        suite = run_alpha_ablation_suite(
            protocol=protocol,
            panel_reference=panel_reference,
            observations=observations,
            score_functions=score_functions,
            created_at=created_at,
        )
        sources = tuple(
            sorted(
                {
                    *(item.reference for item in panels),
                    *(item.reference for item in outcomes),
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
            research_question=(
                "Price through Forecast: which canonical research layers add "
                "incremental T+1 10:30 explanatory value?"
            ),
            classification=_ablation_finding(suite),
            rationale=_ablation_rationale(suite),
            source_references=sources,
            metrics=_ablation_metrics(suite),
            payload=_suite_payload(suite, panel_missing),
            created_at=created_at,
            limitations=(
                "CUMULATIVE_SCORING_CONTRACT_FROZEN_NOT_TUNED",
                "MARKET_CAP_AND_INDUSTRY_NOT_ESTIMABLE_WHEN_PROVIDER_OMITS_FACTS",
            ),
        )
        strategy_metrics = _strategy_metrics(outcomes)
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
                "checkpoint_count": len(
                    {item.variant_id for item in strategy_metrics}
                ),
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
            research_question=(
                "Does the full exploratory chain retain net portfolio value after "
                "turnover and drawdown?"
            ),
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
            panels=panels,
            observations=observations,
            panel_missing=panel_missing,
        )
        corpus_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.CORPUS_SUMMARY,
            research_question="What exact coverage and missingness does this corpus contain?",
            classification=ResearchFinding.INCONCLUSIVE,
            rationale=(
                "Corpus summary is descriptive evidence and does not classify Alpha."
            ),
            source_references=sources,
            metrics=summary_metrics,
            payload={
                "owner": owner.to_canonical_dict(),
                "panel_owner_count": len(panels),
                "outcome_owner_count": len(outcomes),
                "excluded_missing_target_rows": panel_missing,
            },
            created_at=created_at,
        )
        challenger = HistoricalExploratoryChallenger(self._components).train(
            run_id=run_id
        )
        model_evidence = HistoricalResearchEvidence.create(
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            experiment_reference=experiment,
            evidence_kind=HistoricalEvidenceKind.EXPLORATORY_MODEL,
            research_question=(
                "Can an owner-resolved fixed regularized-linear challenger improve "
                "T+1 10:30 prediction over the training-mean baseline?"
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
            observation_count=len(observations),
            suite=suite,
            evidence=evidence,
        )

    def _normalized_owner(
        self, references: tuple[ValidationArtifactReference, ...]
    ) -> HistoricalDataOwner:
        matches = tuple(
            item for item in references if item.artifact_kind == NORMALIZED_DATASET_KIND
        )
        if len(matches) != 1:
            raise ValueError("Historical Evidence requires one normalized Dataset owner")
        return self._corpus.load(matches[0]).owner


def _observations(
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[tuple[AblationObservation, ...], int]:
    result: list[AblationObservation] = []
    missing = 0
    previous_selected: set[str] = set()
    for panel in sorted(panels, key=lambda item: item.trading_date):
        rows = _objects(panel.payload.get("rows"), "panel rows")
        selected = {
            str(item["symbol"]) for item in rows if bool(item.get("selected"))
        }
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
                        if name in _FACTOR_MAP
                        and (value := _optional_decimal(raw)) is not None
                    ),
                    key=lambda item: (item[0].value, item[1]),
                )
            )
            symbol = str(row["symbol"])
            cost = _optional_decimal(row.get("cost_return"))
            result.append(
                AblationObservation(
                    observation_id=(
                        f"{panel.component_id}:{symbol}:t-plus-one-1030"
                    ),
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
                    liquidity_bucket=str(
                        row.get("liquidity_bucket", "NOT_ESTIMABLE")
                    ),
                    market_cap_bucket=str(
                        row.get("market_cap_bucket", "NOT_ESTIMABLE")
                    ),
                    volatility_bucket=str(
                        row.get("volatility_bucket", "NOT_ESTIMABLE")
                    ),
                    theme=str(row.get("theme", "NOT_ESTIMABLE")),
                    industry=str(row.get("industry", "NOT_ESTIMABLE")),
                    trading_date=panel.trading_date,
                )
            )
        previous_selected = selected
    return tuple(result), missing


def _score_functions(
    protocol: AblationProtocol,
    observations: tuple[AblationObservation, ...],
) -> Mapping[str, ScoreFunction]:
    rank_values: dict[tuple[str, FactorFamily, str], Decimal] = {}
    by_session_factor: dict[
        tuple[str, FactorFamily, str], list[tuple[str, Decimal]]
    ] = {}
    for item in observations:
        for family, factor_id, value in item.factor_values:
            by_session_factor.setdefault(
                (item.session_key, family, factor_id), []
            ).append((item.observation_id, value))
    for key, values in by_session_factor.items():
        ordered = sorted(values, key=lambda item: (item[1], item[0]))
        denominator = Decimal(max(1, len(ordered) - 1))
        for index, (observation_id, _value) in enumerate(ordered):
            rank_values[(observation_id, key[1], key[2])] = Decimal(index) / denominator

    def scorer(item: AblationObservation, variant: AblationVariant) -> Decimal:
        values = tuple(
            rank_values[(item.observation_id, family, factor_id)]
            for family, factor_id, _raw in item.factor_values
            if variant.includes(family, factor_id)
        )
        return (
            Decimal("0")
            if not values
            else sum(values, Decimal("0")) / Decimal(len(values))
        )

    return {item.variant_id: scorer for item in protocol.variants}


def _panel_set_reference(
    panels: tuple[HistoricalSessionComponent, ...]
) -> ValidationArtifactReference:
    payload = {"panels": [item.reference.to_canonical_dict() for item in panels]}
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "HISTORICAL_RESEARCH_PANEL_SET_BINDING",
        ArtifactId(f"historical-panel-set-{digest[7:31]}"),
        digest,
    )


def _suite_payload(suite: AlphaAblationSuite, missing: int) -> dict[str, Any]:
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
                "metrics": item.metrics.to_canonical_dict(),
            }
            for item in suite.results
        ],
        "slice_evaluations": [
            item.to_canonical_dict() for item in suite.slice_evaluations
        ],
        "excluded_missing_target_rows": missing,
    }


def _ablation_metrics(
    suite: AlphaAblationSuite,
) -> tuple[HistoricalEvidenceMetric, ...]:
    output: list[HistoricalEvidenceMetric] = []
    for result in suite.results:
        output.extend(
            _metric_set(result.variant.variant_id, "ALL", "ALL", result.metrics)
        )
    for item in suite.slice_evaluations:
        output.extend(
            _metric_set(item.variant_id, item.dimension, item.value, item.metrics)
        )
    return tuple(output)


def _metric_set(
    variant_id: str,
    slice_kind: str,
    slice_value: str,
    metrics: AblationMetrics,
) -> tuple[HistoricalEvidenceMetric, ...]:
    result = []
    for field in fields(metrics):
        value = getattr(metrics, field.name)
        decimal_value = (
            Decimal(value)
            if isinstance(value, int)
            else value
            if isinstance(value, Decimal)
            else None
        )
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
                metric_status=(
                    EvidenceMetricStatus.AVAILABLE
                    if decimal_value is not None
                    else EvidenceMetricStatus.NOT_ESTIMABLE
                ),
                assumption_status=assumption,
            )
        )
    return tuple(result)


def _strategy_metrics(
    outcomes: tuple[HistoricalSessionComponent, ...]
) -> tuple[HistoricalEvidenceMetric, ...]:
    values: dict[str, dict[str, list[Decimal]]] = {}
    for component in outcomes:
        protocol = OutcomeTargetProtocol.from_canonical_dict(
            _mapping(component.payload.get("target_protocol"), "target protocol")
        )
        checkpoint_by_label: dict[str, str] = {}
        target_by_id = {
            str(item.target_id): item.checkpoint.value for item in protocol.targets
        }
        for raw in _objects(component.payload.get("labels"), "labels"):
            label = TargetOutcomeLabel.from_canonical_dict(raw)
            checkpoint_by_label[str(label.label_id)] = target_by_id[
                str(label.target.artifact_id)
            ]
        for result in _objects(
            component.payload.get("strategy_economics"), "strategy economics"
        ):
            reference = _mapping(
                result.get("target_label_reference"), "target label reference"
            )
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
                    bucket.setdefault(name, []).append(value)
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
            observations = names.get(name, [])
            value = (
                None
                if not observations
                else sum(observations, Decimal("0")) / Decimal(len(observations))
            )
            metrics.append(
                HistoricalEvidenceMetric(
                    variant_id=checkpoint,
                    slice_kind="ALL",
                    slice_value="ALL",
                    metric_name=name,
                    metric_value=value,
                    metric_status=(
                        EvidenceMetricStatus.AVAILABLE
                        if value is not None
                        else EvidenceMetricStatus.NOT_ESTIMABLE
                    ),
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
    panels: tuple[HistoricalSessionComponent, ...],
    observations: tuple[AblationObservation, ...],
    panel_missing: int,
) -> tuple[HistoricalEvidenceMetric, ...]:
    values = {
        "session_count": Decimal(len(panels)),
        "symbol_count": Decimal(len({item.symbol for item in observations})),
        "sample_count": Decimal(len(observations)),
        "missing_target_count": Decimal(panel_missing),
        "normalized_row_count": Decimal(owner.coverage.normalized_row_count),
        "source_row_count": Decimal(owner.coverage.source_row_count),
        "provider_failure_count": Decimal(
            sum(value for _key, value in owner.coverage.failure_counts)
        ),
    }
    return tuple(
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


def _challenger_metrics(
    result: ExploratoryChallengerResult,
) -> tuple[HistoricalEvidenceMetric, ...]:
    values = {
        "training_session_count": Decimal(result.training_session_count),
        "validation_session_count": Decimal(result.validation_session_count),
        "training_sample_count": Decimal(result.training_sample_count),
        "validation_sample_count": Decimal(result.validation_sample_count),
        "excluded_missing_target_count": Decimal(
            result.excluded_missing_target_count
        ),
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
            metric_status=(
                EvidenceMetricStatus.AVAILABLE
                if value is not None
                else EvidenceMetricStatus.NOT_ESTIMABLE
            ),
            assumption_status=MetricAssumptionStatus.EMPIRICAL,
        )
        for name, value in sorted(values.items())
    )


def _challenger_finding(result: ExploratoryChallengerResult) -> ResearchFinding:
    if result.status != "AVAILABLE":
        return ResearchFinding.NOT_ESTIMABLE
    if result.validation_mse is None or result.baseline_mse is None:
        return ResearchFinding.NOT_ESTIMABLE
    if (
        result.validation_mse < result.baseline_mse
        and result.validation_rank_ic is not None
        and result.validation_rank_ic > 0
    ):
        return ResearchFinding.POSITIVE
    if (
        result.validation_mse >= result.baseline_mse
        and (
            result.validation_rank_ic is None
            or result.validation_rank_ic <= 0
        )
    ):
        return ResearchFinding.NEGATIVE
    return ResearchFinding.INCONCLUSIVE


def _challenger_rationale(result: ExploratoryChallengerResult) -> str:
    if result.status != "AVAILABLE":
        return (
            "Owner reload completed but the challenger was not estimable: "
            + ",".join(result.reason_codes)
            + "."
        )
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
    rank_lift = (
        None
        if first.rank_ic is None or last.rank_ic is None
        else last.rank_ic - first.rank_ic
    )
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


def _strategy_finding(
    metrics: tuple[HistoricalEvidenceMetric, ...]
) -> ResearchFinding:
    nets = tuple(
        item.metric_value
        for item in metrics
        if item.metric_name == "net_return" and item.metric_value is not None
    )
    if not nets:
        return ResearchFinding.NOT_ESTIMABLE
    if all(item > 0 for item in nets):
        return ResearchFinding.POSITIVE
    if all(item <= 0 for item in nets):
        return ResearchFinding.NEGATIVE
    return ResearchFinding.INCONCLUSIVE


def _strategy_rationale(
    metrics: tuple[HistoricalEvidenceMetric, ...]
) -> str:
    available = tuple(
        item for item in metrics
        if item.metric_name == "net_return" and item.metric_value is not None
    )
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
    return (
        ResearchFinding.POSITIVE
        if metrics.net_return > 0
        else ResearchFinding.NEGATIVE
    )


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
