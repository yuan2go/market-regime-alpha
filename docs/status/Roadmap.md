# Roadmap

> **Status:** ROADMAP  
> **Authority:** Dependency-ordered forward work  
> **Repository Baseline:** `main@5a441746ada08eb08310b12e34d9e0f56f56a952`
> **Strongest Research Evidence Revision:** `0d1a5a8` (WP-ALPHA-RESEARCH-01)
> **Last Updated:** 2026-08-21
> **Code Evidence:** `docs/status/Current-State.md`, `docs/status/Gap-Register.md`

The project has left the platform-first phase. The next program is an **Alpha Proof Campaign**: one vertical research/strategy loop drives the engineering backlog, while formal/prospective evidence remains independently gated.

This roadmap is evidence-conditioned. After each Work Package, actual results may reorder, simplify or eliminate later work.

---

## Program objective

Prove or reject one complete, realistic A-share Alpha chain:

```text
Decision-Time Evidence
→ PIT Tradable Universe
→ Transparent Feature/Factor Baseline
→ Cross-sectional Ranking / Candidate
→ Signal / Forecast only where incremental
→ Strategy
→ Portfolio / Risk
→ Shadow / Manual execution semantics
→ Outcome
→ Attribution
→ Research Decision
```

The initial Golden Strategy Question should reuse the existing frozen decision/execution protocol where authoritative. Conceptually it is a late-session decision with T+1 morning realization, evaluated through MFE/MAE, gross/cost/net, fillability, turnover, capacity and drawdown.

---

# P0 Work Packages

## WP-GOLDEN-LOOP-01 — Golden Alpha Proof Vertical Slice

**Status:** `COMPLETE` for research-correctness engineering and retrospective
canonical Evidence closure at the executable V2 baseline. Empirical Alpha,
Strategy economics and prospective proof remain outside this completion claim.

**Current problem**  
The repository contains most individual capabilities, but next-stage progress is still too easy to measure by platform feature completion instead of one complete economic proof chain.

**Goal**  
Make one Strategy Version the reference vertical slice from decision-time evidence through immutable outcome and attribution.

**Business value**  
Exposes the real bottleneck: data, factor information, Candidate policy, Forecast, Strategy economics, cost or architecture.

**Technical scope**  
Use existing canonical owners/runtime wherever possible. Close only real gaps in dataset/feature lineage, ranking, strategy/shadow decision freeze, outcome settlement, query and attribution. Do not create a parallel Runtime.

**Dependencies**  
Existing PostgreSQL Authority, Historical Research and Strategy Runtime.

**Real market window required?**  
No for engineering/historical proof. Yes later for prospective evidence.

**Acceptance**

- one frozen Strategy/Experiment/Target/Decision-Time identity;
- one exact PIT-labelled historical research slice;
- one replayable owner chain from input through outcome/attribution;
- explicit blocked/missing states rather than fabricated values;
- no second scheduler, business Authority or fixture-only production path.

**System capability gained**  
A Golden Research Loop that exposes the next highest-information problem.

**Observed result**
The 126-session exact-rational V2 campaign and replay bind Research Evaluation
to the canonical Cycle, Cross-Strategy Portfolio, Outcome and Attribution
owners. It rejects the Alpha claim: Price and Price+Volume RankIC, spread, gross
and net are negative; all 37,800 Candidates are rejected; Signal/Forecast
coverage is zero; 126 Portfolio sessions are `NO_ACTION`; Strategy economics
are `NOT_ESTIMABLE`. WP-ALPHA-RESEARCH-01 has now completed the next controlled
Factor/Gate/Candidate discovery step without changing that dataset.

---

## WP-ALPHA-RESEARCH-01 — PIT-aware Factor → Gate → Candidate Discovery

**Status:** `COMPLETE`, governed by
`docs/research/protocols/WP-ALPHA-RESEARCH-01-Frozen-Discovery-Protocol.md`.

**Frozen scope**
Reuse only the existing Phase E3 dataset scope: 126 CSI 300 Decision Sessions
from 2025-01-02 through 2025-07-11, DecisionTime 14:55 Asia/Shanghai and T+1
10:30 Target. Provider, Universe, Target/Horizon, cost assumptions and Golden
V2 tie-aware correctness contract do not change.

**Resolved implementation gap**
The canonical Feature owner currently materializes 70 outputs. Panel v2 now
projects all of them with PIT/lineage/coverage state and retains Candidate plus
Gate diagnostics. The existing two-factor Golden V2 projection remains
compatible; no Feature computation was copied.

**Goal**
Determine which registered Feature families carry stable forward information
and whether Market Regime, Theme, Capital and Dynamic Pool should remain hard
Gates, become soft factors, be retested or retire.

**Technical scope**

```text
persisted frozen Experiment Definition
→ owner-resolved full Feature/Factor Panel
→ hard-integrity population
→ current-hard / soft-feature / no-predictive Gate contrasts
→ transparent Candidate challengers
→ tie-aware multi-K / quantile / stability / economics diagnostics
→ multiple-testing adjustment
→ immutable exploratory Evidence and Gate dispositions
```

No Golden Runner, scheduler, backtest Authority, feature recomputation or
Forecast/Portfolio/Governance expansion is admitted.

**Acceptance**

- exact Dataset/Universe/session/DecisionTime/Target/cost/factor/Gate/scoring/
  metric/evidence-ceiling Experiment owner is persisted and reloaded before run;
- all canonical Feature outputs enter lineage/coverage; only the pre-registered
  factor registry enters hypotheses;
- Panel retains Candidate status, score, rank and complete Gate reasons;
- tradability/data-integrity Gates remain hard;
- Market/Theme/Capital/Dynamic Pool each receive isolated hard/soft/none contrasts;
- every registered hypothesis emits common coverage, RankIC/IC stability,
  quintile, Top-1/3/5/10, MFE/MAE, turnover, gross/net and conditional diagnostics;
- the existing multiple-testing kernel adjusts the complete discovery family;
- each predictive Gate ends as `KEEP_AS_HARD_GATE`, `DEMOTE_TO_FACTOR`,
  `RETEST` or `RETIRE`; negative and `NOT_ESTIMABLE` evidence remains durable;
- Historical Runtime → canonical owners → Panel → Golden Evaluation/Evidence
  remains the sole execution chain.

**System capability gained**
A transparent Alpha discovery baseline and evidence-based Candidate policy,
without pretending the Frozen Discovery Dataset is Formal OOS.

**Observed result**

- final run `historical-research-run-0e150a21c7869adc84a57af5` completed
  126/126 sessions and exact replay;
- 49 numeric Factors, 12 Gate variants and five Candidate policies enter one
  62-hypothesis BH-FDR family;
- hard-integrity Price/Return is exploratory `POSITIVE` with RankIC 0.090809,
  Top-5 assumed-cost net 0.014807 and positive quarterly RankIC;
- all current predictive Gates are `RETEST`; Market/Theme/Capital have no
  within-session mixed population and Dynamic Pool is integrity-confounded;
- Current Hard Chain, Strategy economics and Portfolio performance remain
  `NOT_ESTIMABLE`;
- Evidence remains `EXPLORATORY / PIT_INCOMPLETE / IN_SAMPLE_DISCOVERY /
  UNQUALIFIED`; no Forecast/Strategy/Portfolio/Governance expansion followed.

See `docs/references/WP-ALPHA-RESEARCH-01-Research-Report.md`.

---

## WP-PROSPECTIVE-01 — Prospective Evidence Clock

**Current problem**  
The platform has Shadow/prospective mechanics but no sustained future-time evidence proving model/strategy stability.

**Goal**  
Begin immutable, version-scoped future decision cohorts as soon as the Golden baseline can run honestly.

**Technical scope**  
Freeze decision-time evidence, dataset/feature identity, model/strategy version, code/config identity, Candidate/Signal/Forecast/Portfolio and later bind settled outcomes. Preserve historical predictions unchanged.

**Real market window required?**  
Yes for proof. Engineering, rehearsal and inspection can proceed without waiting.

**Acceptance**

- live-origin/trusted-clock session qualification rules;
- immutable frozen decisions;
- later settlement of required outcomes;
- separate version cohorts;
- replay of exact owner lineage;
- Replay/Fixture/backfill sessions excluded from prospective sample counts.

**System capability gained**  
A prospective evidence asset that cannot be recreated after the fact.

---

# P1 Work Packages

## WP-ALPHA-RESEARCH-02 — External Validation

**Status:** `NEXT_RESEARCH_DESIGN_NOT_YET_FROZEN`; WP-ALPHA-RESEARCH-01 has
frozen its complete result, but no external-validation Experiment is yet active.

A separately content-addressed Experiment may test longer time ranges, CSI
500/1000 or broader A-shares, distinct market states, another Provider and a
longer prospective cohort. None of those changes may be backported into
WP-ALPHA-RESEARCH-01 or used to rewrite its negative results.

**Dependency:** at least one pre-registered WP-ALPHA-RESEARCH-01 factor or
Candidate policy has estimable discovery evidence worth external validation.

---

## WP-STRATEGY-PROOF-01 — Prediction to Executable Strategy

**Current problem**  
Predictive/ranking evidence is not the same as executable net trading value.

**Goal**  
Translate surviving Alpha information into Strategy economics under realistic A-share constraints.

**Technical scope**

```text
Entry / execution checkpoint
Fillability
Position sizing
Top-K / weighting / cash
T+1 and lot constraints
Holding / Exit
Turnover
Cost / slippage
Liquidity / impact / capacity
Drawdown / exposure
```

Keep Portfolio simple until evidence requires more sophistication.

**Dependencies**  
A baseline or factor combination with credible predictive information.

**Real market window required?**  
No for historical simulation; yes for prospective economic proof.

**Acceptance**

- prediction metric and Strategy metric reported separately;
- exact gross→cost→net reconciliation;
- all assumptions carry provenance;
- impossible fills/ambiguous path cases fail closed;
- cost/turnover/capacity sensitivity reported;
- Strategy Version identity changes when result-affecting policy changes.

**System capability gained**  
A Strategy Research Platform rather than a prediction-only platform.

---

## WP-ATTRIBUTION-COMPRESSION-01 — Attribution and Architecture Compression

**Current problem**  
Strong engineering foundations coexist with legacy/compatibility shapes and decision layers whose business value may overlap.

**Goal**  
Use Golden Loop evidence to explain failure sources and safely reduce unnecessary architecture.

**Attribution spine**

```text
Data / PIT
Universe / Eligibility
Context
Ranking / Candidate
Signal
Forecast
Entry
Portfolio / Sizing
Holding / Exit
Cost / Slippage
Execution / Fill
```

**Architecture inventory**

```text
parallel Runtime/writer
unused interface/protocol
Repository wrapper
Receipt/Evidence wrapper
legacy Candidate-to-Entry path
duplicate Shadow/Portfolio shape
obsolete compatibility reader
stale documentation
```

**Real market window required?**  
No for most work.

**Acceptance**

- failure diagnosis is usable by research/operator workflows;
- each retained abstraction names its consumer/failure mode;
- safe deletion has consumer inventory and replay/differential proof where compatibility matters;
- no Big Bang rewrite.

**System capability gained**  
More research value with a smaller, clearer architecture surface.

---

# P2 Work Package

## WP-FORMAL-RESEARCH-01 — Formal PIT / Locked OOS / Calibration / Qualification

**Current problem**  
Formal engineering owners exist, but qualified source/PIT/OOS/calibration/economic evidence does not.

**Goal**  
Move only surviving exploratory hypotheses into formal qualification when required independent evidence is available.

**Technical scope**  
Qualified Provider facts, Formal PIT, frozen Dataset/Protocol, purge/embargo, untouched Locked OOS, multiplicity control, calibration where probability is claimed, economic/cost/capacity evidence and qualification decisions.

**External dependency**  
Yes — qualified historical/PIT evidence and untouched observations.

**Acceptance**

- no reuse of exploratory/OOS observations outside frozen policy;
- every result-affecting owner resolved by exact identity/hash;
- statistical and economic floors independently evaluated;
- failure remains rejected/blocked rather than relaxed.

**System capability gained**  
Credible formal research claims rather than engineering-complete formal machinery.

---

# P3 / Future Work Package

## WP-CONTROLLED-EXECUTION-01 — Optional Controlled Broker Execution

**Precondition**  
Blueprint A has credible Alpha/Strategy/Prospective evidence and Manual production has a separately approved operational case for automation.

**Scope**  
Broker adapter, authenticated order Authority, preview, reconciliation, duplicate-order prevention, cancellation semantics, capital/risk limits, approval and kill switch.

**Status**  
`DEFERRED`. It is not required to complete the current Alpha Research OS.

---

# Evidence gates between Work Packages

```text
Baseline has no ranking information
→ do not jump to complex ML; revisit Target/Data/Features

Candidate sample is starved
→ diagnose gate/coverage before Forecast work

Forecast remains NOT_ESTIMABLE
→ diagnose sample/estimator/conditioning; do not lower the floor just to obtain output

Gross economics negative
→ return to Factor/Candidate/Target/Horizon

Gross positive but Net negative
→ prioritize Cost/Turnover/Liquidity/Entry/Portfolio

In-sample discovery Gross and Net positive
→ freeze disjoint external validation before Forecast/Strategy promotion

Historical survives, prospective fails
→ investigate leakage/stability/drift/availability before qualification
```

---

# Top 5 highest-value actions

1. **WP-ALPHA-RESEARCH-02** — separately freeze time/Universe/Provider validation for the exact Price/Return challenger and its three intraday contributors; do not retune WP-01.
2. **WP-PROSPECTIVE-01** — prepare/freeze the honest challenger cohort and start the future evidence clock when a live-origin market window and required data are available; historical replay cannot fill it.
3. **WP-ATTRIBUTION-COMPRESSION-01** — preserve the four `RETEST` Gate dispositions and investigate whether session-constant Context owners express valid policy or redundant filtering; do not retire from non-estimability alone.
4. **WP-STRATEGY-PROOF-01** — remain dependency-blocked until external Candidate evidence supports an executable action; do not promote in-sample discovery into Strategy economics.
5. **WP-ALPHA-RESEARCH-01 maintenance** — keep its Experiment, supersession chain, Panel/Evaluation replay and full negative/`NOT_ESTIMABLE` output immutable.

`WP-ATTRIBUTION-COMPRESSION-01` runs alongside these when the Golden Loop reveals redundant architecture.

---

# Roadmap guardrails

- Do not add a new top-level Runtime.
- Do not introduce a new business Authority when an existing owner can preserve the invariant.
- Do not treat engineering completion as Alpha proof.
- Do not use Formal/OOS/Prospective labels without owner evidence.
- Do not tune negative results until they become positive without creating a new frozen Experiment.
- Do not build all Future Scope in one release.
- Do not preserve an abstraction solely because it already exists.
- Prefer one complete Work Package over many disconnected TODOs.

After each Work Package, update `Current-State.md`, `Capability-Matrix.md`, `Gap-Register.md` and this Roadmap from the new executable/evidence baseline.
