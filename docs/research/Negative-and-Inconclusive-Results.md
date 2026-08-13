# Negative and Inconclusive Results

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Current registry of failed, blocked or insufficient research claims
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-13
> **Code Evidence:** `src/market_regime_alpha/application/historical_corpus`, `src/market_regime_alpha/application/research_evaluation`

| Claim | Current result | Evidence authority |
|---|---|---|
| The tested UP context improves frozen B1-E Candidate excess | Primary hypothesis not supported | exploratory |
| Any MR-2B secondary is a confirmed winner | No secondary passed the required authority | exploratory |
| B1-E is Formal OOS Alpha | Not established | none |
| Qualified Xuntou PIT replication ran on real input | Blocked by external input/runtime | external blocker |
| Entry Path Target proves an Entry model | False; infrastructure only | contract/test |
| Legacy Dividend-T proves generalizable Alpha | Not established | legacy/exploratory |
| Passing engineering tests proves Production readiness | False | engineering only |
| Current Calibration output is a probability | False; `calibrated=false` | engineering only |
| Current Strategy Shadow proves Holding/Exit | False; engineering floors only | engineering only |
| Phase E Pilot Price-only baseline has economic value | `NEGATIVE`: RankIC -0.01652; gross 0.000935, engineering-assumption cost 0.002100, net -0.001165 | six-stock real free-data Pilot |
| Phase E Pilot Volume and Market Regime establish net Alpha | `INCONCLUSIVE`: incremental net lift +0.000070 and +0.000196, but both variants remain net negative | six-stock real free-data Pilot |
| Phase E Pilot Theme and Dynamic Pool add value | `NEGATIVE`: incremental net lift -0.000350 and -0.000228 | six-stock real free-data Pilot |
| Phase E Pilot ETF and Capital add zero value | `NOT_ESTIMABLE`, not zero: BaoStock returned no requested ETF history, leaving both factor families unobserved | six-stock real free-data Pilot |
| Phase E Pilot Candidate, Signal and Forecast add zero value | `NOT_ESTIMABLE`, not zero: Canonical gates rejected all 4,002 Candidate rows after missing ETF/Capital context | six-stock real free-data Pilot |
| Full Phase E Pilot effective chain has economic value | `NEGATIVE`: gross 0.000623, cost 0.002100, net -0.001477, maximum drawdown -0.7309 | six-stock real free-data Pilot |
| Any Phase E Pilot T+1 checkpoint is net profitable | `NEGATIVE`: all OPEN/09:45/10:00/10:30/11:30/CLOSE mean net returns are below zero | six-stock real free-data Pilot |
| Phase E Pilot Market Cap or Industry slice explains returns | `NOT_ESTIMABLE`: required historical facts are absent | six-stock real free-data Pilot |
| Positive Phase E Pilot fixed-ridge challenger proves Formal OOS or economics | False: the small MSE improvement and 0.05842 validation RankIC are exploratory temporal validation only | six-stock real free-data Pilot |
| Phase E2 Volume adds value to Price | `NEGATIVE`: gross incremental lift -0.002688 and RankIC falls from 0.064539 to 0.040527 | 300-stock free-data exploratory corpus |
| Phase E2 ETF establishes incremental Alpha | `INCONCLUSIVE`: real ETF coverage exists, but gross lift is only +0.000187 over 19 sessions | 300-stock free-data exploratory corpus |
| Phase E2 Candidate ranking adds value | `NEGATIVE`: ten real selections become observable, but Candidate incremental lift is -0.000802 | 300-stock free-data exploratory corpus |
| Phase E2 Signal adds value | No observed increment: ten Signal snapshots are all `INACTIVE` and incremental lift is exactly 0.000000; deprioritize until active-state coverage exists | 300-stock free-data exploratory corpus |
| Phase E2 Forecast adds value | `NOT_ESTIMABLE`: ten Forecast objects exist, but each has only 2--18 usable same-symbol path samples against the frozen minimum of 20 | 300-stock free-data exploratory corpus |
| Phase E2 cumulative ablation proves economic value | `INCONCLUSIVE`: full ranking net is +0.012374 after assumed costs, but all six executable T+1 checkpoints are gross- and net-negative | 300-stock free-data exploratory corpus |
| Phase E2 current Portfolio result proves general Alpha | False: gross +0.014474, assumed-cost net +0.012374 and drawdown -0.130944 cover only 19 retrospective sessions and conflict with negative checkpoint economics | 300-stock free-data exploratory corpus |
| Phase E2 Market Cap or Industry is estimable | `NOT_ESTIMABLE`: no Decision-time share owner exists and current Industry is deliberately not backfilled | 300-stock free-data exploratory corpus |
| Phase E2 exploratory challenger is estimable | `NOT_ESTIMABLE`: 19 temporal sessions do not meet the frozen temporal-session floor | 300-stock free-data exploratory corpus |

Negative evidence is first-class and immutable. A failed result may motivate a new separately frozen hypothesis; it may not be reworded into success.
