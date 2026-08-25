# Negative and Inconclusive Results

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Current registry of failed, blocked or insufficient research claims
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-26
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
| Phase E2 signed layer lifts remain admissible V2 evidence | False: the V1 scorer split equal Factor values with observation identity; Volume/ETF/Candidate/Signal ranking and lift claims below are retained only as methodology-invalidated historical records | immutable V1 Evidence + V2 Methodology Assessment |
| Phase E2 Volume adds value to Price | `METHODOLOGY_INVALIDATED`: recorded V1 gross lift -0.002688 and RankIC change cannot support a current claim | 300-stock V1 exploratory corpus |
| Phase E2 ETF establishes incremental Alpha | `METHODOLOGY_INVALIDATED`: recorded V1 gross lift +0.000187 cannot support a current claim | 300-stock V1 exploratory corpus |
| Phase E2 Candidate ranking adds value | `METHODOLOGY_INVALIDATED`: recorded V1 Candidate lift -0.000802 cannot support a current claim | 300-stock V1 exploratory corpus |
| Phase E2 Signal adds value | `METHODOLOGY_INVALIDATED`: recorded V1 zero increment cannot support a current claim; ten Signal snapshots were inactive | 300-stock V1 exploratory corpus |
| Phase E2 Forecast adds value | `NOT_ESTIMABLE`: ten Forecast objects exist, but each has only 2--18 usable same-symbol path samples against the frozen minimum of 20 | 300-stock free-data exploratory corpus |
| Phase E2 cumulative ablation proves economic value | `METHODOLOGY_INVALIDATED`: the V1 +0.012374 net ranking result is superseded; no exact-rational Phase E2 replacement was run in this campaign | immutable V1 Evidence + V2 Methodology Assessment |
| Phase E2 current Portfolio result proves general Alpha | False: the V1 positive Portfolio interpretation is methodology-invalidated, not merely weakened; no replacement positive estimate exists | immutable V1 Evidence + V2 Methodology Assessment |
| Phase E2 Market Cap or Industry is estimable | `NOT_ESTIMABLE`: no Decision-time share owner exists and current Industry is deliberately not backfilled | 300-stock free-data exploratory corpus |
| Phase E2 exploratory challenger is estimable | `NOT_ESTIMABLE`: 19 temporal sessions do not meet the frozen temporal-session floor | 300-stock free-data exploratory corpus |
| Phase E3 ETF establishes longitudinal Alpha context | `NOT_ESTIMABLE`: all 2,790 requests succeed, but every frozen `510300.SH` interval returns zero observations; no index or Daily-only substitution is allowed | 126-session longitudinal free-data corpus |
| Phase E3 Capital, Candidate, Signal or canonical Forecast adds value | `NOT_ESTIMABLE`: ETF amount expansion is absent, Capital is insufficient in all sessions, all 37,800 Candidates are rejected and Signal/Forecast are never emitted; thresholds and Forecast floor are unchanged | 126-session longitudinal free-data corpus |
| Phase E3 V1 signed Context lifts remain admissible | False: Volume/Theme/Dynamic Pool negative lifts and Market Regime positive lift used identity-broken V1 ranking and are methodology-invalidated | immutable V1 Evidence + V2 Methodology Assessment |
| Golden V2 Price-only baseline has information or economic value | `NEGATIVE`: RankIC -0.061618, spread -0.002222, Top-10 gross -0.000839, assumed cost 0.002100 and net -0.002939 | exact-rational V2 / 37,375 observations / 126 sessions |
| Golden V2 adding Volume establishes a useful baseline | `NEGATIVE`: gross improves only +0.000041; RankIC -0.059226, spread -0.001937, gross -0.000798, net -0.002899 and drawdown -0.457415 remain negative | exact-rational V2 / 37,375 observations / 126 sessions |
| Golden V2 Regime, Theme or Dynamic Pool adds executable ranking value | No Top/Bottom boundary or gross increment. Regime/Theme are neutral in this scope; Dynamic Pool is non-constant in only 3/126 sessions and slightly changes RankIC but not boundary exposure/economics | exact-rational V2 canonical Evaluation |
| Golden V2 ETF, Capital, Candidate, Signal or Forecast lift is zero | False: ETF/Capital/Candidate/Signal/Forecast increments are `NOT_ESTIMABLE`; all Candidate rows are rejected and downstream coverage is zero | exact-rational V2 canonical Evaluation |
| Golden V2 first-rejection counts prove an individual Gate is useful or harmful | False: Candidate owners record Capital 15,595, Market Regime 14,978, Theme 7,199, Dynamic Pool 22 and Liquidity 6 first failures, but sequential first-failure ordering is not an isolated Gate contrast; Golden V2 Panel/Evidence dropped those diagnostics and WP-01 Panel v2 now preserves them without promoting the counts into lift | direct Candidate-owner audit + WP-01 canonical Panel |
| WP-ALPHA-RESEARCH-01 initial run `a09d…a8d` proves Market Regime or Theme should remain a hard Gate | `METHODOLOGY_INVALIDATED / SUPERSEDED`: the first evaluator compared different temporal subsets and therefore mislabeled conditional sample selection as incremental lift; its Candidate registry also omitted the implemented `NO_PREDICTIVE_GATES` control | immutable run + `historical-evidence-e2d71e…d7a1`; excluded before conclusion and explicitly superseded by the matched-session protocol |
| Golden V2 full ranking chain has economic value | `NEGATIVE`: RankIC -0.059283, Top-10 gross -0.000798, assumed cost 0.002100, net -0.002899 and maximum drawdown -0.457415 | exact-rational V2 / 37,375 observations / 126 sessions |
| Golden V2 canonical Strategy or Portfolio economics are zero | False: 126/126 sessions are `NO_ACTION` with zero Portfolio lines, so gross/cost/net/turnover/drawdown are `NOT_ESTIMABLE` | canonical Cycle/Portfolio/Outcome/Attribution owners |
| Phase E3 V1 six-checkpoint pseudo-portfolio economics remain Canonical Strategy Evidence | False: the 224,718 retrospective checkpoint diagnostics are retained historical research, but the old Evidence producer reconstructed a portfolio from `RESEARCH_PANEL`; V2 canonical Strategy/Portfolio economics are `NOT_ESTIMABLE` | immutable V1 Evidence + V2 canonical owner closure |
| Phase E3 fixed-ridge challenger proves canonical Forecast, Formal OOS or economics | False: MSE 0.000502153 versus baseline 0.000518944 and RankIC 0.015405 cover one exploratory temporal split; canonical Forecast remains empty | 29,729 training / 7,646 later validation observations |
| Phase E3 corporate-action exclusions are ordinary missing returns | False: 2,082 six-checkpoint labels are explicitly unavailable because they cross a known action or one persisted coverage gap | owner-resolved corporate-action facts |
| Running Overnight and Swing through one platform establishes either strategy's Alpha | False: migration-085 proof establishes contracts, runtime, persistence, replay and isolation only; no new empirical return sample was produced | engineering only |
| Multi-horizon Path Outcome support establishes Swing economic value | False: the kernel and PostgreSQL owner are executable, but automatic longitudinal path production and qualified evaluation remain pending | contract/PostgreSQL engineering only |
| A strategy Challenger can automatically replace the active version | False: feedback is diagnostic and every current qualification is fail-closed; no Champion mutation path exists | engineering only |
| Phase II unit tests prove the three intraday Factors are correct Alpha | False: tests prove deterministic kernels and fail-closed boundaries only; the real physical package was not reopened | engineering only / `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED` |
| Phase II determined whether the three intraday Factors are independent Alpha or one latent factor | `NOT_RUN / NOT_PROVEN`: pairwise/rank/leave-one-out/incremental/residual diagnostics are implemented, but no real corpus diagnostic was executed | engineering capability only |
| Phase II externally validated the Price/Return challenger | False: the frozen Temporal/Universe/Provider capability exists, but no new External Dataset was executed | `EMPIRICALLY_EXECUTED=false / EXTERNALLY_VALIDATED=false` |
| Market Regime, Theme or Capital is now a supported stock-level hard Gate | False: session-level and cross-sectional Context semantics are implemented; current Market/Global Theme roles are session-level and Capital is a public proxy. No Context was empirically promoted | engineering only / several roles `NOT_ESTIMABLE` |
| Candidate Policy V2 activates the Challenger | False: Incumbent/Challenger coexistence and comparison are implemented, but Challenger admission requires real correctness plus external validation evidence | dormant engineering capability |
| Conditional Forecast outputs calibrated probability or qualified Strategy action | False: at this result's evidence revision barrier heads emitted raw logits/frequencies, calibration was absent, no non-circular pre-Strategy Risk resolver was wired and Strategy economics were not run. A later engineering checkpoint wired the resolver without creating calibration, economics or qualification evidence | historical `IMPLEMENTED_NOT_WIRED`; current `OWNER_WIRED / CALIBRATED=false / STRATEGY_QUALIFIED=false` |
| WP-ALPHA-PROOF-02 frozen three-factor higher-direction challenger has Discovery Alpha | `REJECTED`: mean RankIC -0.091138, ICIR -0.496474, BH-FDR 0.001732, Top-5 gross -0.000891 and engineering-assumption-cost net -0.002991; the significant sign is adverse and must not be reversed under the same Experiment | exact 126-session Discovery run `historical-research-run-0382e3c92084432a7d7b9c36` + immutable Evidence |
| WP-ALPHA-PROOF-02 establishes end-to-end physical correctness | `CORRECTNESS_FAILED`: package checksum and all 6,548,518 Raw→Normalized observations reproduce, but 8/37,800 persisted Target sources are not reproducible and 425 are partial | `alpha-correctness-proof:9196bf13d40dde78f50ab3314ac511d05f952f91b4075bf5f201c755eeb1067b` |
| WP-ALPHA-PROOF-02 externally validates or consumes Locked OOS | `NOT_ESTIMABLE / BLOCKED_BY_CORRECTNESS`: External was not admitted; BaoStock remains `PIT_INCOMPLETE`; Locked roster is frozen and `LOCKED_OOS_CONSUMED=false` | exact correctness Evidence + label-blind Locked scope `frozen-locked-oos-scope:ed65a20e87fba32e48194f3c74592d880defa8ec972e593aa69f84217751c8b3` |

Negative evidence is first-class and immutable. A failed result may motivate a new separately frozen hypothesis; it may not be reworded into success.
