# WP-ALPHA-RESEARCH-01 Frozen Discovery Protocol

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Pre-registered exploratory research protocol; executable truth requires the persisted Experiment Definition and canonical PostgreSQL owners
> **Owner:** Market Regime Alpha maintainers
> **Decision Date:** 2026-08-20
> **Repository Baseline:** `main@5a441746ada08eb08310b12e34d9e0f56f56a952`
> **Evidence Ceiling:** `EXPLORATORY / PIT_INCOMPLETE / IN_SAMPLE_DISCOVERY / UNQUALIFIED / FORMAL_OOS=false / CALIBRATED=false`

## Research question

Which information observable by the frozen DecisionTime carries stable, reproducible and economically meaningful incremental information about the frozen T+1 path, and which current predictive Gate is noise, a harmful filter or only a sample selector?

No existing Market Regime, ETF, Theme, Capital, Dynamic Pool, Candidate, Signal or Forecast layer is presumed useful. Negative, inconclusive, `NOT_ESTIMABLE` and architecture-retirement conclusions are admissible outcomes.

## Frozen Discovery Dataset

This Work Package reuses the Phase E3 dataset scope only. Phase E3 results are not the Alpha baseline.

| Dimension | Frozen value |
|---|---|
| Normalized dataset owner | `historical-data-owner-c4cc4f5fd5a39248c116b3e7` / `sha256:c4cc4f5fd5a39248c116b3e72d83dac09cb7ee6466f8ef84f803e64b4c38ea77` |
| Constituent timeline | `historical-constituent-timeline:af987d1d42d9137abaab010ca6047b8a09ea27cb6d2936480566ec2fc8bb9b58` / `sha256:af987d1d42d9137abaab010ca6047b8a09ea27cb6d2936480566ec2fc8bb9b58` |
| Historical security facts | `historical-security-facts:4fc1085c2579c2fae6028636d8c506b30f1f39884440a3ebf0dad57546aa28df` |
| Context-instrument owner | `historical-context-instrument-set:d5151fdd88ba8949e173cd7e0533cdaf2e89b275b1e0663ee40518b59ba580d4` / `sha256:d5151fdd88ba8949e173cd7e0533cdaf2e89b275b1e0663ee40518b59ba580d4` |
| Context instruments | `000300.SH`, `510300.SH`; no substitute when an observation is absent |
| Decision sessions | 126 sessions, 2025-01-02 through 2025-07-11 inclusive |
| Universe | Effective-dated CSI 300 cohort, 300 symbols per Decision Session |
| DecisionTime | 14:55:00 `Asia/Shanghai` |
| Target Protocol | `outcome-target-protocol:6718c60fc274d65b69d14eb954ebb71be71605835ae0460289b628085d522fd5` / `sha256:6718c60fc274d65b69d14eb954ebb71be71605835ae0460289b628085d522fd5` |
| Discovery Target | T+1 next-session 10:30: `outcome-target:853ede76b6e80de700beb7d785f81fbb0d0801a67ed860798c63f96c7915ab6b` / matching `sha256` hash |
| Feature configuration | `feature-set-aaea2725245b1656b94dd89c` / `sha256:aaea2725245b1656b94dd89ca20a5ee5ef38e0609009825e31ab626c0cbceb01` |
| Ranking correctness | Existing Golden Loop V2 exact-rational, tie-aware arithmetic midrank contract and fractional boundary policy |
| Missingness | Explicit missing; no result-dependent imputation or silent zero |

Changing any dataset owner, date, session count, Universe, Provider, DecisionTime, Target/Horizon, cost assumption or ranking correctness contract creates another Experiment and is outside WP-ALPHA-RESEARCH-01.

## Frozen cost and capacity assumptions

The existing Phase E3 engineering-assumption policy remains unchanged:

| Parameter | Value |
|---|---:|
| Commission | 3 bps each side |
| Stamp duty | 5 bps sell side |
| Spread/slippage | 5 bps each side |
| Impact coefficient | 8 bps |
| Participation rate | 10% |
| Existing Golden comparison cost return | 0.002100 |
| Lot size | 100 shares |
| Settlement | A-share T+1 |

These assumptions are not empirically calibrated. Gross and assumed-cost net results must be reported separately.

## Experiment Definition owner

Before a Historical Research run starts, one content-addressed `RESEARCH_EXPERIMENT_DEFINITION` owner must be written and reloaded from PostgreSQL. Its semantic payload must include:

- the exact dataset, constituent-timeline, security-fact and context-instrument owner references;
- session start, session end and expected session count;
- Universe policy and 300-symbol-per-session expectation;
- DecisionTime, timezone, Target Protocol and exact T+1 10:30 Target reference;
- Feature Set and economics-policy references;
- the factor registry and family membership;
- all Gate and Candidate policy variants;
- the unchanged Golden V2 scoring/ranking contract reference;
- evaluation metrics, quantile count and Top-K set;
- the multiple-testing family and method;
- the discovery evidence ceiling and stopping rule.

The run command must bind the reloaded owner identity/hash. A mismatch fails closed. Results never mutate this owner.

## Canonical Research Panel

The Panel is an owner-resolved projection, not a second Feature implementation. For every session and symbol it must copy:

1. every canonical Feature output with Feature ID, output ID, raw value/state, availability time, missing reasons, configuration identity and compact source lineage;
2. Market Regime, ETF, Theme and Capital values/statuses from their owners;
3. Dynamic Pool membership and reasons from the Dynamic Pool owner;
4. Candidate selection status, rank, score and complete rejection reasons from the Candidate owner;
5. the existing Target, MFE/MAE, cost/economics and slice values;
6. Signal/Forecast diagnostics only as observed coverage gaps; this Work Package does not redesign those layers.

The Panel must not recompute a technical feature, infer a missing context value, substitute a Provider, or change owner availability semantics.

## Pre-registered factor families

All canonical Feature outputs enter coverage/missingness diagnostics. Research hypotheses use a frozen registry that assigns each output to one role: numeric ranked factor, categorical/bucket diagnostic, raw-level diagnostic or not-estimable.

| Family | Registered information |
|---|---|
| Price / Return | intraday return to DecisionTime; close location; gap return; high-low range; returns 1/3/5/10 |
| Volume / Amount / Turnover | volume/amount ratios and percentiles; expansion/contraction; persistence; abnormal/breakout and price-volume agreement; turnover outputs remain explicit when missing |
| Trend | moving-average distances/slopes/relative returns/alignment; MACD DIF/DEA/histogram/slopes/states; rolling-high and short-return structure |
| Volatility / Extension | high-low range, range expansion, gap extension, overextension and consecutive-up diagnostics |
| Market context | Market Regime state/score/coverage |
| ETF context | exact frozen ETF observation/state/score; absent ETF evidence remains `NOT_ESTIMABLE` |
| Theme | Theme membership/state/score/coverage |
| Capital | explicitly labelled public Capital Proxy state/score/coverage |
| Dynamic Pool / Candidate | membership, Candidate score/rank/status and Gate diagnostics; these are policy diagnostics, not hidden factors |

Raw SMA, EMA, VWAP and absolute price-level outputs are copied for lineage/coverage but are not cross-sectional Alpha hypotheses because their raw scale is not comparable. Categorical outputs use only predeclared ordinal/bucket semantics. No feature is added, removed, inverted or reclassified after outcome inspection.

## Predictive Gate ablation

Tradability and data-integrity gates always remain hard:

- suspension/non-tradable status;
- DecisionTime/PIT correctness;
- required data completeness;
- required history length;
- base liquidity eligibility;
- canonical Universe membership.

Market Regime, Theme, Capital and Dynamic Pool are predictive-policy Gates. For each Gate `G`, the same post-integrity population is evaluated under:

1. `CURRENT_HARD_GATE_G`: apply only `G` as a hard predictive filter;
2. `SOFT_FEATURE_G`: retain the population and consume `G` only as a score/factor;
3. `NO_PREDICTIVE_GATE_G`: retain the population and omit `G` from ranking.

The existing full sequential policy is separately reported as `CURRENT_HARD_CHAIN`. `NO_PREDICTIVE_GATES` is the common hard-integrity-only control. These isolated contrasts prevent first-failure ordering from being mistaken for independent Gate value.

The comparison is causal-style diagnosis over one observational Frozen Discovery Dataset, not proof of causal intervention.

## Candidate research policies

The complete pre-registered policy set is evaluated; no winner is selected and repackaged after seeing returns:

- `CURRENT_HARD_CHAIN`: current Candidate policy, unchanged;
- `HARD_INTEGRITY_PRICE_RETURN`: hard-integrity population ranked by the registered Price/Return family;
- `HARD_INTEGRITY_PRICE_VOLUME_TREND`: hard-integrity population ranked by equal-weight family percentiles;
- `SOFT_CONTEXT_CANDIDATE`: the preceding transparent technical ranking plus Market/Theme/Capital/Dynamic Pool as soft family scores.

All policies preserve exact tie-aware ranks. Candidate selection uses the frozen Top-5 policy with boundary ties and minimum population 5; evaluation additionally reports Top-1/3/5/10 without turning those diagnostic K values into changed Candidate policy.

## Evaluation and multiple testing

Every registered factor, family, Gate variant and Candidate policy emits the same metric surface:

- before/after observation and session counts, missingness and rejection rate;
- cross-sectional IC and RankIC, session distribution, mean, dispersion, ICIR and monthly/quarterly stability;
- five equal-count tie-aware buckets, bucket returns and monotonicity diagnostics;
- Top-1/3/5/10 gross, assumed-cost net, hit rate, spread, MFE and MAE;
- turnover, overlap, drawdown and capacity/fillability where estimable;
- conditional results by time, Market Regime and available non-leaky slices;
- incremental lift versus the declared control using identical observations.

The exploratory hypothesis family is `WP_ALPHA_RESEARCH_01_DISCOVERY_V1`. Benjamini-Hochberg FDR adjustment from the existing multiple-testing kernel is applied across the complete registered numeric-factor and policy comparison family. Descriptive coverage and Gate counts have no fabricated p-values. Adjusted values remain exploratory and cannot create Formal OOS authority.

## Decision vocabulary

Each predictive Gate receives exactly one research disposition:

- `KEEP_AS_HARD_GATE`: hard filtering has stable incremental economic/information value and a defensible integrity-like failure mode;
- `DEMOTE_TO_FACTOR`: soft consumption dominates hard filtering without destructive coverage loss;
- `RETEST`: evidence is mixed, unstable or underpowered;
- `RETIRE`: the Gate is estimable, adds no stable information and causes material sample/value loss.

`NOT_ESTIMABLE` maps to `RETEST`, never `RETIRE`, unless the architecture is separately retired for having no valid owner or consumer.

## Stopping and evidence rules

The stopping rule is exhaustion of the 126 frozen sessions. No threshold, factor mapping, direction, Gate variant, K, metric, cost or disposition rule may be changed because results are negative.

The final Evidence remains discovery evidence:

```text
EXPLORATORY
PIT_INCOMPLETE
IN_SAMPLE_DISCOVERY
UNQUALIFIED
FORMAL_OOS=false
CALIBRATED=false
PRODUCTION_QUALIFIED=false
```

Phase E2/E3 V1 positive ranking/lift results remain `METHODOLOGY_INVALIDATED / SUPERSEDED` and are excluded from current conclusions. WP-ALPHA-RESEARCH-02 must use a separately frozen Experiment for time, Universe or Provider validation.
