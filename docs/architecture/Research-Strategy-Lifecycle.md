# Research and Strategy Lifecycle

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical research/strategy responsibility split
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-12
> **Code Evidence:** `src/market_regime_alpha/application/research_evaluation`, `src/market_regime_alpha/application/research_validation`, `src/market_regime_alpha/application/shadow_research`, `src/market_regime_alpha/application/strategy_shadow`

## Lifecycle

```text
Research Universe Policy / immutable Runtime Scope
-> Canonical Dataset / Feature / State / Candidate / Signal / Forecast
-> ResearchDailySummary
-> Research Shadow decision
-> factual multi-target Outcome
-> Evaluation Dataset and complete Panel V2
-> canonical Factor Extraction
-> exploratory Ablation and capacity analysis
-> calibration fit/evaluation (not calibrated)
-> locked-partition metric computation (not Formal OOS Authority)
-> Entry research
-> Strategy Shadow Entry/Fill/Position
-> Portfolio Shadow Cash/NAV/Exposure/Cost/Attribution
-> Holding/Exit engineering assessment
-> blocked Production Admission projection
```

The same owner stages can be applied across a frozen multi-session range by the
Shared Decision Session Kernel. `HistoricalResearchRunner` journals each
session/stage in PostgreSQL, resumes under lease/fence, and replays exact owner
hashes. It is exploratory Historical Research, not a second daily Runtime and
not Formal OOS.

For free-data operation, retrospective decisions and later outcomes additionally
feed an immutable Historical Sample Dataset in PostgreSQL. The Registry Reader
may supply those already-available `UNQUALIFIED` samples to a later
Research/Shadow PathForecast. This is operational sample plumbing, not PIT/OOS
qualification or empirical validation.

## Responsibility split

- Factor Extraction reads verified canonical Dataset, FeatureBundle, State, Pool, Candidate, Signal and Forecast values. It records missingness; it does not recompute those owners.
- Runtime Scope owns the session symbol decision. It combines overlapping free
  Operational Universe facts conservatively, preserves every Provider artifact
  reference and retains `EXCLUDED`/`UNKNOWN`; downstream owners receive the
  resulting scope rather than selecting a Provider.
- Evaluation Dataset binds frozen decisions to later settlements. Panel V2 provides the complete row/slice cross-section used by factor and evaluation consumers. They are complementary, not V1/V2 competing Authorities.
- Ablation compares factor variants and incremental lift under exploratory evidence. Formal Evaluation applies frozen windows, purge/embargo, multiple-testing and sensitivity rules. Neither grants model qualification.
- Calibration fits and evaluates Platt/isotonic/binning mappings on disjoint
  partitions. The qualification owner now exists, but it remains
  `calibrated=false` until exact Formal OOS and calibration evidence satisfy its
  independently frozen policy; current evidence does not.
- Entry research evaluates Candidate-only, Candidate+Signal, Candidate+Forecast and Candidate+Intraday variants. Its strongest output is `SHADOW_ENTER`; Canonical Entry still has no `ENTER` state.
- Research Shadow freezes what the research system knew and later binds factual outcomes. It has no simulated account or execution ledger.
- Strategy Shadow owns an isolated simulated Entry/Fill/Position/Holding/Exit session. The free-data operator uses a selected-Candidate pass-through with no score threshold and a T+1 fixed-time observation contract, not tuned model parameters. Later invocations reload Entry/Fill/Position and append Holding/Exit observations until settlement. Every stored artifact has `real_trading_mutation=false`.
- Portfolio Shadow owns an independent simulated Cash/Order Intent/Fill/Position/NAV ledger under the same Strategy Shadow boundary. Top1/3/5 Equal/Score/Risk policies and all cost/capacity inputs carry explicit provenance; T+1, 100-share lots, suspension, price limits and continuous-auction constraints fail closed. It cannot write actual account or Position authorities.
- Performance/Attribution reloads the immutable Portfolio Shadow chain and emits
  content-addressed metric, monthly/yearly return and attribution rows. Missing
  denominators or dimensions remain `NOT_ESTIMABLE`; reconciliation failure is
  rejected rather than hidden in a residual.
- Exploratory Model Research freezes samples, features, targets, walk-forward
  folds, coefficients and lineage. Its executor emits raw barrier scores, not
  probabilities. A real stored research artifact makes
  `RESEARCH_MODEL_AVAILABLE=true`; Formal qualification, OOS and calibration
  remain false.
- Holding/Exit validation consumes Strategy Shadow outcomes only. It cannot mutate actual `position_books` or `manual_fills`.
- Production Admission lists missing floors. It is not an Authority and cannot reach review eligibility or authorization.

## Qualification state

The repository contains operational writers for `UNQUALIFIED` free-data
Historical Samples, exploratory model artifacts and narrow owner-specific
Formal assessment decisions. The Formal orchestration checks Provider Fact
qualification, Formal PIT, Historical Sample, Locked OOS and Calibration in
order and stops at the first missing or rejected predecessor. With current free
data it persists `BLOCKED`; it cannot invoke OOS consumption or calibration fit.
Migration 046 still prevents reference-only promotion.

## Non-claims

- no Alpha winner;
- no parameter optimization in this lifecycle;
- no formal OOS result;
- no calibrated probability;
- no Entry authorization;
- no actual Fill or Position from Strategy Shadow;
- no authenticated operator or broker readiness proof; engineering RBAC is not authentication or Production Admission.
