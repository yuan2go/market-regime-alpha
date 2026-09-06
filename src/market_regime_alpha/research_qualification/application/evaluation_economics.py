"""Acquire exact Outcome price facts after the Evaluation input UoW closes."""

from dataclasses import replace
from uuid import UUID

from market_regime_alpha.outcome.ports.queries import OutcomeEpisodePriceReadPort
from market_regime_alpha.research_qualification.domain.episode_formula import episode_contract
from market_regime_alpha.research_qualification.domain.evaluation_computation import EvaluationMetricInputs
from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError


def acquire_episode_prices(
    inputs: tuple[EvaluationMetricInputs, ...], owner: OutcomeEpisodePriceReadPort | None,
) -> tuple[EvaluationMetricInputs, ...]:
    cache = {}
    acquired = []
    for item in inputs:
        formula = item.metric.formula
        if formula is None or formula.formula_version != 2:
            acquired.append(item)
            continue
        if owner is None:
            raise EvaluationReconciliationError("V2 requires the canonical Outcome price owner")
        _, entry, exit = episode_contract(formula)
        identities = tuple(sorted({UUID(str(row[2])) for row in item.source_rows}, key=str))
        key = identities, entry, exit
        if key not in cache:
            facts = owner.episode_prices(identities, entry, exit)
            if len(facts) != len(identities) or {fact.revision_id for fact in facts} != set(identities):
                raise EvaluationReconciliationError("Outcome price owner returned an incomplete roster")
            cache[key] = {fact.revision_id: fact for fact in facts}
        acquired.append(replace(item, source_rows=tuple((*row, cache[key][row[2]]) for row in item.source_rows)))
    return tuple(acquired)
