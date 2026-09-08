# Golden Loop V2 Scoring and Research Correctness Contract

> **Status:** HISTORICAL
> **Authority:** Frozen methodology contract for the first Golden Loop V2 campaign
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-08-20
> **Starting main:** `6f6e4681e71af49172607a75a05a94358805f63b`
> **Code Evidence:** `src/market_regime_alpha/research/cross_sectional_ranking.py`, `src/market_regime_alpha/application/historical_corpus/golden_loop.py`, `tests/research/test_cross_sectional_ranking.py`

This contract corrects cross-sectional ranking and closes canonical Evidence
wiring without changing the frozen Alpha question. The first V2 campaign keeps
the existing Target, Decision Time, Horizon, Factor definitions, Candidate and
Signal thresholds, Forecast sample floor, cost assumptions, Strategy contracts,
and Cross-Strategy Portfolio policy.

Its evidence ceiling remains `EXPLORATORY`, `PIT_INCOMPLETE`, `UNQUALIFIED`,
`FORMAL_OOS=false`, `CALIBRATED=false`, and `PRODUCTION_QUALIFIED=false`.

## 1. Scoring identity

The contract identity is
`WITHIN_SESSION_TIE_AWARE_EXACT_RATIONAL_FACTOR_PERCENTILE_MEAN_V2`. Every V2 Experiment,
session evaluation, and aggregate Evidence owner binds its exact identity and
hash.

The ranking kernel accepts an unordered mapping from opaque entity key to a
finite numeric value and a direction. Entity keys identify outputs only. A
symbol, exchange, observation ID, input order, or storage order never
participates in score, rank, percentile, tie grouping, or boundary membership.
Malformed, boolean, or non-finite numeric inputs fail closed.

## 2. Ties and normalization

- Equal values receive the same arithmetic midrank.
- For a non-constant cross-section with `n >= 2`, ascending percentile is
  `(midrank - 1) / (n - 1)`; descending percentile is its complement.
- A singleton or constant factor gives every eligible entity neutral percentile
  `0.5` and diagnostic status `CONSTANT`.
- A constant factor cannot change ordering, boundary weights, turnover, or
  economics. Its ranking contribution is `NO_RANKING_INFORMATION`.
- RankIC uses the same midrank semantics. Constant score or target input is
  `NOT_ESTIMABLE`, never an invented zero correlation.

## 3. Missingness

- Candidate transparent composites retain
  `STRICT_COMPLETE_CASE_REJECT`; rejected entities do not re-enter by neutral
  imputation.
- Historical cumulative ablation retains the frozen observation population and
  fixed declared-factor denominator. A missing factor contribution is neutral
  `0.5`, with explicit observed count, missing count, and coverage.
- A factor with no observed values is `NOT_ESTIMABLE`; it cannot change
  selection or receive incremental-lift credit.
- Partial constant coverage remains ranking-neutral while coverage is retained.
- No Universe, threshold, or sample floor may be changed to manufacture
  coverage or an estimable Forecast.

## 4. Composite and metamorphic invariants

Factor identity must be unique, and exact arithmetic makes factor-order
permutation invariant. Composite score is the frozen weighted mean of V2
percentiles using the fixed denominator and existing weights. Arithmetic
midranks and composite sums remain exact rational values until the final
order-preserving Decimal projection; finite intermediate rounding cannot split
a mathematical tie or merge distinct scores.

The following invariants are required tests:

- input permutation invariance;
- symbol-renaming equivariance;
- identical-value equality;
- constant-factor neutrality for scores, selection weights, and economics;
- positive affine-transform invariance;
- duplicate tie-group expansion preserves tied percentile semantics;
- missingness and coverage diagnostics are explicit and deterministic.

Candidate, Signal, Forecast, Strategy utility, and Portfolio allocation retain
distinct meanings. The scorer cannot manufacture a Forecast probability.

## 5. Boundary-tie selection

Ranking and Top-K selection are separate. Ranking never selects a winner from a
tie by identity.

Historical Top-K diagnostics use
`FRACTIONAL_BOUNDARY_WEIGHT_V1`:

- observations strictly above the Kth score receive one full slot;
- remaining slots are divided equally across the boundary tie group;
- weights preserve the declared K-slot exposure;
- bottom-K uses the symmetric rule;
- diagnostics record strict-above count, boundary score, group size,
  fractional weight, and best/worst boundary sensitivity.

This research selection policy does not replace or modify the canonical
Cross-Strategy Portfolio policy, which continues to consume Strategy Proposals.

## 6. Canonical runtime and Evidence flow

The existing bounded Historical runner remains the only historical execution
path:

```text
HistoricalResearchRunner
→ ResearchDecisionSessionKernel
→ HistoricalDecisionMaterializer
→ MultiStrategyHistoricalAdapter
→ PostgreSQL session components and Strategy owners
```

At the existing `PERFORMANCE` stage, V2 binds:

```text
RESEARCH_PANEL
+ MULTI_STRATEGY_CYCLE
+ CROSS_STRATEGY_PORTFOLIO
+ HISTORICAL_OUTCOME
+ Experiment / Scoring / Selection identities
→ RESEARCH_EVALUATION
→ existing Strategy feedback / attribution owner
```

The Historical Evidence Producer reloads and aggregates those canonical owners.
It does not rank observations, run Strategy logic, allocate a pseudo portfolio,
or synthesize replacement economics. When the canonical Strategy path produces
no observable action/outcome, Strategy Economics and Portfolio Performance are
`NOT_ESTIMABLE`/`NO_ACTION`.

Historical execution remains Shadow/Simulation. It never creates an observed
physical Fill or physical Position claim.

## 7. V1 lineage and anti-tuning boundary

Prior owners are immutable and remain queryable. V2 writes a separate
`METHODOLOGY_ASSESSMENT` Evidence owner that binds exact affected Phase E2/E3
references and first-pass V2 references. It records defects
`TIE_SPLIT_BY_OBSERVATION_ID_V1` and
`FINITE_DECIMAL_INTERMEDIATE_TIE_DRIFT_V2`, the replacement scoring identity,
and immutable superseded lineage. The latter was discovered only by the real
Phase E3 campaign: finite intermediate Decimal rounding changed four
bottom-boundary weights after an entirely unobserved factor was added.

The V2 Experiment changes only the hypothesis/correctness identity, scoring
contract, boundary policy, canonical Evidence wiring, and exact code revision.
Any later change to Feature, threshold, Target, Horizon, cost, or Portfolio
policy requires a new Experiment identity.

## 8. Replay and acceptance

Missing canonical Cycle, Portfolio, Outcome, Experiment, scoring, or selection
sources fail closed. Identical retries are idempotent; conflicting payloads are
rejected. Resume and replay reuse the existing journal, lease/fence, frozen
inputs, and business evaluator.

Campaign acceptance requires an isolated Phase E3 PostgreSQL dump migration
from 084 through the current head, a new immutable V2 campaign, interruption or
bounded-run resume, content-hash replay equality, and diagnostics for:

- exact zero increment from constant factors;
- absence of identity-based symbol/exchange tie splitting;
- methodology correction of affected Phase E2/E3 claims;
- persistence or rejection of Phase E3 negative results;
- exact canonical Portfolio/Evidence owner identity equality;
- Candidate, Signal, and Forecast coverage with honest `NO_ACTION` and
  `NOT_ESTIMABLE` states.

Passing this contract establishes research-correctness engineering and
reproducible exploratory evidence only. It does not establish Alpha, Formal PIT,
Formal OOS, calibrated probability, trading authority, or production
qualification.
