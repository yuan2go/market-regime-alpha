"""Shared Strategy semantics for Continuous, Historical, and Replay execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
)
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    GateAttribution,
    MultiStrategyCycle,
    PriceFreshnessStatus,
    StrategyContract,
    StrategyEligibilityStatus,
    StrategyFamily,
    StrategyPositionState,
    StrategyProposal,
    StrategyRegistry,
    StrategyRun,
    StrategyRunStatus,
    StrategyRuntimeInput,
    StrategyVersion,
    strategy_reference,
)


_STRATEGY_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class _Eligibility:
    status: StrategyEligibilityStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PolicyDecision:
    action: CanonicalStrategyAction
    desired_weight: Decimal
    reason_codes: tuple[str, ...]


class _StrategyPolicy:
    def decide(
        self,
        *,
        contract: StrategyContract,
        candidate: CandidateRecord | None,
        position: StrategyPositionState | None,
        eligibility: _Eligibility,
    ) -> _PolicyDecision:
        raise NotImplementedError


class _OvernightPolicy(_StrategyPolicy):
    def decide(
        self,
        *,
        contract: StrategyContract,
        candidate: CandidateRecord | None,
        position: StrategyPositionState | None,
        eligibility: _Eligibility,
    ) -> _PolicyDecision:
        del candidate
        unit_weight = contract.strategy_budget / Decimal(contract.top_k)
        if position is not None and position.sessions_held >= max(contract.horizon_sessions):
            return _PolicyDecision(
                CanonicalStrategyAction.EXIT,
                -contract.strategy_budget,
                ("OVERNIGHT_HORIZON_REACHED",),
            )
        if position is not None:
            return _PolicyDecision(
                CanonicalStrategyAction.HOLD,
                Decimal("0"),
                ("OVERNIGHT_AWAITING_NEXT_SESSION",),
            )
        if eligibility.status is StrategyEligibilityStatus.ELIGIBLE:
            return _PolicyDecision(
                CanonicalStrategyAction.ENTER,
                unit_weight,
                ("OVERNIGHT_ENTRY_ELIGIBLE",),
            )
        return _PolicyDecision(
            CanonicalStrategyAction.NO_ACTION,
            Decimal("0"),
            ("OVERNIGHT_ENTRY_NOT_ELIGIBLE",),
        )


class _SwingStatePolicy(_StrategyPolicy):
    def decide(
        self,
        *,
        contract: StrategyContract,
        candidate: CandidateRecord | None,
        position: StrategyPositionState | None,
        eligibility: _Eligibility,
    ) -> _PolicyDecision:
        del candidate
        parameters = dict(contract.parameters)
        unit_weight = contract.strategy_budget / Decimal(contract.top_k)
        if position is None:
            if eligibility.status is StrategyEligibilityStatus.ELIGIBLE:
                return _PolicyDecision(
                    CanonicalStrategyAction.ENTER,
                    unit_weight,
                    ("SWING_ENTRY_ELIGIBLE",),
                )
            return _PolicyDecision(
                CanonicalStrategyAction.NO_ACTION,
                Decimal("0"),
                ("SWING_ENTRY_NOT_ELIGIBLE",),
            )
        if position.current_price is None:
            return _PolicyDecision(
                CanonicalStrategyAction.NO_ACTION,
                Decimal("0"),
                ("SWING_CURRENT_PRICE_NOT_ESTIMABLE",),
            )
        if position.price_freshness is PriceFreshnessStatus.NOT_ESTIMABLE:
            return _PolicyDecision(
                CanonicalStrategyAction.NO_ACTION,
                Decimal("0"),
                ("SWING_CURRENT_PRICE_NOT_ESTIMABLE",),
            )
        if position.price_freshness is PriceFreshnessStatus.STALE:
            return _PolicyDecision(
                CanonicalStrategyAction.NO_ACTION,
                Decimal("0"),
                ("SWING_CURRENT_PRICE_STALE",),
            )
        return_since_entry = position.current_price / position.average_cost - Decimal("1")
        stop_loss = Decimal(parameters.get("stop_loss", "0.08"))
        if return_since_entry <= -stop_loss:
            return _PolicyDecision(
                CanonicalStrategyAction.EXIT,
                -contract.strategy_budget,
                ("SWING_STOP_LOSS_REACHED",),
            )
        if position.sessions_held >= max(contract.horizon_sessions):
            return _PolicyDecision(
                CanonicalStrategyAction.EXIT,
                -contract.strategy_budget,
                ("SWING_MAX_HORIZON_REACHED",),
            )
        drawdown = Decimal("1") - position.current_price / position.peak_price
        reduce_drawdown = Decimal(parameters.get("reduce_drawdown", "0.04"))
        if drawdown >= reduce_drawdown:
            return _PolicyDecision(
                CanonicalStrategyAction.REDUCE,
                -(unit_weight / Decimal("2")),
                ("SWING_PEAK_DRAWDOWN_REDUCTION",),
            )
        add_return = Decimal(parameters.get("add_return", "0.03"))
        max_add_count = int(parameters.get("max_add_count", "1"))
        if (
            eligibility.status is StrategyEligibilityStatus.ELIGIBLE
            and return_since_entry >= add_return
            and position.add_count < max_add_count
        ):
            return _PolicyDecision(
                CanonicalStrategyAction.ADD,
                unit_weight / Decimal("2"),
                ("SWING_ADD_CONDITION_MET",),
            )
        return _PolicyDecision(
            CanonicalStrategyAction.HOLD,
            Decimal("0"),
            ("SWING_POSITION_REMAINS_VALID",),
        )


class MultiStrategyRuntime:
    """Runs every active Strategy Version without owning the control plane."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry
        self._policies: dict[StrategyFamily, _StrategyPolicy] = {
            StrategyFamily.OVERNIGHT: _OvernightPolicy(),
            StrategyFamily.SWING_STATE: _SwingStatePolicy(),
        }

    def execute(self, runtime_input: StrategyRuntimeInput) -> MultiStrategyCycle:
        with localcontext(_STRATEGY_DECIMAL_CONTEXT):
            return self._execute(runtime_input)

    def _execute(self, runtime_input: StrategyRuntimeInput) -> MultiStrategyCycle:
        if runtime_input.authority_mode is RuntimeAuthorityMode.PRODUCTION:
            raise RuntimeError("PRODUCTION_AUTHORIZED_FALSE")
        cycle_id = MultiStrategyCycle.identity(
            runtime_input,
            tuple(strategy_reference(item) for item in self._registry.active_versions),
        )
        candidates = {item.symbol: item for item in runtime_input.candidate_set.records}
        runs = tuple(
            self._execute_version(
                cycle_id=cycle_id,
                runtime_input=runtime_input,
                version=version,
                candidates=candidates,
            )
            for version in self._registry.active_versions
        )
        return MultiStrategyCycle.create(
            cycle_id=cycle_id,
            runtime_input=runtime_input,
            runs=runs,
            created_at=runtime_input.decision_time,
        )

    def _execute_version(
        self,
        *,
        cycle_id: ArtifactId,
        runtime_input: StrategyRuntimeInput,
        version: StrategyVersion,
        candidates: dict[str, CandidateRecord],
    ) -> StrategyRun:
        contract = self._registry.contract_for(version)
        run_id = StrategyRun.identity(cycle_id, version)
        positions = {item.symbol: item for item in runtime_input.positions if item.strategy_version_id == version.version_id}
        symbols = tuple(sorted(set(candidates) | set(positions)))
        gates: list[GateAttribution] = []
        proposals: list[StrategyProposal] = []
        for symbol in symbols:
            candidate = candidates.get(symbol)
            eligibility = _eligibility(candidate, contract)
            decision = self._policies[version.family].decide(
                contract=contract,
                candidate=candidate,
                position=positions.get(symbol),
                eligibility=eligibility,
            )
            reason_codes = tuple(sorted(set(eligibility.reason_codes + decision.reason_codes)))
            gates.append(
                GateAttribution(
                    symbol=symbol,
                    eligibility_status=eligibility.status,
                    candidate_status=("POSITION_ONLY" if candidate is None else candidate.selection_status.value),
                    rank=None if candidate is None else candidate.rank,
                    action=decision.action,
                    reason_codes=reason_codes,
                )
            )
            if decision.action in {
                CanonicalStrategyAction.ENTER,
                CanonicalStrategyAction.ADD,
                CanonicalStrategyAction.REDUCE,
                CanonicalStrategyAction.ROTATE,
                CanonicalStrategyAction.EXIT,
            }:
                proposals.append(
                    StrategyProposal.create(
                        strategy_run_id=run_id,
                        strategy_version_reference=strategy_reference(version),
                        candidate_reference=_candidate_reference(runtime_input),
                        symbol=symbol,
                        action=decision.action,
                        desired_weight=decision.desired_weight,
                        utility_score=(
                            None
                            if candidate is None or candidate.candidate_discovery_score is None
                            else Decimal(str(candidate.candidate_discovery_score))
                        ),
                        reason_codes=decision.reason_codes,
                        limitations=contract.limitations,
                    )
                )
        status = (
            StrategyRunStatus.DATA_INSUFFICIENT
            if not gates
            or all(
                item.eligibility_status is StrategyEligibilityStatus.NOT_ESTIMABLE
                for item in gates
            )
            else StrategyRunStatus.COMPLETED
        )
        reason_code = (
            "STRATEGY_CANDIDATE_POPULATION_EMPTY"
            if not gates
            else (
                "STRATEGY_INPUT_DATA_INSUFFICIENT"
                if status is StrategyRunStatus.DATA_INSUFFICIENT
                else "STRATEGY_RUN_COMPLETED"
            )
        )
        return StrategyRun.create(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_version_reference=strategy_reference(version),
            origin=runtime_input.origin,
            authority_mode=runtime_input.authority_mode,
            decision_time=runtime_input.decision_time,
            input_hash=runtime_input.input_hash,
            status=status,
            gate_attributions=tuple(gates),
            proposals=tuple(proposals),
            reason_codes=(reason_code,),
        )


def _eligibility(
    candidate: CandidateRecord | None,
    contract: StrategyContract,
) -> _Eligibility:
    if candidate is None:
        return _Eligibility(
            StrategyEligibilityStatus.INELIGIBLE,
            ("POSITION_NOT_IN_CANDIDATE_SET",),
        )
    if candidate.selection_status is CandidateSelectionStatus.DATA_INSUFFICIENT:
        return _Eligibility(
            StrategyEligibilityStatus.NOT_ESTIMABLE,
            ("CANDIDATE_DATA_INSUFFICIENT",),
        )
    if candidate.selection_status is not CandidateSelectionStatus.SELECTED:
        return _Eligibility(
            StrategyEligibilityStatus.INELIGIBLE,
            (f"CANDIDATE_{candidate.selection_status.value}",),
        )
    if candidate.candidate_discovery_score is None:
        return _Eligibility(
            StrategyEligibilityStatus.NOT_ESTIMABLE,
            ("CANDIDATE_SCORE_NOT_ESTIMABLE",),
        )
    if candidate.rank is None or candidate.rank > contract.top_k:
        return _Eligibility(
            StrategyEligibilityStatus.INELIGIBLE,
            ("STRATEGY_TOP_K_EXCLUDED",),
        )
    minimum_score = Decimal(dict(contract.parameters).get("minimum_entry_score", "0"))
    if Decimal(str(candidate.candidate_discovery_score)) < minimum_score:
        return _Eligibility(
            StrategyEligibilityStatus.INELIGIBLE,
            ("STRATEGY_MINIMUM_SCORE_REJECTED",),
        )
    return _Eligibility(
        StrategyEligibilityStatus.ELIGIBLE,
        ("STRATEGY_CANDIDATE_ELIGIBLE",),
    )


def _candidate_reference(
    runtime_input: StrategyRuntimeInput,
) -> RuntimeArtifactReference:
    envelope = runtime_input.candidate_set.envelope
    return RuntimeArtifactReference("CANDIDATE_SET", envelope.artifact_id, envelope.content_hash)


__all__ = ["MultiStrategyRuntime"]
