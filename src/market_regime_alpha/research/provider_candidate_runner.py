"""Provider rehearsal artifact to fixed R5 Candidate baseline evaluations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.candidates import (
    CandidateResearchDataset,
    build_candidate_population_from_historical_artifacts,
    build_candidate_research_dataset,
    materialize_r5_opportunity_targets_from_calendar,
    r5_next_session_opportunity_target_contracts,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, TargetId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.data import DataEligibility, DatasetContract
from market_regime_alpha.features.rehearsal_baselines import (
    materialize_r5_baseline_features,
    r5_baseline_feature_definitions,
)
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
)
from market_regime_alpha.research.r5_baseline_runner import (
    R5TargetBaselineRun,
    run_r5_target_baselines,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_policy import TradingEligibilityPolicy


PROVIDER_CANDIDATE_RUNNER_VERSION = "R5_PROVIDER_CANDIDATE_RUNNER_V1"
PROVIDER_REHEARSAL_POLICY_V2 = "r5-provider-rehearsal-trading-eligibility@v2"
NO_CANDIDATES_AFTER_ELIGIBILITY = "NO_CANDIDATES_AFTER_ELIGIBILITY"


class ProviderCandidateRunOutcome(str, Enum):
    """Whether the selected provider artifact yielded evaluable Candidate slices."""

    EVALUATED = "EVALUATED"
    NO_CANDIDATES_AFTER_ELIGIBILITY = "NO_CANDIDATES_AFTER_ELIGIBILITY"


@dataclass(frozen=True, slots=True)
class CandidateDecisionDiagnostic:
    """Universe and eligibility accounting for one exact Decision Time."""

    decision_time: DecisionTime
    universe_member_count: int
    eligible_count: int
    ineligible_count: int
    unknown_count: int

    def __post_init__(self) -> None:
        counts = (
            self.universe_member_count,
            self.eligible_count,
            self.ineligible_count,
            self.unknown_count,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
            raise TypeError("Candidate diagnostic counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("Candidate diagnostic counts must be non-negative")
        if self.universe_member_count != (
            self.eligible_count + self.ineligible_count + self.unknown_count
        ):
            raise ValueError("eligibility status counts must cover the Universe members")


@dataclass(frozen=True, slots=True)
class ProviderCandidateRun:
    """One provider-backed/provider-export-backed R5 Candidate rehearsal run."""

    outcome: ProviderCandidateRunOutcome
    data_eligibility: DataEligibility
    market_artifact_id: ArtifactId
    source_dataset_id: DatasetId
    eligibility_artifact_id: ArtifactId
    eligibility_policy_artifact_id: ArtifactId
    decision_times: tuple[DecisionTime, ...]
    decision_diagnostics: tuple[CandidateDecisionDiagnostic, ...]
    target_runs: tuple[R5TargetBaselineRun, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ProviderCandidateRunOutcome):
            raise TypeError("outcome must be a ProviderCandidateRunOutcome")
        if self.data_eligibility is not DataEligibility.REHEARSAL:
            raise ValueError("provider Candidate run must remain REHEARSAL")
        if not self.decision_times:
            raise ValueError("provider Candidate run requires Decision Times")
        if tuple(sorted(self.decision_times, key=lambda item: item.value)) != self.decision_times:
            raise ValueError("decision_times must be chronological")
        if tuple(item.decision_time for item in self.decision_diagnostics) != self.decision_times:
            raise ValueError("decision diagnostics must cover each Decision Time in order")
        if self.outcome is ProviderCandidateRunOutcome.NO_CANDIDATES_AFTER_ELIGIBILITY:
            if self.target_runs:
                raise ValueError("empty Candidate outcome cannot contain Target evaluations")
            if any(item.eligible_count for item in self.decision_diagnostics):
                raise ValueError("empty Candidate outcome cannot contain eligible instruments")
        elif len(self.target_runs) != 3:
            raise ValueError("evaluated provider Candidate run requires three Target families")
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("limitations must be unique")


def run_provider_candidate_experiment(
    *,
    market_artifact: ProviderRehearsalMarketArtifact,
    eligibility_policy: TradingEligibilityPolicy,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
    decision_count: int,
) -> ProviderCandidateRun:
    """Materialize provider evidence and evaluate the fixed B0/B1 ladder by Target."""

    _validate_provider_rehearsal_policy(eligibility_policy)
    if isinstance(decision_count, bool) or not isinstance(decision_count, int):
        raise TypeError("decision_count must be an integer")
    if decision_count <= 0:
        raise ValueError("decision_count must be positive")

    available_decision_times = market_artifact.decision_times
    if decision_count > len(available_decision_times):
        raise ValueError("decision_count exceeds provider artifact Decision Times")
    decision_times = available_decision_times[-decision_count:]
    if materialized_at.value <= decision_times[-1].value:
        raise ValueError("materialized_at must be after the final selected Decision Time")

    eligibility_artifact = market_artifact.materialize_trading_eligibility(
        policy=eligibility_policy
    )
    dataset_contracts = (
        market_artifact.dataset_contract,
        _universe_source_dataset_contract(market_artifact),
    )
    limitations = _unique(
        (
            *market_artifact.dataset_contract.limitations,
            f"RUNNER_VERSION={PROVIDER_CANDIDATE_RUNNER_VERSION}",
            "PROVIDER_REHEARSAL_ONLY",
            "FIXED_B0_B1_LADDER_NOT_MODEL_SELECTION",
            "DESCRIPTIVE_REHEARSAL_METRICS_NOT_ALPHA_EVIDENCE",
        )
    )

    diagnostics: list[CandidateDecisionDiagnostic] = []
    datasets_by_target: dict[TargetId, list[CandidateResearchDataset]] = defaultdict(list)
    target_contracts = r5_next_session_opportunity_target_contracts()
    target_contract_by_id = {contract.target_id: contract for contract in target_contracts}
    feature_definitions = r5_baseline_feature_definitions()

    for decision_time in decision_times:
        universe_snapshot = market_artifact.universe_artifact.snapshot_for_decision_time(
            decision_time
        )
        eligibility_snapshot = eligibility_artifact.snapshot_for_decision_time(decision_time)
        status_counts = {
            status: sum(
                eligibility_snapshot.status_for(symbol) is status
                for symbol in universe_snapshot.member_symbols
            )
            for status in TradingEligibilityStatus
        }
        diagnostics.append(
            CandidateDecisionDiagnostic(
                decision_time=decision_time,
                universe_member_count=len(universe_snapshot.member_symbols),
                eligible_count=status_counts[TradingEligibilityStatus.ELIGIBLE],
                ineligible_count=status_counts[TradingEligibilityStatus.INELIGIBLE],
                unknown_count=status_counts[TradingEligibilityStatus.UNKNOWN],
            )
        )
        population = build_candidate_population_from_historical_artifacts(
            universe_artifact=market_artifact.universe_artifact,
            eligibility_artifact=eligibility_artifact,
            decision_time=decision_time,
        )
        if not population.symbols:
            continue

        feature_materializations = materialize_r5_baseline_features(
            population=population,
            source_dataset_id=market_artifact.dataset_contract.dataset_id,
            daily_bars=market_artifact.daily_bars,
            decision_snapshots=market_artifact.decision_snapshots,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        next_session_date = market_artifact.trading_calendar.resolve_next_session_date(
            decision_time
        )
        target_bundle = materialize_r5_opportunity_targets_from_calendar(
            population=population,
            calendar=market_artifact.trading_calendar,
            source_dataset_id=market_artifact.dataset_contract.dataset_id,
            decision_snapshots=tuple(
                item
                for item in market_artifact.decision_snapshots
                if item.decision_time == decision_time
            ),
            next_session_bars=tuple(
                item
                for item in market_artifact.next_session_bars
                if item.session_date == next_session_date
            ),
            materialized_at=materialized_at,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        for target_materialization in target_bundle.materializations:
            target_contract = target_contract_by_id[target_materialization.target_id]
            dataset = build_candidate_research_dataset(
                population=population,
                dataset_contracts=dataset_contracts,
                feature_definitions=feature_definitions,
                feature_materializations=feature_materializations,
                target_contract=target_contract,
                target_materialization=target_materialization,
                limitations=limitations,
            )
            datasets_by_target[target_materialization.target_id].append(dataset)

    if not datasets_by_target:
        return ProviderCandidateRun(
            outcome=ProviderCandidateRunOutcome.NO_CANDIDATES_AFTER_ELIGIBILITY,
            data_eligibility=DataEligibility.REHEARSAL,
            market_artifact_id=market_artifact.artifact_id,
            source_dataset_id=market_artifact.dataset_contract.dataset_id,
            eligibility_artifact_id=eligibility_artifact.artifact_id,
            eligibility_policy_artifact_id=eligibility_policy.policy_artifact_id,
            decision_times=decision_times,
            decision_diagnostics=tuple(diagnostics),
            target_runs=(),
            limitations=_unique((*limitations, NO_CANDIDATES_AFTER_ELIGIBILITY)),
        )

    target_runs = tuple(
        run_r5_target_baselines(
            datasets=tuple(datasets_by_target[contract.target_id]),
            code_revision=code_revision,
            config_hash=config_hash,
            model_identity_prefix="xuntou-rehearsal",
            panel_limitations=limitations,
        )
        for contract in target_contracts
    )
    return ProviderCandidateRun(
        outcome=ProviderCandidateRunOutcome.EVALUATED,
        data_eligibility=DataEligibility.REHEARSAL,
        market_artifact_id=market_artifact.artifact_id,
        source_dataset_id=market_artifact.dataset_contract.dataset_id,
        eligibility_artifact_id=eligibility_artifact.artifact_id,
        eligibility_policy_artifact_id=eligibility_policy.policy_artifact_id,
        decision_times=decision_times,
        decision_diagnostics=tuple(diagnostics),
        target_runs=target_runs,
        limitations=limitations,
    )


def _universe_source_dataset_contract(
    market_artifact: ProviderRehearsalMarketArtifact,
) -> DatasetContract:
    universe = market_artifact.universe_artifact
    return DatasetContract(
        dataset_id=universe.source_dataset_id,
        schema_version="provider-candidate-universe-source-contract-v1",
        eligibility=market_artifact.dataset_contract.eligibility,
        manifest_artifact_id=universe.artifact_id,
        provider_references=market_artifact.dataset_contract.provider_references,
        pit_correct_for_scope=market_artifact.dataset_contract.pit_correct_for_scope,
        scope="Historical Universe evidence composed into an R5 provider Candidate run",
        limitations=_unique(
            (
                *market_artifact.dataset_contract.limitations,
                "UNIVERSE_SOURCE_CONTRACT_VIEW_OF_PROVIDER_MARKET_ARTIFACT",
            )
        ),
    )


def _validate_provider_rehearsal_policy(policy: TradingEligibilityPolicy) -> None:
    if policy.policy_version != PROVIDER_REHEARSAL_POLICY_V2:
        raise ValueError("provider Candidate runs require provider-rehearsal eligibility policy v2")
    required_flags = (
        policy.exclude_st,
        policy.require_prev_close,
        policy.require_limit_metadata,
        policy.require_decision_buyability,
    )
    if not all(required_flags):
        raise ValueError("provider-rehearsal eligibility policy v2 cannot weaken required evidence")
    if policy.minimum_listing_age_calendar_days != 61:
        raise ValueError("provider-rehearsal eligibility policy v2 requires listing age 61 days")
    if policy.minimum_liquidity_value is None or policy.liquidity_measure_id is None:
        raise ValueError("provider-rehearsal eligibility policy v2 requires explicit liquidity")


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
