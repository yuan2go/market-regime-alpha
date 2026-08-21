# Market Regime Alpha — Canonical Overall Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE  
> **Authority:** Single normative system-design baseline  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-19  
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This document defines how Market Regime Alpha should work. It is not an implementation-status report and does not upgrade any research or production claim. Current reality is recorded in `docs/status/` and remains authoritative only when supported by executable code, PostgreSQL owner state, tests actually run and reproducible evidence.

---

## 1. Vision, Goals and Non-Goals

Market Regime Alpha is a:

> **Reliable A-share Alpha Research Operating System + Human-in-the-loop Trading Decision Support Platform.**

Its purpose is to make research claims and trading decisions **reproducible, falsifiable, replayable, auditable and progressively qualifiable**.

The canonical loop is:

```text
Reliable Data / Evidence
→ PIT-safe Research Dataset
→ Feature / Factor
→ Alpha Correctness / Independent Reproduction
→ Frozen External Validation
→ Market / ETF / Theme / Capital Context Conditional Research
→ Tradable Universe
→ Candidate
→ Signal
→ Path Forecast
→ Strategy
→ Portfolio / Risk
→ Prospective Shadow / Human Decision
→ Outcome
→ Attribution
→ Research Feedback
→ Model / Strategy Governance
```

The system shall preserve exact data/time/universe/code/model/strategy lineage; separate facts from inference and decisions; support historical, replay, Shadow and manual operation through convergent semantics; preserve negative and `NOT_ESTIMABLE` evidence; model material A-share execution constraints; and promote/degrade/retire only through explicit evidence.

It shall **not** promise deterministic returns, equate backtests with future Alpha, call raw scores probabilities, infer PIT from retrospective APIs/current membership, let feedback mutate a Champion without requalification, or treat broker automation as a prerequisite for a valuable research/decision system.

Microservices, Kafka, Kubernetes, generic agents, AutoML, reinforcement-learning execution and broker automation are Deferred unless a demonstrated requirement exists.

---

## 2. Architecture Principles

1. **Code and evidence outrank prose.** Executable call chain > PostgreSQL owner state > tests actually executed > reproducible evidence > status docs > historical docs.
2. **One business fact, one Authority.** Projections, reports and receipts may exist, but cannot become hidden writers.
3. **PostgreSQL-centered modular monolith.** Keep one Python modular monolith until independent deployment/scaling/failure/team boundaries justify a split.
4. **One canonical all-day control plane.** Strategy families are bounded children; Historical Research is a bounded runner, not a second daily architecture.
5. **Historical and prospective semantics converge.** Reuse business/strategy logic; vary clock, frozen evidence and execution adapter.
6. **Evidence is scoped.** A claim is bound to Data/PIT × Universe × DecisionTime × Target/Horizon × Model × Strategy × Cost × Evaluation Protocol × Evidence Period.
7. **Position is Fill-derived.** Prediction ≠ Decision ≠ Intent ≠ Fill ≠ Physical Position.
8. **Fail closed for correctness; diagnose starvation.** Leakage, invalid lineage and unsafe execution fail closed; empty/rejected populations remain observable with reasons.
9. **Production-grade, not maximum complexity.** Every abstraction must protect a real invariant/failure mode or serve a real consumer.
10. **Architecture must earn its keep.** Regime/Theme/Capital/Candidate/Signal/Forecast layers remain only where they provide distinct semantic, policy or empirical value.

---

## 3. Business and Capability Architecture

Canonical business chain:

```text
Market Data / Evidence
→ Reference / PIT / Universe
→ Dataset
→ Feature / Factor
→ Shared Context / State
→ Dynamic / Tradable Universe
→ Candidate
→ Signal
→ Path Forecast
→ Opportunity / Thesis
→ Strategy Decision
→ Portfolio / Risk
→ Shadow / Human Decision
→ Manual Execution / Observed Fill
→ Physical Position + Strategy Sleeve
→ Holding / Exit
→ Market Outcome + Strategy Outcome
→ Attribution / Diagnosis
→ Research Feedback
→ Model / Strategy Governance
```

Capability domains:

| Domain | Responsibility |
|---|---|
| Market & Reference Data | Provider evidence, market facts, calendar, security lifecycle, corporate actions, trading rules, index/ETF/industry/theme reference |
| PIT & Universe | Decision-time knowability, historical membership/lifecycle, eligibility and tradable scope |
| Dataset / Feature / Factor | Immutable datasets, feature materialization, factor definitions/evaluation |
| Shared Context | Regime, ETF/Theme, Capital/Flow or explicit proxies, breadth/liquidity and related inferred state |
| Candidate / Signal / Forecast | Ranking, setup assessment and target/horizon-specific path estimation |
| Strategy | Versioned action policy: Entry/Hold/Add/Reduce/Exit and proposal semantics |
| Portfolio / Risk | Selection, allocation, cash, exposure, concentration, turnover, liquidity, capacity and drawdown controls |
| Decision / Execution | Authoritative decision lineage, Shadow/manual boundary, intent, observed Fill, reconciliation |
| Outcome / Attribution | Market path facts, strategy economics and layered diagnosis |
| Research / Evaluation | Experiment identity, cross-sectional evaluation, ablation, calibration, OOS, sensitivity, multiplicity |
| Evidence / Governance | Evidence lineage, Champion/Challenger, qualification/admission/degradation |
| Runtime / Operations | Schedule, recovery, replay, query, trace, metrics, backup/restore |

These are capability boundaries, not service boundaries.

---

## 4. Domain, State and Authority Model

### Facts → Derived indicators → Inferred state → Decision artifacts

**Facts** include price, volume, trading status, membership, published shares, corporate actions and observed Fill.  
**Derived indicators** include momentum, relative strength, MACD, ATR, MA slope, VWAP distance and volume expansion.  
**Inferred state** includes Market Regime, Theme State, Capital State, Trend/Liquidity State.  
**Decision artifacts** include Candidate, Signal, Forecast, Strategy Proposal, Portfolio Decision and Execution Intent.

A derived/proxy Capital signal is labelled as such; it is never promoted into raw capital-flow fact.

Core governed identities include Dataset Manifest, Feature/Factor definition, State Model, Model Version, Strategy Contract/Version/Run, Portfolio Decision, Decision, Execution Intent, Fill, Physical Position, Strategy Sleeve, Outcome, Attribution, Experiment, Evidence Artifact, Qualification Assessment and Runtime Attempt.

Authority rules:

- market/reference facts → canonical evidence/PIT owner;
- Dataset identity → Dataset Manifest owner;
- features → Feature owner;
- inferred state → State owner;
- model lifecycle → Model Governance;
- strategy lifecycle → Strategy Registry/Runtime;
- allocation decision → Portfolio/Decision owner;
- intent/Fill → execution/manual ledger owner;
- Physical Position → effective observed Fill projection;
- Market/Strategy Outcome → Outcome owner;
- Attribution → diagnostic evidence owner;
- qualification/admission → owner-resolved qualification policy;
- runtime/recovery state → runtime journal.

A logical Authority does not require a separate service/table hierarchy when an existing aggregate can preserve the invariant. Projection and Receipt are not Authority.

---

## 5. Data, Evidence, PIT and Dataset Architecture

Data layers:

```text
L0 Provider / Source Evidence
L1 Canonical Market & Reference Facts
L2 Features & Inferred State
L3 Research Dataset / Target Views
L4 Outcome / Evaluation / Attribution
```

Preserve relevant temporal semantics distinctly:

```text
event_time / trading_time
effective_from / effective_to
available_at / retrieved_at
materialized_at / recorded_at / system_imported_at
settled_at
decision_time / as_of_time
```

The PIT question is whether the value was legitimately knowable at `decision_time`, not whether it can be retrieved now for a historical date.

Research must defend against look-ahead, survivorship, revision, universe/future-membership, adjustment/corporate-action, label, backfill and calendar leakage.

Two evidence tracks remain explicit:

```text
Exploratory:
FREE_DATA / UNQUALIFIED / PIT_INCOMPLETE
→ rapid discovery/rejection
→ never sufficient for Formal Alpha

Formal:
Qualified Source
→ Formal PIT
→ Locked Dataset
→ Predeclared Evaluation
→ Locked OOS
→ Calibration/Economics where required
→ Qualification
```

A reusable/formal Dataset Manifest freezes dataset/hash, universe/membership evidence, date range, decision clock, source/reference versions, feature/target versions, PIT status, exclusions/missingness and code/config identity.

Large immutable artifacts may live outside PostgreSQL, but PostgreSQL owns canonical identity, lineage, binding and business state. No file/SQLite/memory fallback becomes canonical business Authority.

---

## 6. Quantitative Research Architecture

### Discovery-to-prediction dependency order

An unusually strong discovery result does not advance directly into Candidate,
Forecast or Strategy. The canonical research dependency is:

```text
Alpha Discovery
→ independent feature/target reproduction and temporal correctness
→ separately frozen external validation
→ context-conditional evaluation
→ incumbent/challenger Candidate policy
→ conditional Forecast
→ Strategy economics
```

Correctness compares canonical persisted values with independently recomputed
values from decision-bounded source bars. Owner replay is deterministic evidence,
but is not physical-package reproduction. A missing physical package therefore
remains `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED` even when owner replay passes.

External validation changes one declared dimension at a time: time, Universe or
Provider. Free/PIT-incomplete validation is external validation only; it is not
Formal OOS. Frozen validation outcomes cannot be used to retune factor direction,
Candidate thresholds, target, DecisionTime, Top-K or cost assumptions.

### Transparent baseline first

Every strategy research program begins with a small interpretable cross-sectional baseline using only valid decision-time features. Possible families include Relative Strength, Momentum, Volume/Turnover change, Price Position, Volatility, Liquidity and Industry Relative Strength. The exact formula is frozen by Experiment, not hard-coded into the architecture.

Before optimizing a full strategy, evaluate ranking information using appropriate metrics such as:

```text
RankIC / IC stability
Quantile monotonicity
Top-minus-Bottom spread
Top1 / Top3 / Top5 / Top10
MFE / MAE
hit rate
turnover
gross / cost / net
drawdown / capacity
```

A feature/factor definition declares formula, data source, availability boundary, lookback, normalization, missing-value policy, threshold/score semantics and version. MACD, moving averages, volume/price or Chan-style ideas enter only after conversion to measurable features/gates/scores.

Model complexity escalates only when justified:

```text
Rule/score baseline
→ linear ranking/regression/logistic
→ tree models
→ LightGBM/XGBoost
→ learning-to-rank
→ ensemble
```

A more complex model must show repeatable incremental predictive **and** economic value.

Research infrastructure supports immutable experiment identity, train/validation/OOS, purge/embargo when labels overlap, cross-sectional evaluation, bootstrap/clustered uncertainty, de-duplication, ablation, calibration on disjoint partitions, sensitivity, hypothesis-family/multiple-testing control and untouched Locked OOS.

Changing target, universe, threshold, feature search or cost after seeing OOS creates a new Experiment identity; OOS is not repeatedly reopened.

---

## 7. Shared Context and Decision-Layer Boundaries

Market Regime, ETF, Theme and Capital are **Context**, not universal BUY/SELL authority. Each must have explicit inputs/state/version/time semantics and must prove incremental value versus the transparent baseline through ablation. Session-level Context is evaluated across sessions; it cannot be represented as within-session stock-level lift. Cross-sectional Context may support interactions only when symbols in the same session genuinely carry different values.

Canonical questions:

```text
Candidate = Which securities deserve further analysis?
Signal    = Is there a trade setup now?
Forecast  = What future path distribution is expected?
Strategy  = Should this Strategy Version act?
Portfolio = Which accepted proposals receive capital, and how much?
```

If several layers reduce to the same score with no distinct policy/consumer, simplify or merge them.

Candidate policy has three explicit layers: universal tradability/data integrity,
validated Alpha ranking, and evidence-supported Context conditioning. Missing an
unrelated incumbent factor is not a universal integrity failure. Incumbent and
Challenger identities coexist until evidence and Governance authorize a change.

Path Forecast is target/horizon-specific. It may estimate expected return/downside, MFE/MAE, barrier probabilities, target-before-stop, time-to-MFE or continuation/failure. It explicitly binds Forecast/Target/Trading/Outcome horizons.

Historical lookup, conditional statistics, heuristic mappings and raw ranks are named honestly. Uncalibrated output is not a probability. Insufficient evidence remains `NOT_ESTIMABLE` with diagnostics for sample count, coverage, conditioning and failing floor.

---

## 8. Golden Alpha Proof Vertical Slice

The target platform is multi-strategy, but the next research-development program is driven by one narrow **Golden Strategy Question** rather than horizontal platform expansion.

Default proof shape:

```text
T 14:50–14:55 decision boundary
→ then-knowable / then-tradable A-share Universe
→ Feature / Factor snapshot
→ Cross-sectional Ranking / Candidate
→ Signal / Forecast only if incremental
→ Strategy Decision
→ Top-K Shadow Portfolio
→ T+1 morning realization (core 09:30–10:30 window)
→ Market Outcome + executable Strategy Outcome
→ MFE / MAE / Gross / Cost / Net / Fillability / Turnover / Capacity / Drawdown
→ Attribution / Diagnosis
```

If the repository already owns a more precise frozen decision/execution protocol, reuse it rather than inventing a second one to match example times.

The Golden Slice is a proof vehicle, not the permanent identity of the platform. After its contracts/evidence loop work, other Strategy Families reuse the platform.

---

## 9. Strategy and Portfolio Architecture

Every Strategy Version freezes family/version, universe/eligibility, decision clock/horizon, Target, feature/model dependencies, candidate policy, Entry/Hold/Add/Reduce/Exit policy, Portfolio proposal policy, risk assumptions, cost/execution assumptions, evaluation protocol, qualification policy and code/config identity.

A Model estimates; a Strategy owns an action policy.

Reference families may include Overnight/T+1 and Swing State. ETF/theme rotation, trend, mean reversion, dividend/long-term and event strategies are Future until the Alpha Proof loop justifies expansion.

Portfolio is a real strategy layer. Start simple:

```text
Top-K
Equal/Score Weight
Cash / NAV
Exposure
Turnover / Cost
Drawdown
```

Add industry/theme concentration, correlation, liquidity, capacity, volatility targeting or risk budgets only when empirical risk/economic evidence requires them. Do not build an advanced optimizer before simple baselines establish value.

Executable research models applicable A-share constraints: T+1, 100-share lots, suspension, price limits, listing lifecycle, auction versus continuous trading, fillability, liquidity, slippage/fees, impact and capacity. Ideal future min/max fills are not executable assumptions.

---

## 10. Canonical Runtime, Workflow and Agents

One top-level all-day runtime owns:

```text
Schedule / Session
→ Evidence acquisition/refresh
→ Normalize / validate / PIT eligibility
→ Feature materialization
→ Shared Context
→ Strategy Versions
→ Universe / Ranking / Candidate
→ Signal / Forecast
→ Strategy Proposal
→ Cross-strategy Portfolio / Risk
→ Frozen Decision
→ Shadow / Manual execution boundary
→ Fill / Position where observed
→ Outcome when available
→ Attribution / Evidence
```

Historical Research uses a historical clock/frozen evidence and the same business/strategy semantics. It may have a bounded journal/recovery/replay layer but cannot implement a second Strategy algorithm.

Query, inspection, replay, recovery, qualification and administration are operator tools; they cannot bypass canonical owners.

Agents/LLMs may assist hypothesis generation, summarization, diagnosis or operations. They are never Market Fact, business Authority, Qualification Authority or autonomous trading authority. If LLM-derived evidence affects a governed decision, preserve model/prompt/input provenance.

---

## 11. Prospective Shadow, Outcome, Attribution and Feedback

Prospective evidence begins early because lost future decision time cannot be reconstructed later.

Freeze each governed prospective decision with decision time, evidence/dataset identity, feature snapshot, model/strategy version, code/config identity and applicable Candidate/Signal/Forecast/Portfolio. Later append outcomes; never rewrite historical predictions. Model/Strategy versions form separate cohorts.

Replay/Fixture/backfilled sessions do not count as live prospective proof.

**Market Outcome** describes what objectively happened: return, high/low, MFE/MAE, gap, barrier order/timing.  
**Strategy Outcome** describes what the strategy experienced: entry/exit/fills, holding time, gross PnL, cost, net PnL, turnover, drawdown and relevant fillability/capacity.

Attribution should diagnose at least:

```text
Data/PIT
Universe/Eligibility
Context
Ranking/Candidate
Signal
Forecast
Entry
Sizing/Portfolio
Holding Horizon
Exit
Cost/Slippage
Execution/Fill
```

Attribution is diagnostic unless a causal design supports causal claims.

Feedback loop:

```text
Hypothesis
→ Frozen Experiment
→ Historical Evidence
→ Strategy Simulation
→ Prospective Evidence
→ Outcome
→ Attribution/Diagnosis
→ Reject / Revise / Promote-to-next-gate
→ New Frozen Experiment
```

Outcome never silently mutates the Champion.

---

## 12. Reliability, Recovery and Replay

Implement reliability only for real failure modes:

- idempotency for repeatable side effects;
- transactions for atomic invariants;
- bounded retry for transient failures;
- leases/fences where concurrent ownership/stale workers exist;
- checkpoints/resume for long work;
- append-only correction/supersession where audit history matters;
- versioning/migrations for durable contract change;
- audit for privileged/economically material actions.

Recovery resumes the same authoritative operation. Replay reloads exact frozen owners/inputs/code/config/strategy and re-executes real business semantics; it does not call a replacement Provider to manufacture missing historical evidence. Proof scope is explicit.

---

## 13. Governance, Qualification and Production Admission

Qualification is multi-dimensional evidence:

| Dimension | Question |
|---|---|
| Engineering | Is software/runtime correctly wired, tested, recoverable and replayable for the scope? |
| Data/PIT | Are required facts genuinely decision-time valid? |
| Statistical | Did the frozen hypothesis survive declared validation/OOS? |
| Economic | Does the strategy survive costs, liquidity, capacity and constraints? |
| Prospective | Does it remain stable on future live-origin Shadow evidence? |
| Operational | Is it admitted for Research, Shadow, Manual or future broker execution? |

Production Admission is explicit policy over independently owned evidence, not a magic boolean.

Implementation proof labels:

```text
CODE_IMPLEMENTED
CANONICAL_WIRED
TEST_EXECUTED
RUNTIME_PROVEN
RESEARCH_QUALIFIED
PRODUCTION_QUALIFIED
```

Research labels remain independent:

```text
EXPLORATORY
PIT_INCOMPLETE
IN_SAMPLE
SHADOW
NOT_ESTIMABLE
UNQUALIFIED
FORMAL_OOS
CALIBRATED
```

Invalid upgrades include Mock/Fixture → Runtime Proven, backtest → Prospective Proven, protocol mechanics → Formal OOS, raw score → calibrated probability, or engineering PASS → Alpha Proven.

Champion/Challenger promotion requires a new applicable frozen evidence path.

Controlled broker execution is Blueprint B/Future and requires separate authentication, order/reconciliation, approval, limits and kill-switch admission after Blueprint A is empirically credible.

---

## 14. Observability, Security and Operations

Correlate Run/Session/Attempt, Experiment/Dataset, Model/Strategy Version, Code/config, Decision Time, Portfolio/Decision, Outcome/Attribution and Trace.

Business observability should expose provider freshness/coverage, PIT/eligibility rejections, universe/candidate/selected counts, factor coverage, Forecast estimability/calibration, Shadow/settled-outcome counts, RankIC/Top-K/MFE/MAE/Gross/Net, turnover/drawdown/capacity/exposure, drift where defined, runtime failures/recovery and qualification blockers.

Operators must be able to explain **why no strategy ran, why no Candidate was selected, why Forecast was not estimable, and why gross/net economics failed**.

Current security priorities: secret protection, least privilege, audit and safe configuration. External authenticated identity must bind to durable principals before production permission depends on identity. Broker-security controls are Deferred with broker execution.

---

## 15. Testing, Validation and Proof Ladder

1. Unit — algorithms/invariants.
2. Contract — provider/repository/model/strategy contracts.
3. Integration — PostgreSQL, migrations, composition.
4. Architecture — dependency, runtime and Authority boundaries.
5. E2E Runtime — real canonical composition.
6. Recovery/Replay — interruption/resume/idempotency/determinism.
7. Research Validation — PIT/leakage/frozen dataset/statistical/economic method.
8. Prospective Proof — future live-origin Shadow behavior.
9. Production Admission — explicit operational authorization.

Tests prove only what they execute. Results from a different commit do not make the current HEAD `TEST_EXECUTED`.

---

## 16. Target Architecture

```text
External Market / Reference Evidence
              ↓
       Data / Evidence / PIT
              ↓
     Dataset / Feature / Factor
              ↓
       Shared Context / State
              ↓
 Candidate / Signal / Path Forecast
              ↓
       Strategy Runtime Kernel
      ┌───────┼────────┐
   Overnight Swing   Future
      └───────┼────────┘
              ↓
       Portfolio / Risk
              ↓
     Authoritative Decision
              ↓
  Shadow / Human Manual Execution
              ↓
      Observed Fill / Position
              ↓
      Outcome / Attribution
              ↓
    Evidence / Qualification
              ↓
       Research Feedback
```

Cross-cutting: PostgreSQL Authority, identity/versioning, PIT, audit, observability, recovery/replay and security.

---

## 17. Architecture Compression

Default `DEFER` unless a real unresolved failure mode exists:

```text
new Authority
new Receipt/Evidence hierarchy
new generic Protocol/Policy layer
new Repository wrapper
new Approval/Qualification type
new generic Workflow engine
new Compatibility layer
new parallel Runtime
```

Continuously inventory parallel writers, duplicate concepts, single-implementation interfaces without substitution need, repository wrappers without invariants, unused receipts, fixture-only production abstractions, legacy writers, obsolete compatibility and dead docs/code.

Disposition:

```text
KEEP | SIMPLIFY | MERGE | REFACTOR | RETIRE | DELETE | DEFER
```

A successful iteration may increase business value while reducing concept count.

---

## 18. Evidence-driven Development

Use the observed failure to select work:

```text
Candidate coverage too small
→ Universe / gate / threshold / ranking diagnosis

Forecast NOT_ESTIMABLE
→ sample / coverage / conditioning / estimator diagnosis

Gross < 0
→ Factor / Candidate / Target / Horizon

Gross > 0 but Net < 0
→ Cost / turnover / liquidity / Entry / Portfolio

Historical positive, Prospective weak
→ leakage / stability / drift / availability

Architecture has no real consumer
→ SIMPLIFY / MERGE / RETIRE / DELETE
```

Never tune a negative result merely to make it positive without freezing a new Experiment/Strategy identity.

---

## 19. Canonical Roadmap

The next program is an **Alpha Proof Campaign** with these Work Packages:

- **P0 WP-GOLDEN-LOOP-01** — one DecisionTime→Universe→Feature→Candidate→Strategy→Shadow Portfolio→Outcome→Attribution vertical slice.
- **P0 WP-ALPHA-RESEARCH-01** — frozen PIT-aware Factor→Gate→Candidate discovery: owner-resolved Panel, transparent baseline, predictive-Gate ablation and explicit rejection.
- **P0 WP-ALPHA-CORRECTNESS-01 — ENGINEERING COMPLETE** — independent source-bar/target reproduction, temporal/placebo/bar-order-derived execution/redundancy/robust-inference checks; current physical state remains `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`.
- **P1 WP-ALPHA-RESEARCH-02 — CAPABILITY COMPLETE / NOT RUN** — canonical Experiment Definition freezes single-dimension time/Universe/Provider external validation after a discovery result survives correctness; Panel-linked Outcome/Strategy Economics owners gate entry economics.
- **P1 WP-ALPHA-CONTEXT-01 — CAPABILITY COMPLETE / NOT RUN** — session-level and cross-sectional Context conditional evaluation without default hard-Gate authority.
- **P1 WP-CANDIDATE-POLICY-02 — ENGINEERING COMPLETE / CHALLENGER DORMANT** — explicit Incumbent/Challenger policies with integrity, Alpha and Context layers.
- **P2 WP-PREDICTION-01 — KERNEL IMPLEMENTED / OWNER WIRING FAIL-CLOSED** — Candidate→Signal→conditional Forecast→Strategy contract has explicit requirement and lineage semantics; caller projections and the circular post-Portfolio RiskDecision path are rejected, and activation waits for one non-circular PostgreSQL pre-Strategy Risk resolver.
- **Next Strategy Economics** — Entry/Fillability/Sizing/Portfolio/Holding/Exit/Cost/Capacity/Risk economics.
- **Then Formal PIT / Formal OOS** — qualified Provider/PIT, Locked OOS and calibration once external evidence exists.
- **Then Prospective Proof** — immutable live-origin future decision/outcome cohorts.
- **P3 WP-CONTROLLED-EXECUTION-01** — optional broker automation only after separate empirical/operational admission.

Gaps are classified as **A: build now**, **B: engineering-ready but prospective evidence must accumulate**, or **C: external capability/evidence dependent**. B/C never block A, and A never pretends to satisfy B/C.

The roadmap is evidence-conditioned. Current details and acceptance criteria live in `docs/status/Roadmap.md`.

---

## 20. Superseded Designs

Explicitly superseded:

| Historical approach | Canonical decision |
|---|---|
| Build full platform before model research | Run vertical Alpha Proof; build only blockers exposed by the loop |
| Stop platform work and jump to complex ML | Preserve data/method correctness; start with transparent baseline |
| Governance-first roadmap | Freeze nonessential governance expansion |
| Forecast-first architecture | Prove Universe/Feature/Ranking/Candidate information first |
| Candidate equals Entry | Separate unless evidence/consumers justify deliberate merge |
| Regime/Theme/Capital directly decide trades | Context consumed by Strategy and validated by ablation |
| Multiple daily runtimes | One top-level control plane |
| Qualification as giant state machine | Independent evidence dimensions + admission policy |
| Separate backtest/live business logic | Shared domain/strategy semantics |
| Decision creates Position | Fill-derived Physical Position |
| Broker automation defines production | Human-in-loop production is valid; broker is Future |
| More abstraction = more maturity | Correct simple design with real consumers wins |

The former `docs/constitution/00` through `09` set is superseded by this Canonical Design and retained only in Git history.

---

## 21. Completion Criteria

Blueprint A is materially achieved when:

1. Strategy Versions run through one canonical platform without parallel authority planes;
2. decisions are reproducible from then-knowable evidence and frozen Dataset/Model/Strategy/Code identity;
3. transparent baselines and surviving factors show reproducible incremental information;
4. prediction value translates into realistic gross/net Strategy economics;
5. Portfolio owns allocation/risk rather than bookkeeping only;
6. prospective Shadow accumulates immutable future cohorts;
7. Outcome/Attribution diagnoses Data→Execution failures;
8. negative and `NOT_ESTIMABLE` evidence can reject/simplify models and architecture;
9. Formal PIT/OOS/calibration/economic/prospective claims are independently auditable;
10. recovery/replay is proven for relevant runtime scopes;
11. operators can explain missing/rejected decisions;
12. adding a strategy requires a Strategy Version and evidence program, not a new platform.

Controlled broker execution is not part of these completion criteria.

---

## 22. Canonical Summary

Market Regime Alpha is neither primarily an infrastructure project nor primarily a model-training project. It is an **evidence-driven Alpha research and decision operating system**.

Near-term operating principle:

```text
Freeze unnecessary infrastructure growth
→ run one Golden Alpha Proof loop
→ establish a transparent baseline
→ measure factor/context/model incremental value
→ translate prediction into executable Strategy/Portfolio economics
→ accumulate immutable prospective evidence
→ attribute failures and reject weak hypotheses
→ build only the capability the evidence shows is missing
→ continuously simplify redundant architecture
```

Progress is measured by evidence quality and closed research/decision loops, not by class/table/receipt count. Research conclusions require evidence, decisions require Authority, outcomes must be replayable, qualifications must be independently provable, and Production Admission cannot be obtained by assertion.
