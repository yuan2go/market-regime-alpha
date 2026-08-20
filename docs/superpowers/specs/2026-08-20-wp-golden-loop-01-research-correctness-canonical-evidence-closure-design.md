# WP-GOLDEN-LOOP-01 Research Correctness and Canonical Evidence Closure

> **Status:** HISTORICAL

**Approval state:** APPROVED
**Approved:** 2026-08-20
**Starting main:** `6f6e4681e71af49172607a75a05a94358805f63b`
**Evidence ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_OOS_FALSE`, `PRODUCTION_AUTHORIZED_FALSE`

## Objective

Close the first Golden Alpha Proof vertical slice without changing the frozen
Alpha question. The work corrects cross-sectional ranking, makes the corrected
methodology a new immutable Experiment, and makes Historical Evidence consume
the same canonical Strategy, Portfolio, Outcome, cost, and attribution owners
that the Historical bounded runner produced.

The first V2 campaign changes only research correctness and canonical wiring.
Target, Decision Time, Horizon, Factor definitions, Candidate and Signal
thresholds, Forecast sample floors, cost assumptions, capacity assumptions,
Strategy contracts, and Cross-Strategy Portfolio policy remain unchanged.

## Established baseline

The current implementation has two correctness breaks.

1. `WITHIN_SESSION_FACTOR_PERCENTILE_MEAN_V1` orders equal factor values by
   `observation_id` and assigns unequal percentiles. Shared ETF, Theme, and
   Market Regime values therefore create stock-code pseudo-ranking. Phase E2's
   recorded positive Portfolio result is methodology-invalidated.
2. `MultiStrategyHistoricalAdapter` persists `MULTI_STRATEGY_CYCLE` and
   `CROSS_STRATEGY_PORTFOLIO`, but `HistoricalEvidenceProducer` ignores them and
   rebuilds a pseudo portfolio from `RESEARCH_PANEL`.

Phase E3 remains negative under a read-only tie-aware diagnostic recomputation.
That diagnostic is not a new Evidence Owner and cannot supersede V1 by itself.

## Scope and non-goals

### In scope

- One shared pure cross-sectional ranking kernel used by active Candidate,
  transparent Baseline, PIT replication Baseline, and Historical Ablation
  consumers.
- A frozen V2 Scoring and Research Correctness Contract.
- A separately versioned Top-K boundary-tie selection policy and sensitivity
  diagnostics.
- A new immutable Experiment identity that preserves every V1 owner.
- An explicit methodology-assessment Evidence owner linking affected Phase E2
  and Phase E3 Evidence to the V2 correction.
- A run-owned `RESEARCH_EVALUATION` component produced inside the existing
  Historical bounded runner.
- Historical Strategy simulation outcomes and attribution bound to canonical
  Multi-Strategy Cycle, Cross-Strategy Portfolio, Historical Outcome, and cost
  owners.
- Phase E3 Authority dump migration from 084 to the repository migration head,
  a fresh V2 campaign, resume/replay/equivalence proof, and documented results.

### Out of scope

- Alpha parameter optimization, Feature selection, threshold changes, Forecast
  floor changes, cost calibration, Portfolio policy tuning, or OOS reuse.
- A second scheduler, runtime, backtest engine, database Authority, or Strategy
  implementation.
- Observed Fill or physical Position claims. Historical execution remains
  Shadow/Simulation and retains `NOT_REAL_FILL`.
- Broker integration, production admission, automatic Champion changes, and
  automatic model revision.

## V2 Scoring and Research Correctness Contract

The contract identity is
`WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2`. It is frozen into the V2
Experiment and emitted in every session evaluation and aggregate Evidence
owner.

### Ranking input and identity

- The kernel accepts an unordered mapping from opaque entity key to a finite
  numeric value plus direction.
- Entity keys identify outputs only. They never participate in score, rank,
  percentile, tie grouping, or boundary membership.
- Reordering inputs or renaming entity keys while preserving the value mapping
  must produce the correspondingly permuted result.
- Boolean, non-finite, and malformed numeric inputs fail closed before ranking.

### Ties and normalization

- Equal numeric values receive the same arithmetic midrank.
- For a non-constant cross-section with `n >= 2`, ascending percentile is
  `(midrank - 1) / (n - 1)` and descending percentile is its complement.
- A singleton or constant factor receives the neutral percentile `0.5` for all
  eligible entities and the diagnostic status `CONSTANT`.
- Constant factors cannot change score ordering, boundary weights, turnover,
  or Portfolio economics. Their incremental ranking value is
  `NO_RANKING_INFORMATION`, not a positive empirical result.
- RankIC uses the same midrank semantics. A constant score or constant target
  is `NOT_ESTIMABLE`, never zero correlation by invention.

### Missingness

- Candidate transparent composites retain their frozen
  `STRICT_COMPLETE_CASE_REJECT` population policy. Rejected entities remain
  explicit and cannot silently re-enter through neutral imputation.
- Historical cumulative ablation retains the same observation population but
  uses a fixed declared-factor denominator. A missing non-constant factor
  contributes neutral `0.5` and is recorded in coverage and missingness
  diagnostics.
- A factor with zero observed values is `NOT_ESTIMABLE`; it contributes neutral
  `0.5`, cannot change selection, and cannot receive incremental-lift credit.
- A partially observed constant factor remains ranking-neutral while its
  observed count, missing count, and coverage are preserved.
- No layer may lower a sample floor or change the eligible Universe to turn
  missingness into apparent Alpha.

### Composite scoring

- Component order is canonicalized by declared Factor identity.
- The composite is the frozen weighted mean of V2 percentiles using the fixed
  declared denominator and the existing weights.
- Adding a constant factor, multiplying all weights by a common positive
  scalar, permuting rows, or renaming symbols cannot change relative ordering
  or boundary weights.
- Candidate score, Signal score, Forecast score, and Strategy utility remain
  distinct semantics. V2 does not manufacture Forecast probability.

## Boundary-tie selection policy

Ranking and selection are separate operations. Ranking returns equal scores for
ties and never picks a winner by symbol or observation identity.

Historical Top-K research metrics use the versioned
`FRACTIONAL_BOUNDARY_WEIGHT_V1` policy:

- entities strictly above the Kth score receive one full slot;
- the remaining slots are divided equally across every entity in the boundary
  tie group;
- weights sum to the same K-slot exposure without selecting an arbitrary
  symbol;
- bottom-K uses the symmetric rule;
- gross, cost, net, MFE, MAE, hit rate, turnover, and drawdown use the resulting
  fractional weights;
- diagnostics report strict-above count, boundary score, boundary group size,
  fractional slot weight, and metric bounds for choosing the best or worst
  boundary members.

The canonical Cross-Strategy Portfolio policy is not changed by this work. It
continues to consume Strategy Proposals. Any proposal-level equal-utility
contention remains visible as Portfolio attribution rather than being resolved
inside the ranking kernel.

## Canonical data flow

The existing Historical bounded runner remains the only Historical execution
path:

```text
HistoricalResearchRunner
  -> ResearchDecisionSessionKernel
  -> HistoricalDecisionMaterializer
  -> MultiStrategyHistoricalAdapter
  -> PostgreSQL immutable session components and Strategy owners
```

V2 extends the existing `PERFORMANCE` stage, after the base materializer has
produced `RESEARCH_PANEL`:

```text
RESEARCH_PANEL
  + MULTI_STRATEGY_CYCLE
  + CROSS_STRATEGY_PORTFOLIO
  + HISTORICAL_OUTCOME
  + frozen V2 Experiment/Scoring/Selection identities
  -> GoldenLoopSessionEvaluator
  -> RESEARCH_EVALUATION component
  -> StrategyPathOutcome where observable
  -> StrategyFeedbackArtifact, including NOT_ESTIMABLE/NO_ACTION
```

`RESEARCH_EVALUATION` is a content-addressed Historical session component, not
a new Authority hierarchy. Its source bindings must include the exact panel,
cycle, portfolio, outcome, Experiment, scoring contract, and selection policy
references. PostgreSQL reload verifies those references and hashes.

The Evidence Producer becomes an aggregator and verifier only:

- it loads `RESEARCH_EVALUATION` owners in canonical session order;
- it verifies one V2 Experiment, scoring contract, and selection policy;
- it aggregates stored sufficient statistics and canonical owner identities;
- it never computes factor ranks, Strategy actions, Portfolio allocation, or
  replacement economics;
- Strategy Economics and Portfolio Performance use accepted canonical
  Portfolio weights joined to the exact Historical Outcome/cost owner;
- no accepted proposal produces `NO_ACTION` and `NOT_ESTIMABLE`, not a synthetic
  trade.

## Methodology invalidation and supersession

V1 Evidence remains immutable and queryable. Migration 089 extends the existing
Historical Evidence enum with `METHODOLOGY_ASSESSMENT`; it does not update or
delete old rows.

The V2 campaign writes one assessment owner containing:

- exact affected Phase E2 and Phase E3 Evidence references;
- defect identity `TIE_SPLIT_BY_OBSERVATION_ID_V1`;
- status `METHODOLOGY_INVALIDATED` for ranking-dependent Alpha Ablation and
  Portfolio Performance conclusions;
- status `UNAFFECTED_BY_RANKING_DEFECT` only for evidence proven independent of
  the scorer, such as corpus coverage;
- the V2 Experiment, scoring contract, selection policy, and corrected Evidence
  references;
- the relation `SUPERSEDED_FOR_METHODOLOGY`, which does not imply a more
  favorable empirical result.

Evidence queries and reports must surface the assessment before interpreting a
V1 conclusion. Documentation records the exact IDs; prose alone is not the
invalidation Authority.

## Experiment identity and anti-tuning boundary

The V2 Experiment reuses the Phase E3 Target Protocol, Decision Time, frozen
Feature configuration, economics policy set, data owner, calendar, Universe,
thresholds, and random seed. It changes only:

- primary hypothesis identity from V1 to V2 correctness;
- scoring contract identity;
- Top-K boundary selection policy identity;
- canonical Evidence wiring identity;
- current code revision.

The verifier accepts the old Phase E3 Experiment for replay only and the exact
new Golden Loop V2 Experiment for new runs. It does not accept arbitrary
variants. Any later Feature, threshold, Target, Horizon, cost, or Portfolio
change requires another Experiment identity.

## Failure handling and replay

- Missing canonical cycle, portfolio, outcome, scoring, or Experiment sources
  fails the session stage closed.
- Duplicate writes are idempotent only when hash and payload are identical.
- Partial runs resume through the existing journal lease/fence and stage
  receipts; no new recovery mechanism is introduced.
- Replay reloads frozen source owners and recomputes through the same evaluator,
  then compares ordered IDs, hashes, payloads, source bindings, Evidence, and
  metrics.
- A Phase E3 market-data or owner gap blocks only the affected metric and is
  represented as `NOT_ESTIMABLE`; it does not authorize fixture substitution.

## Validation

### Metamorphic correctness

- input permutation invariance;
- symbol-renaming equivariance;
- identical values receive identical percentile and rank;
- constant-factor neutrality for scores, boundary weights, and economics;
- positive affine-transform invariance;
- duplicate-value group expansion preserves tied percentile semantics;
- fractional boundary weights are permutation and symbol invariant;
- missingness status/coverage changes are explicit and deterministic.

### Architecture and persistence

- Candidate, transparent Baseline, PIT Baseline, and Ablation import the shared
  kernel; repository architecture tests reject private duplicate percentile
  implementations in these active paths.
- Evidence Producer tests prove it cannot produce V2 Evidence without canonical
  Evaluation, Cycle, Portfolio, Outcome, and feedback sources.
- PostgreSQL tests cover migration 089, immutable component/evidence writes,
  lineage reload, idempotency, conflict rejection, and replay equality.
- Simulation outcomes retain `NOT_REAL_FILL`, and no physical Position owner is
  written.

### Campaign acceptance

The isolated Phase E3 Authority dump must prove migration 084 through the new
head. The fresh V2 run must complete, resume/replay must match ordered owner
sets by SHA-256, and the report must answer:

- whether constant Factors have exactly zero ranking increment;
- whether symbol/exchange-prefix concentration attributable to tie splitting
  disappears;
- how Phase E2's old positive result is corrected;
- whether Phase E3 remains negative;
- whether canonical Portfolio and Evidence reference the same owner identities;
- exact Candidate, Signal, and Forecast coverage and resulting
  `NO_ACTION`/`NOT_ESTIMABLE` status.

All repository quality gates are run and reported individually as `PASS`,
`FAIL`, `NOT_RUN`, or `BLOCKED`. Passing local tests or replay does not establish
Formal PIT, Formal OOS, calibrated Forecast, Alpha qualification, trading
authority, or production qualification.

## Architecture compression decisions

- **MERGE:** Candidate composite and Historical Ablation percentile algorithms
  into one pure kernel.
- **DELETE:** private duplicate active-path rank-percentile implementations after
  consumer migration.
- **REFACTOR:** Evidence Producer from business evaluator to owner aggregator.
- **KEEP:** one Continuous Runtime, one Historical bounded runner, PostgreSQL
  Authority, existing Strategy Runtime, existing Portfolio policy, and existing
  Outcome/cost semantics.
- **DEFER:** broad cleanup of unrelated legacy ranking/statistics helpers. They
  are outside the Golden Loop consumer graph and require separate evidence.
