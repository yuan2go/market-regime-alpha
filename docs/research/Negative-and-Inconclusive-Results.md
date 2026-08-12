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
| Phase E Price-only baseline has economic value | `NEGATIVE`: RankIC -0.01652; gross 0.000935, engineering-assumption cost 0.002100, net -0.001165 | real free-data exploratory corpus |
| Volume and Market Regime establish net Alpha | `INCONCLUSIVE`: incremental net lift +0.000070 and +0.000196, but both variants remain net negative | real free-data exploratory corpus |
| Theme and Dynamic Pool add value in the representative corpus | `NEGATIVE`: incremental net lift -0.000350 and -0.000228 | real free-data exploratory corpus |
| ETF and Capital add zero value | `NOT_ESTIMABLE`, not zero: BaoStock returned no requested ETF history, leaving both factor families unobserved | real free-data exploratory corpus |
| Candidate, Signal and Forecast add zero value | `NOT_ESTIMABLE`, not zero: Canonical gates rejected all 4,002 Candidate rows after missing ETF/Capital context | real free-data exploratory corpus |
| Full Phase E effective chain has economic value | `NEGATIVE`: gross 0.000623, cost 0.002100, net -0.001477, maximum drawdown -0.7309 | real free-data exploratory corpus |
| Any tested T+1 checkpoint is net profitable | `NEGATIVE`: all OPEN/09:45/10:00/10:30/11:30/CLOSE mean net returns are below zero | real free-data exploratory corpus |
| Current Market Cap or Industry slice explains returns | `NOT_ESTIMABLE`: required historical facts are absent | real free-data exploratory corpus |
| Positive fixed-ridge challenger proves Formal OOS or economics | False: the small MSE improvement and 0.05842 validation RankIC are exploratory temporal validation only | real free-data exploratory corpus |

Negative evidence is first-class and immutable. A failed result may motivate a new separately frozen hypothesis; it may not be reworded into success.
