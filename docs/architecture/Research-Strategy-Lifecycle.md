# Research and Strategy Lifecycle

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical research/strategy responsibility split
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `src/market_regime_alpha/application/research_evaluation`, `src/market_regime_alpha/application/research_validation`, `src/market_regime_alpha/application/shadow_research`, `src/market_regime_alpha/application/strategy_shadow`

## Lifecycle

```text
Canonical Dataset / Feature / State / Candidate / Signal / Forecast
-> ResearchDailySummary
-> Research Shadow decision
-> factual multi-target Outcome
-> Evaluation Dataset and complete Panel V2
-> canonical Factor Extraction
-> exploratory Ablation and capacity analysis
-> calibration fit/evaluation (not calibrated)
-> locked-partition metric computation (not Formal OOS Authority)
-> Entry research
-> Strategy Shadow
-> Holding/Exit engineering assessment
-> blocked Production Admission projection
```

## Responsibility split

- Factor Extraction reads verified canonical Dataset, FeatureBundle, State, Pool, Candidate, Signal and Forecast values. It records missingness; it does not recompute those owners.
- Evaluation Dataset binds frozen decisions to later settlements. Panel V2 provides the complete row/slice cross-section used by factor and evaluation consumers. They are complementary, not V1/V2 competing Authorities.
- Ablation compares factor variants and incremental lift under exploratory evidence. Formal Evaluation applies frozen windows, purge/embargo, multiple-testing and sensitivity rules. Neither grants model qualification.
- Calibration fits and evaluates Platt/isotonic/binning mappings on disjoint partitions. It remains `calibrated=false` until a future owner-resolving writer exists.
- Entry research evaluates Candidate-only, Candidate+Signal, Candidate+Forecast and Candidate+Intraday variants. Its strongest output is `SHADOW_ENTER`; Canonical Entry still has no `ENTER` state.
- Research Shadow freezes what the research system knew and later binds factual outcomes. It has no simulated account or execution ledger.
- Strategy Shadow owns an isolated simulated Entry/Fill/Position/Holding/Exit session. Every stored artifact has `real_trading_mutation=false`.
- Holding/Exit validation consumes Strategy Shadow outcomes only. It cannot mutate actual `position_books` or `manual_fills`.
- Production Admission lists missing floors. It is not an Authority and cannot reach review eligibility or authorization.

## Qualification state

The repository contains engineering mechanics for Historical Sample, Calibration, Entry, Holding/Exit and Strategy Shadow assessment. It deliberately contains no public function that converts a reference tuple into a qualified artifact. Migration 046 enforces that choice at the database layer.

The next legitimate implementation is a set of narrow owner-specific writers, added only after real inputs exist. A universal evidence resolver or a caller-supplied “resolved” DTO would recreate the same false-Authority problem.

## Non-claims

- no Alpha winner;
- no parameter optimization in this lifecycle;
- no formal OOS result;
- no calibrated probability;
- no Entry authorization;
- no actual Fill or Position from Strategy Shadow;
- no operator, RBAC or broker readiness proof.
