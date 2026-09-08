# WP-ALPHA-RESEARCH-01 Research Report

> **Status:** HISTORICAL
> **Evidence ceiling:** `EXPLORATORY / PIT_INCOMPLETE / IN_SAMPLE_DISCOVERY / UNQUALIFIED`
> **Run:** `historical-research-run-0e150a21c7869adc84a57af5`
> **Primary Evidence:** `historical-evidence-f9326f869186419a89e450b9@sha256:f9326f869186419a89e450b9b64923046a30677d4c3c0003f1f12060388c1fe6`
> **Last Updated:** 2026-08-21

## Conclusion

The frozen campaign found one pre-registered, estimable Candidate challenger
worth external validation: the hard-integrity population ranked by the complete
Price/Return family. Across 126 Decision Sessions it has mean forward RankIC
`0.090809`, BH-FDR `3.77e-7`, Top-5 gross `0.016907`, frozen assumed-cost net
`0.014807`, turnover `0.8368` and maximum drawdown `-0.029790`. Its quarterly
RankIC is positive in Q1 (`0.101656`), Q2 (`0.087197`) and the nine-session Q3
fragment (`0.046191`). This is discovery evidence, not Formal OOS Alpha or an
executable Strategy result.

The existing Candidate policy remains `NOT_ESTIMABLE`: it rejects every one of
37,319 hard-integrity observations. No predictive Gate earned a hard-Gate claim.
Market Regime, Theme and Capital are session-level sample selectors in this
dataset, with zero sessions containing both accepted and rejected securities;
Dynamic Pool passes the full integrity population and is confounded with the
integrity policy. All four dispositions are `RETEST`.

The strongest individual results are three intraday features:

| Factor | Mean RankIC | BH-FDR | Top-5 net | Turnover |
|---|---:|---:|---:|---:|
| `intraday_return_to_decision_time` | 0.666655 | 0 | 0.056024 | 0.9296 |
| `vwap_slope` | 0.480058 | 0 | 0.037427 | 0.9632 |
| `price_vs_vwap_return` | 0.420244 | 5.64e-307 | 0.042356 | 0.9392 |

All three use the same retrospective event-time intraday evidence class. Their
large in-sample effect, high turnover, shared source family, free-provider PIT
ceiling and absent external period make replication the next question. They are
not promoted into a model, Signal, Forecast, Strategy or Portfolio in this work
package.

## Frozen identity and execution

| Item | Frozen value |
|---|---|
| Repository base | `main@5a441746ada08eb08310b12e34d9e0f56f56a952` |
| Evaluation revision | `0d1a5a8` |
| Experiment | `research-experiment-definition:ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e` |
| Experiment hash | `sha256:ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e` |
| Command hash | `sha256:0e150a21c7869adc84a57af555fed952ce200114be095387dd6d570e70a7d7df` |
| Dataset owner | `historical-data-owner-c4cc4f5fd5a39248c116b3e7@sha256:c4cc4f5fd5a39248c116b3e72d83dac09cb7ee6466f8ef84f803e64b4c38ea77` |
| Source owner run | `historical-research-run-12e8dd606b480380dc0df356@sha256:12e8dd606b480380dc0df356ca5aa6c2fdc7b2abd6b215feca74195a50227029` |
| Sessions | 2025-01-02 through 2025-07-11; 126 |
| Universe | effective-dated CSI 300; 300 securities/session |
| DecisionTime | 14:55 Asia/Shanghai |
| Target | T+1 10:30 checkpoint from the frozen multi-horizon protocol |
| Ranking | unchanged Golden V2 exact-rational tie-aware contract `sha256:ae1a0ad8a5b9563746a4d35305d562b54d92b7b6752996cef39efd56a47200c5` |
| Multiple testing | one 62-hypothesis `WP_ALPHA_RESEARCH_01_DISCOVERY_V1` family; Benjamini-Hochberg FDR |

The same Historical Research Runtime completed 126/126 sessions, persisted the
new Panel/Evaluation through the existing `PERFORMANCE` stage, and passed exact
report and deterministic replay. SCOPE through OUTCOME reloaded the exact
PostgreSQL source component owners and every reuse receipt records
`CANONICAL_SOURCE_OWNERS_REUSED_METHODOLOGY_ONLY`. No new runner, scheduler,
backtest authority or production business kernel was introduced.

The registered normalized-dataset locator no longer has a physical Parquet
package on the local filesystem. This campaign therefore did not claim a new
physical package verification: it reused already registered PostgreSQL
component owners and records
`PHYSICAL_PACKAGE_NOT_REOPENED_CANONICAL_OWNER_COMPONENT_REUSE` as an Evidence
limitation.

## Methodology correction before conclusion

Initial run `historical-research-run-a09d88080459cf300673ca8d` compared hard
Gate results across different temporal subsets and omitted the implemented
`NO_PREDICTIVE_GATES` policy from the persisted Candidate registry. Its Alpha
Evidence `historical-evidence-e2d71ea0eb80a8cab86ed654@sha256:e2d71ea0eb80a8cab86ed654e36d0024624122d43b8bd3aeff0ed93ff6a3d7a1`
is immutable but `METHODOLOGY_INVALIDATED / SUPERSEDED` and is explicitly bound
as superseded by the final command.

The final protocol requires at least 20 same-session mixed populations and 20
paired RankIC/Top-5 net contrasts before a hard Gate can receive an estimable
incremental disposition. No date, Universe, Provider, DecisionTime, Target,
cost, Factor direction or Golden ranking rule changed during the correction.

## Canonical Panel and coverage

Panel v2 projects all 70 canonical Feature outputs rather than only `return_3`
and `amount_ratio_5`: 49 pre-registered numeric ranked hypotheses, 11 raw-level
diagnostics and 10 categorical diagnostics. Every value retains Feature/output
identity, state, DecisionTime availability, timeframe, configuration id/hash,
source count/lineage, missing reasons and limitations. Candidate status, rank,
score, complete rejection reasons, hard-integrity decision and four predictive
Gate diagnostics are also preserved.

| Context/owner projection | Observations | Coverage |
|---|---:|---:|
| Price | 37,359 | 0.999572 |
| Volume | 37,319 | 0.998502 |
| Market Regime | 22,529 | 0.602783 |
| Theme | 37,077 | 0.992027 |
| Dynamic Pool | 37,375 | 1.000000 |
| ETF | 0 | 0 |
| Capital | 0 | 0 |
| Candidate score | 0 | 0 |
| Signal | 0 | 0 |
| Forecast | 0 | 0 |

There are 37,375 complete target observations and 37,319 hard-integrity
observations. ETF, Capital and current Candidate scoring remain
`NOT_ESTIMABLE`; public Capital proxies are not interpreted as hidden
institutional intent.

## Candidate policies

| Policy | After / before | Mean RankIC | BH-FDR | Bucket monotonicity | Top-5 gross | Top-5 net | Turnover | Max drawdown | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `CURRENT_HARD_CHAIN` | 0 / 37,319 | NA | NA | NA | NA | NA | 1.0000 | NA | `NOT_ESTIMABLE` |
| `HARD_INTEGRITY_PRICE_RETURN` | 37,319 / 37,319 | 0.090809 | 3.77e-7 | -0.931471 | 0.016907 | 0.014807 | 0.8368 | -0.029790 | exploratory `POSITIVE` |
| `HARD_INTEGRITY_PRICE_VOLUME_TREND` | 37,319 / 37,319 | 0.027256 | 0.127190 | -0.865356 | 0.007169 | 0.005069 | 0.8336 | -0.112231 | `INCONCLUSIVE` |
| `NO_PREDICTIVE_GATES` | 37,319 / 37,319 | 0.027256 | 0.127190 | -0.865356 | 0.007169 | 0.005069 | 0.8336 | -0.112231 | `INCONCLUSIVE` control |
| `SOFT_CONTEXT_CANDIDATE` | 37,319 / 37,319 | 0.027256 | 0.127190 | -0.865356 | 0.007169 | 0.005069 | 0.8336 | -0.112231 | no lift over control |

Bucket 1 contains the highest score, so a useful higher-is-better policy has
negative correlation between bucket number and return. For the Price/Return
challenger, bucket returns are `0.003681`, `0.000775`, `0.001015`, `0.000030`
and `-0.003011`; positive-session RankIC ratio is `0.690476`, RankIC IR is
`0.496945`, Top-5 hit rate is `0.687302`, spread is `0.025900`, MFE is
`0.032478`, MAE is `0.002984`, and the diagnostic capacity ceiling is about
CNY 128.72 million under the frozen assumptions.

## Gate ablation and dispositions

| Gate | Current-hard after / before | Rejection | Pass-all sessions | Reject-all sessions | Mixed sessions | Current-hard RankIC | Current-hard Top-5 net | Disposition |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Capital | 0 / 37,319 | 1.000000 | 0 | 126 | 0 | NA | NA | `RETEST` |
| Dynamic Pool | 37,319 / 37,319 | 0 | 126 | 0 | 0 | 0.027256 | 0.005069 | `RETEST` |
| Market Regime | 22,493 / 37,319 | 0.397278 | 76 | 50 | 0 | 0.028284 | 0.005102 | `RETEST` |
| Theme | 23,682 / 37,319 | 0.365417 | 80 | 46 | 0 | 0.041710 | 0.006137 | `RETEST` |

For Market Regime and Theme, the displayed hard metrics describe pass-period
conditional subsets only. Paired hard-versus-none RankIC and net lift are
`NOT_ESTIMABLE` because no session has both accepted and rejected securities.
Their soft scores are constant within each session and have exactly zero RankIC
and Top-5 net lift over the no-predictive control. Capital rejects every session.
Dynamic Pool passes every post-integrity row and remains integrity-confounded.
Accordingly, none is `KEEP_AS_HARD_GATE`, `DEMOTE_TO_FACTOR` or `RETIRE` from
this dataset.

## Complete numeric Factor registry result

All directions were frozen as higher raw value before outcomes were inspected.
The table reports mean session RankIC, BH-FDR-adjusted p-value and Top-5 frozen
assumed-cost net. `NA` is preserved rather than converted to zero. Twenty-eight
of 49 numeric factors have BH-FDR at or below 0.05: three positive and 25
negative. A significant negative result is not direction-flipped into a new
hypothesis in this campaign.

| Factor | Family | Mean RankIC | BH-FDR | Top-5 net |
|---|---|---:|---:|---:|
| `technical.intraday_price_action.v1:intraday_return_to_decision_time` | PRICE_RETURN | 0.666655 | 0 | 0.056024 |
| `technical.macd.v1:dea` | TREND | -0.020097 | 0.307354 | -0.003196 |
| `technical.macd.v1:dea_slope` | TREND | -0.030132 | 0.127190 | -0.003607 |
| `technical.macd.v1:dif` | TREND | -0.026319 | 0.188429 | -0.003855 |
| `technical.macd.v1:dif_slope` | TREND | -0.044921 | 0.020076 | -0.001223 |
| `technical.macd.v1:histogram` | TREND | -0.030132 | 0.127190 | -0.003607 |
| `technical.macd.v1:histogram_consecutive_direction` | TREND | -0.038042 | 0.004535 | 0.000046 |
| `technical.moving_average.v2:distance_ema12_ema26` | TREND | -0.028245 | 0.187814 | -0.003525 |
| `technical.moving_average.v2:distance_sma5_sma20` | TREND | -0.022249 | 0.258302 | -0.004975 |
| `technical.moving_average.v2:ma_slope_20` | TREND | -0.043493 | 0.032157 | -0.003546 |
| `technical.moving_average.v2:ma_slope_5` | TREND | -0.059064 | 0.001993 | -0.004197 |
| `technical.moving_average.v2:ma_slope_60` | TREND | -0.028139 | 0.136277 | -0.004949 |
| `technical.moving_average.v2:price_vs_ema20_return` | TREND | -0.049058 | 0.022749 | -0.004610 |
| `technical.moving_average.v2:price_vs_sma10_return` | TREND | -0.045595 | 0.028021 | -0.004561 |
| `technical.moving_average.v2:price_vs_sma20_return` | TREND | -0.043173 | 0.040345 | -0.005445 |
| `technical.moving_average.v2:price_vs_sma5_return` | TREND | -0.063691 | 0.000769 | -0.001334 |
| `technical.overheat_extension.v1:consecutive_up_sessions` | VOLATILITY_EXTENSION | -0.042854 | 0.001993 | -0.003291 |
| `technical.overheat_extension.v1:distance_from_rolling_high` | TREND | -0.004356 | 0.833675 | -0.002965 |
| `technical.overheat_extension.v1:gap_extension` | VOLATILITY_EXTENSION | -0.009829 | 0.530780 | -0.001697 |
| `technical.overheat_extension.v1:price_vs_sma10` | TREND | -0.045595 | 0.028021 | -0.004561 |
| `technical.overheat_extension.v1:price_vs_sma5` | TREND | -0.063691 | 0.000769 | -0.001334 |
| `technical.overheat_extension.v1:range_expansion` | VOLATILITY_EXTENSION | -0.011625 | 0.310712 | -0.003758 |
| `technical.overheat_extension.v1:short_return` | TREND | -0.061067 | 0.000980 | -0.003061 |
| `technical.overheat_extension.v1:volume_price_overextension` | VOLATILITY_EXTENSION | -0.066039 | 0.000379 | -0.002388 |
| `technical.price_action.v1:close_location_value` | PRICE_RETURN | -0.036774 | 0.030250 | -0.002452 |
| `technical.price_action.v1:gap_return` | PRICE_RETURN | -0.009829 | 0.530780 | -0.001697 |
| `technical.price_action.v1:high_low_range` | VOLATILITY_EXTENSION | -0.048655 | 0.006040 | -0.004934 |
| `technical.price_action.v1:return_1` | PRICE_RETURN | -0.035733 | 0.057171 | -0.001582 |
| `technical.price_action.v1:return_10` | PRICE_RETURN | -0.033422 | 0.119658 | -0.006567 |
| `technical.price_action.v1:return_3` | PRICE_RETURN | -0.061067 | 0.000980 | -0.003061 |
| `technical.price_action.v1:return_5` | PRICE_RETURN | -0.059016 | 0.001993 | -0.004113 |
| `technical.session_vwap.v1:distance_from_vwap` | TREND | 0.046899 | 0.091869 | 0.019171 |
| `technical.session_vwap.v1:price_vs_vwap_return` | TREND | 0.420244 | 5.64e-307 | 0.042356 |
| `technical.session_vwap.v1:vwap_slope` | TREND | 0.480058 | 0 | 0.037427 |
| `technical.volume_amount_structure.v1:amount_contraction` | VOLUME_AMOUNT_TURNOVER | 0.005304 | 0.608385 | -0.001475 |
| `technical.volume_amount_structure.v1:amount_expansion` | VOLUME_AMOUNT_TURNOVER | -0.020444 | 0.095900 | -0.004937 |
| `technical.volume_amount_structure.v1:amount_percentile_20` | VOLUME_AMOUNT_TURNOVER | -0.043507 | 0.000847 | -0.004998 |
| `technical.volume_amount_structure.v1:amount_ratio_10` | VOLUME_AMOUNT_TURNOVER | -0.039822 | 0.001762 | -0.003202 |
| `technical.volume_amount_structure.v1:amount_ratio_20` | VOLUME_AMOUNT_TURNOVER | -0.044601 | 0.001563 | -0.002995 |
| `technical.volume_amount_structure.v1:amount_ratio_5` | VOLUME_AMOUNT_TURNOVER | -0.035577 | 0.003369 | -0.004872 |
| `technical.volume_amount_structure.v1:turnover_expansion` | VOLUME_AMOUNT_TURNOVER | NA | NA | NA |
| `technical.volume_amount_structure.v1:turnover_persistence` | VOLUME_AMOUNT_TURNOVER | NA | NA | NA |
| `technical.volume_amount_structure.v1:volume_contraction` | VOLUME_AMOUNT_TURNOVER | 0.004767 | 0.630851 | -0.001073 |
| `technical.volume_amount_structure.v1:volume_expansion` | VOLUME_AMOUNT_TURNOVER | -0.019917 | 0.102750 | -0.004477 |
| `technical.volume_amount_structure.v1:volume_percentile_20` | VOLUME_AMOUNT_TURNOVER | -0.038507 | 0.001921 | -0.004248 |
| `technical.volume_amount_structure.v1:volume_persistence` | VOLUME_AMOUNT_TURNOVER | -0.005778 | 0.546747 | -0.001273 |
| `technical.volume_amount_structure.v1:volume_ratio_10` | VOLUME_AMOUNT_TURNOVER | -0.035515 | 0.003480 | -0.002937 |
| `technical.volume_amount_structure.v1:volume_ratio_20` | VOLUME_AMOUNT_TURNOVER | -0.039257 | 0.002661 | -0.002261 |
| `technical.volume_amount_structure.v1:volume_ratio_5` | VOLUME_AMOUNT_TURNOVER | -0.031055 | 0.010417 | -0.004777 |

The other 21 canonical outputs remain lineage-complete diagnostics rather than
numeric hypotheses: 11 raw EMA/SMA/VWAP levels and 10 categorical MACD,
moving-average, VWAP and price-volume states. This prevents raw price levels or
unordered states from entering a misleading cross-sectional rank test.

## Evidence classification and next boundary

The five final Evidence artifacts are:

| Kind | Classification | Identity |
|---|---|---|
| `CORPUS_SUMMARY` | `INCONCLUSIVE` | `historical-evidence-7eb7450d9a7465a8b9976cc0@sha256:7eb7450d9a7465a8b9976cc03006fc62b7efc391cfa6e75f5a11d9c436a7cc6d` |
| `ALPHA_ABLATION` | exploratory `POSITIVE` | `historical-evidence-f9326f869186419a89e450b9@sha256:f9326f869186419a89e450b9b64923046a30677d4c3c0003f1f12060388c1fe6` |
| `STRATEGY_ECONOMICS` | `NOT_ESTIMABLE` | `historical-evidence-963062635ad3b0ffd2321f0c@sha256:963062635ad3b0ffd2321f0ccaea2d5a2d73ca58e8e6d17bca2e6ec4bfb7c07c` |
| `PORTFOLIO_PERFORMANCE` | `NOT_ESTIMABLE` | `historical-evidence-4f23c7166c1fbcaea3863b31@sha256:4f23c7166c1fbcaea3863b31d23aed5e3a0b6aa3525a3d91b5d88ebd951a05c2` |
| `METHODOLOGY_ASSESSMENT` | `INCONCLUSIVE` | `historical-evidence-2861c80f37f28e4941680d80@sha256:2861c80f37f28e4941680d80af5173374ee235e4c2c5bd59e630a8b55fe20e81` |

Engineering execution, PostgreSQL persistence, report, exact replay, tests and
build can be qualified for this scope. Research qualification remains blocked:

```text
FORMAL_PIT_ESTABLISHED              = false
FORMAL_OOS_ALPHA_ESTABLISHED        = false
CALIBRATED_PROBABILITY_ESTABLISHED  = false
STRATEGY_ECONOMICS_ESTIMABLE        = false
PORTFOLIO_PERFORMANCE_ESTIMABLE     = false
PRODUCTION_QUALIFIED                = false
```

## Qualification record

`uv sync --frozen --extra dev --extra postgres`, documentation inventory and
link checks, documentation tests, platform tests, full pytest, full ruff, full
mypy, package build and `git diff --check` pass. The final full suite used a
fresh PostgreSQL database and retained the six pre-existing pandas
fragmentation warnings from legacy Top-1000 tests.

The first final-suite attempt on a heavily reused test database had one
`LockNotAvailable` while an unchanged repository test reapplied migrations.
Lock inspection showed only catalog autovacuum workers; the exact failing node
passed immediately in isolation and the entire platform/full suite then passed
on the fresh database without changing code, tests, timeouts or PostgreSQL
settings. The first attempt remains recorded as an environment failure. GitHub
Actions is disabled and supplies no CI qualification.

The permitted next research step is a separately frozen
`WP-ALPHA-RESEARCH-02 / External Validation` experiment for the exact surviving
Price/Return challenger and its three intraday contributors. Time, Universe or
Provider expansion must not be appended to this run. Conditional Forecast,
Strategy optimization and Portfolio expansion remain deferred until external
Candidate evidence exists.
