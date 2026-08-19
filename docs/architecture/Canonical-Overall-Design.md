# Market Regime Alpha — Canonical Overall Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE  
> **Authority:** Single normative system-design baseline  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-19  
> **Scope:** Research, data, strategy, portfolio, runtime, evidence, qualification, operations and future execution

This document defines how Market Regime Alpha should work. It is not an implementation-status report and does not upgrade any research or production claim. Current implementation and evidence are recorded in `docs/status/` and are authoritative only to the extent proven by executable code, PostgreSQL state, tests and reproducible runtime evidence.

---

## 1. Vision

Market Regime Alpha is a:

> **Reliable A-share Alpha Research Operating System + Human-in-the-loop Trading Decision Support Platform.**

Its purpose is not to predict that a stock will certainly rise tomorrow and not to maximize feature count, model complexity or infrastructure sophistication. Its purpose is to make research claims and trading decisions **reproducible, falsifiable, replayable, auditable and progressively qualifiable**.

The platform should make it possible to answer, for any Strategy Version:

> Given the information genuinely available at the declared decision time, the then-tradable universe, the frozen research protocol and realistic A-share execution constraints, did this hypothesis contain incremental predictive information and did that information survive translation into executable net economic value?

The operating loop is:

```text
Reliable Data / Evidence
        ↓
PIT-safe Research Dataset
        ↓
Feature / Factor
        ↓
Market / ETF / Theme / Capital Context
        ↓
Tradable Universe
        ↓
Candidate
        ↓
Signal
        ↓
Path Forecast
        ↓
Strategy
        ↓
Portfolio / Risk
        ↓
Prospective Shadow / Human Decision
        ↓
Outcome
        ↓
Attribution
        ↓
Research Feedback
        ↓
Model / Strategy Governance
```

---

## 2. Goals

The system shall:

- preserve exact data, time, universe, code, model, strategy and experiment lineage;
- separate facts, derived indicators, inferred state, predictions, decisions, execution facts, outcomes and qualification evidence;
- support historical research, replay, prospective Shadow and human-in-the-loop operation through convergent business semantics;
- support multiple independently versioned Strategy Families without creating parallel platform control planes;
- make Candidate, Signal, Forecast, Strategy and Portfolio distinct only when they have distinct semantics and consumers;
- support transparent quantitative baselines before complex models;
- evaluate predictive value and executable economic value separately;
- model material A-share constraints including T+1, lot size, suspension, price limits, auction/continuous trading, fillability, liquidity, slippage, impact and capacity where relevant;
- preserve negative, inconclusive and `NOT_ESTIMABLE` evidence as first-class results;
- accumulate immutable prospective decisions as early as practical because future-time evidence cannot be reconstructed honestly after the fact;
- support attribution and diagnosis sufficient to direct the next research or engineering iteration;
- promote, degrade or retire models and strategies only through explicit evidence-governed decisions;
- retain only reliability and governance mechanisms that protect a real correctness, concurrency, recovery, audit or operational boundary.

---

## 3. Non-Goals

The system shall not:

- promise deterministic returns, a fixed win rate or guaranteed stock selection;
- treat backtest performance as proof of future profitability;
- treat one T+1 strategy, one factor family or one model as the identity of the platform;
- equate Candidate ranking with Entry, Forecast with Decision, or Decision with Position;
- call an uncalibrated score a probability;
- manufacture PIT from retrospective APIs, filenames, current membership or ingestion timestamps;
- allow outcome feedback to mutate the active Champion without a new frozen experiment and requalification;
- use automatic broker execution as a prerequisite for a valuable production-grade decision-support system;
- adopt microservices, Kafka, Kubernetes, a graph database, a generic agent control plane, AutoML, reinforcement-learning execution or online self-modifying trading without demonstrated business need;
- add Authority, Receipt, Evidence, Policy, Repository, Workflow or Qualification layers merely because they look industrial.

Controlled broker execution is a **future optional capability**, not part of the current completion definition.

---

## 4. Architecture Principles

### P1. Code and evidence outrank claims

```text
Executable code / real call chain
>
PostgreSQL owner state
>
Tests actually executed
>
Reproducible runtime / research evidence
>
Status documentation
>
Historical documentation
```

### P2. One business fact, one Authority

A business fact may have projections, receipts and reports, but it has one canonical writer/owner. A projection cannot become a hidden write authority.

### P3. PostgreSQL-centered modular monolith

The target remains one PostgreSQL-centered Python modular monolith until independent deployment, scaling, failure isolation or team ownership produces a real reason to split it.

### P4. One canonical production control plane

There is one all-day runtime owner. Strategy families are bounded children. Historical research is a bounded runner that reuses the same business semantics; it is not a second live architecture.

### P5. Historical and prospective semantics converge

Research, replay, Shadow and manual production should reuse domain/strategy semantics and vary clock, frozen evidence and execution adapters rather than duplicate business algorithms.

### P6. Evidence is scoped

Any Alpha or Strategy claim is scoped by at least:

```text
Data/PIT status
× Universe
× Decision Time
× Target/Horizon
× Feature/Model Version
× Strategy Version
× Cost/Execution Assumption
× Evaluation Protocol
× Evidence Period
```

Evidence from one scope cannot silently qualify another.

### P7. Position is Fill-derived

```text
Prediction ≠ Decision ≠ Order Intent ≠ Fill ≠ Physical Position
```

Observed Fill facts create physical position truth. Strategy sleeves may allocate observed fills for attribution without becoming a second physical-position authority.

### P8. Fail closed for correctness; diagnose research starvation

Future leakage, unresolved PIT requirements, invalid lineage, unsafe corporate-action treatment, invalid execution semantics and unqualified production admission fail closed. Selectivity itself must remain measurable: empty Candidate sets and rejected Forecasts require explicit reasons.

### P9. Production-grade, not maximum complexity

Every abstraction must pay for itself through a concrete consumer or failure mode. Future flexibility is not sufficient justification.

### P10. Architecture earns its keep empirically

Context and decision layers such as Regime, Theme, Capital, Candidate, Signal and Forecast must be tested for incremental research or business value. A layer with no distinct information, policy or consumer should be simplified, merged, retired or deleted.

---

## 5. Business and Research Architecture

### 5.1 Core roles

- **Quant Researcher** — hypotheses, datasets, features, factors, models, evaluation.
- **Strategy Developer** — decision policy, state transitions, entry/hold/exit semantics and strategy economics.
- **Trader / Decision User** — reviews evidence and recommendations, chooses manual action, records/observes execution facts.
- **Reviewer** — evaluates evidence and qualification decisions.
- **Operator** — owns readiness, scheduled operation, recovery, replay, inspection and operational drills.
- **System** — acquires evidence, freezes lineage, executes canonical computations, records outcomes and produces diagnostics.

### 5.2 Canonical business chain

```text
Market Data / Evidence
        ↓
Reference / PIT / Universe
        ↓
Research Dataset
        ↓
Feature / Factor
        ↓
Market Regime
        ↓
ETF / Theme / Capital Context
        ↓
Tradable / Dynamic Universe
        ↓
Candidate Discovery
        ↓
Signal
        ↓
Path Forecast
        ↓
Trading Opportunity / Thesis
        ↓
Strategy Decision
        ↓
Portfolio / Risk
        ↓
Shadow / Human Decision
        ↓
Manual Execution / Observed Fill
        ↓
Physical Position + Strategy Sleeve
        ↓
Holding / Exit
        ↓
Market Outcome + Strategy Outcome
        ↓
Attribution / Diagnosis
        ↓
Research Feedback
        ↓
Model / Strategy Governance
```

A new capability is valuable only if it strengthens this chain or an explicitly required supporting boundary.

---

## 6. Capability Map

| Capability domain | Responsibility |
|---|---|
| Market & Reference Data | Source evidence, market observations, security lifecycle, trading calendar, corporate actions, trading rules, index/ETF/industry/theme reference |
| PIT & Universe | Decision-time knowability, historical membership/lifecycle, eligibility and tradable scope |
| Dataset / Feature / Factor | Immutable research datasets, feature definitions/materialization, factor definitions and diagnostics |
| Shared Context | Market Regime, ETF/Theme, Capital/Flow or explicitly labelled proxies, breadth, liquidity and related inferred states |
| Candidate / Signal / Forecast | Opportunity ranking, setup assessment and path distribution estimation |
| Strategy | Strategy Version, target/horizon, decision policy, Entry/Hold/Add/Reduce/Exit and proposal semantics |
| Portfolio / Risk | Selection, capital allocation, cash, exposure, concentration, turnover, liquidity, capacity and drawdown controls |
| Decision / Execution | Authoritative decision lineage, Shadow/manual execution boundary, intent, observed Fill and reconciliation |
| Outcome / Attribution | Market path facts, strategy economics, layered diagnostics and failure taxonomy |
| Research / Evaluation | Experiment identity, cross-sectional evaluation, ablation, calibration, OOS, sensitivity and statistical controls |
| Evidence / Governance | Evidence lineage, Champion/Challenger, qualification, admission/degradation/retirement |
| Runtime / Operations | Schedule, retries, leases/fences where needed, recovery, replay, query, trace, metrics, backup/restore |

These are capability boundaries, not service boundaries.

---

## 7. Semantic and State Model

The system must keep four semantic layers distinct.

### 7.1 Facts

Examples: price, volume, turnover, trading status, constituent membership, published shares, corporate action, observed Fill.

Facts retain provider/source and time provenance. They do not contain model judgement.

### 7.2 Derived indicators

Examples: momentum, moving-average slope, MACD, ATR, VWAP distance, relative strength, volume expansion.

Derived values must declare formula, lookback, data dependency and version.

### 7.3 Inferred state

Examples: Market Regime, Theme State, Capital State, Trend State, Liquidity State.

Inferred state is a model output. Proxy-derived Capital State must remain explicitly labelled as proxy/derived evidence; it is not raw capital-flow fact.

### 7.4 Decision state

Candidate, Signal, Forecast, Strategy Proposal, Portfolio Decision and Execution Intent are downstream decision artifacts. They must never be stored or described as market facts.

---

## 8. Domain and Authority Model

Canonical business concepts include:

```text
Source Evidence
Reference Fact
Tradable Universe / Runtime Scope
Dataset Manifest
Feature Definition / Materialization
Factor Definition / Evaluation
State Model / State Observation
Candidate Set
Signal
Forecast
Model Version
Strategy Contract / Strategy Version / Strategy Run
Portfolio Decision
Decision
Execution Intent
Fill
Physical Position
Strategy Sleeve
Market Outcome
Strategy Outcome
Attribution
Experiment
Evidence Artifact
Qualification Assessment
Runtime Attempt
```

### 8.1 Authority rules

- **Market / Reference facts:** owned by their canonical evidence/PIT owner.
- **Dataset identity:** owned by immutable Dataset Manifest authority.
- **Feature materialization:** owned by Feature authority.
- **Inferred state:** owned by State authority.
- **Model lifecycle:** owned by Model Governance.
- **Strategy lifecycle:** owned by Strategy Registry/Runtime.
- **Portfolio decision:** owned by Portfolio/Decision authority.
- **Execution intent and observed Fill:** owned by the execution/manual ledger boundary.
- **Physical Position:** derived from effective observed Fill facts.
- **Outcome:** owned by Outcome authority, with Market and Strategy Outcome separated.
- **Attribution:** owned by Attribution/Evidence authority and cannot rewrite outcomes.
- **Qualification:** owned by qualification/admission policy; no caller boolean may assert a higher level.
- **Runtime attempts/recovery state:** owned by runtime journals.

A logical Authority does not require a separate service, repository family or table hierarchy when one cohesive aggregate is sufficient.

### 8.2 Projection and receipt rules

A Projection is a read model. A Receipt proves an operation or binding occurred. Neither becomes a second source of business truth. “Receipt of Receipt”, “Evidence of Evidence” and similar layers are prohibited unless they protect a specific unresolved failure mode.

---

## 9. Data, Evidence and PIT Architecture

### 9.1 Data layers

```text
L0 Provider / Source Evidence
L1 Canonical Market & Reference Facts
L2 Features & Inferred State
L3 Research Dataset / Target Views
L4 Outcome / Evaluation / Attribution
```

### 9.2 Time semantics

Where relevant, preserve and distinguish:

```text
event_time
trading_time
effective_from / effective_to
available_at
retrieved_at
materialized_at
recorded_at
system_imported_at
settled_at
decision_time / as_of_time
```

The central PIT question is not whether a value can be retrieved now for a historical date, but whether it was legitimately knowable and usable at the frozen decision time.

### 9.3 Required leakage controls

Research must explicitly defend against:

- look-ahead bias;
- survivorship bias;
- revision leakage;
- universe/future-membership leakage;
- adjustment/corporate-action leakage;
- label leakage;
- backfill leakage;
- calendar leakage.

### 9.4 Exploratory and Formal tracks

Two evidence tracks are allowed and must remain visibly distinct.

**Exploratory Track**

```text
FREE_DATA / UNQUALIFIED / PIT_INCOMPLETE
→ rapid feature/factor/model research
→ rejection or provisional hypotheses
```

Exploratory evidence may discover or eliminate ideas. It cannot establish Formal PIT, Formal OOS, qualified Alpha or Production Admission.

**Formal Track**

```text
Qualified Source Evidence
→ Formal PIT
→ Locked Dataset
→ Predeclared Evaluation
→ Locked OOS
→ Calibration / Economic Evidence as required
→ Qualification
```

Formal work must not be blocked from engineering merely because future/external evidence is not yet available, but its status remains fail-closed until that evidence exists.

### 9.5 Dataset Manifest

A formal or reusable research dataset freezes at least:

```text
dataset identity / content hash
universe definition and membership evidence
date range and decision clock
source/reference versions
feature versions
target version
PIT status
exclusions/missingness rules
code/config identity
```

Unversioned ad-hoc queries cannot be the basis of a Formal claim.

---

## 10. Feature, Factor and Model Architecture

### 10.1 Transparent baseline first

Every strategy research program begins with a simple, interpretable quantitative baseline. Typical feature families may include relative strength, momentum, volume/turnover change, price position, volatility, liquidity and industry relative strength where the data is valid.

The exact baseline is frozen by experiment; this document does not hard-code one formula.

The baseline is the benchmark every Context layer, Signal, Forecast or machine-learning model must beat.

### 10.2 Feature/factor contract

A reusable feature/factor definition declares:

- formula and semantic meaning;
- required data and decision-time availability boundary;
- lookback/window;
- normalization/ranking policy;
- missing-value policy;
- threshold or continuous scoring semantics where applicable;
- version and lineage.

Technical ideas such as MACD, moving averages, volume/price structure or Chan-style structure enter the system only after conversion into measurable features, gates or scores with explicit data and validation rules.

### 10.3 Cross-sectional evaluation first

Before optimizing a full strategy, the platform should be able to measure whether a ranking contains information using, where applicable:

```text
RankIC / IC stability
quantile monotonicity
Top-minus-Bottom spread
Top1 / Top3 / Top5 / Top10
MFE / MAE
hit rate
turnover
gross / cost / net
drawdown
capacity
```

If the ranking itself has no credible information, additional execution infrastructure must not be used to disguise the research failure.

### 10.4 Model complexity ladder

Preferred escalation:

```text
Rule / score baseline
→ linear ranking / regression / logistic
→ tree models
→ LightGBM / XGBoost
→ learning-to-rank
→ ensemble
```

A more complex model is justified only by repeatable incremental predictive value and incremental economic value after relevant costs/constraints.

---

## 11. Shared Context: Regime, ETF, Theme and Capital

These capabilities provide **context**, not universal trade authority.

Each must have explicit inputs, state semantics, thresholds/hysteresis where relevant, and decision-time lineage.

They must be tested through ablation such as:

```text
Baseline
Baseline + Regime
Baseline + ETF/Theme
Baseline + Capital/Capital Proxy
Baseline + combinations
```

Compare predictive, economic and stability metrics. A context layer that does not provide stable incremental value should be simplified, merged, retired or retained only as descriptive observability if it has a real consumer.

---

## 12. Candidate, Signal, Forecast, Strategy and Portfolio Boundaries

Canonical questions are:

```text
Candidate  = Which securities deserve further analysis?
Signal     = Is there a trade setup now?
Forecast   = What future path distribution is expected?
Strategy   = Should this Strategy Version act under its policy?
Portfolio  = Which accepted proposals receive capital, and how much?
```

If real code reduces several of these layers to the same score with no distinct policy or consumer, the architecture should merge/simplify them rather than preserve ceremonial layers.

### 12.1 Forecast semantics

Path Forecast may estimate target/horizon-specific quantities such as:

```text
Expected Return
Expected Downside
MFE / MAE distribution
P(Target Hit)
P(Stop Hit)
P(Target Before Stop)
Time-to-MFE
Trend continuation / failure
```

It must explicitly bind:

```text
Forecast Horizon
Target Horizon
Trading Horizon
Outcome Horizon
```

Historical lookup, conditional statistics, heuristic score mapping or raw model rank must be named honestly. Uncalibrated outputs are not probabilities. Insufficient evidence remains `NOT_ESTIMABLE` with diagnostics such as sample count, coverage, conditioning dimension and failing threshold.

---

## 13. Golden Alpha Proof Vertical Slice

The platform is multi-strategy by design, but the next research-development loop should be driven by one narrow, high-information **Golden Strategy Question** rather than by horizontal platform expansion.

The default first proof slice is:

```text
T day 14:50–14:55 decision boundary
        ↓
then-knowable / then-tradable A-share universe
        ↓
Feature / Factor snapshot
        ↓
Cross-sectional ranking / Candidate
        ↓
Signal / Forecast where they add distinct value
        ↓
Strategy decision
        ↓
Top-K Shadow Portfolio
        ↓
T+1 morning realization, with 09:30–10:30 as the core evaluation window
        ↓
Market Outcome + executable Strategy Outcome
        ↓
MFE / MAE / Gross / Cost / Net / Fillability / Turnover / Capacity / Drawdown
        ↓
Attribution / Diagnosis
```

Existing frozen decision/execution protocols that are more precise and already authoritative should be reused rather than replaced merely to match these example times.

This Golden Slice is a proof vehicle, not the permanent identity of the platform. Once its contracts and evidence loop are proven, other Strategy Families reuse the platform.

---

## 14. Strategy Architecture

Every Strategy Version freezes enough information to reproduce and evaluate it:

```text
strategy family/version
universe and eligibility contract
decision clock / holding horizon
target contract
feature/model dependencies
candidate policy
entry / hold / add / reduce / exit policy
portfolio proposal policy
risk assumptions
cost/execution assumptions
evaluation protocol
qualification policy
code/config identity
```

Reference Strategy Families may include Overnight/T+1 and Swing State. Future families such as ETF rotation, theme rotation, trend, mean reversion, dividend/long-term and event strategies are deferred until the Alpha Proof loop and platform contract justify expansion.

A Strategy is not a model. A model estimates; a Strategy owns a bounded action policy.

---

## 15. Portfolio and Risk Architecture

Portfolio is a real strategy layer, not just account bookkeeping.

Start with simple baselines such as:

```text
Top-K
Equal Weight / Score Weight
Cash
NAV
Exposure
Turnover
Cost
Drawdown
```

Add industry/theme concentration, correlation, liquidity, capacity, volatility targets or risk budgets only when real strategy evidence exposes the need. Do not build a sophisticated optimizer before simple baselines establish economic value.

Cross-strategy Portfolio combines proposals without creating execution facts. Physical account truth still comes from observed fills.

---

## 16. A-share Strategy Realism

Research that claims executable economics must model the material constraints of its strategy, including where applicable:

- T+1 sell restriction;
- 100-share lot rules;
- suspension;
- price limits;
- listing/security lifecycle;
- opening/closing auction versus continuous auction;
- executable entry/exit checkpoints;
- fillability and liquidity;
- slippage and transaction cost;
- market impact and capacity.

Idealized future minimum/maximum fills are not valid executable assumptions.

The long-term target metric is not raw direction accuracy but expected executable net utility under the Strategy Contract.

---

## 17. Canonical Runtime

### 17.1 Production / prospective control plane

There is one top-level all-day runtime owner:

```text
Schedule / Session Owner
→ Acquire / Refresh Evidence
→ Normalize / Validate / PIT eligibility
→ Materialize Features
→ Infer Shared Context
→ Resolve Strategy Versions
→ Universe / Ranking / Candidate
→ Signal / Forecast
→ Strategy Policy
→ Strategy Proposal
→ Cross-strategy Portfolio / Risk
→ Freeze Decision
→ Shadow / Manual execution boundary
→ Fill / Position where observed
→ Outcome when available
→ Attribution / Evidence
```

A new Strategy Family is a bounded child and must not introduce another daily scheduler, database or business authority plane.

### 17.2 Historical Research Runtime

Historical research uses frozen historical clock/evidence and the same domain/strategy semantics. It may have a bounded journal, recovery and replay orchestration but cannot become a second implementation of Strategy logic.

### 17.3 Operator tools

Query, inspection, replay, recovery, qualification and administration are operator surfaces. They do not bypass canonical owners or create parallel write paths.

### 17.4 Agents / LLMs

Agents may assist with hypothesis generation, evidence summarization, diagnosis or operator workflows. They are never Market Fact, business Authority, Qualification Authority or autonomous trading authority. Derived LLM evidence must be versioned with model/prompt/input provenance if it affects a governed decision.

---

## 18. Prospective Shadow

Prospective evidence is an independent asset and should begin early because it cannot be honestly recreated after the decision time passes.

Every governed prospective decision freezes, as applicable:

```text
decision_time
evidence/dataset identity
feature snapshot
model version
strategy version
code/config identity
candidate/signal/forecast
portfolio decision
```

Later outcomes append to that frozen decision. Historical predictions are never rewritten after observing results.

Model/Strategy Versions form separate prospective cohorts so stability and drift are attributable.

A prospective run that is Replay, Fixture, backfilled or not live-origin/trusted-clock evidence does not count as Prospective Proof.

---

## 19. Outcome, Attribution and Feedback

### 19.1 Market Outcome

What objectively happened after the decision point, for example returns, high/low, MFE/MAE, gap, barrier order and path timing.

### 19.2 Strategy Outcome

What the simulated or observed strategy actually experienced: entry/exit, holding time, fills, gross PnL, cost, net PnL, turnover, drawdown and fillability/capacity where applicable.

Market Outcome and Strategy Outcome are distinct fact families.

### 19.3 Attribution

The minimum diagnostic spine should be capable of distinguishing failures or contributions from:

```text
Data / PIT
Universe / Eligibility
Market / Theme / Capital Context
Candidate / Ranking
Signal
Forecast
Entry
Sizing / Portfolio
Holding Horizon
Exit
Transaction Cost / Slippage
Execution / Fill
```

Attribution is diagnostic unless a causal design explicitly supports causal claims.

### 19.4 Research feedback

```text
Hypothesis
→ Frozen Experiment
→ Historical Evidence
→ Strategy Simulation
→ Prospective Evidence
→ Outcome
→ Attribution / Diagnosis
→ Reject / Revise / Promote-to-next-gate
→ New Frozen Experiment
```

A mature research OS must be good at **rejecting false ideas**, not merely generating new ones.

---

## 20. Research Methodology

Reusable research infrastructure should support, where statistically appropriate:

- immutable experiment/dataset/model/strategy identity;
- train / validation / OOS separation;
- purging and embargo for overlapping labels/horizons;
- cross-sectional RankIC and quantile analysis;
- bootstrap or appropriate clustered uncertainty;
- feature/factor de-duplication;
- ablation and incremental lift;
- calibration with disjoint fit/evaluation partitions;
- sensitivity analysis;
- predeclared hypothesis families and multiple-testing control;
- locked OOS whose observations cannot be repeatedly unlocked by changing labels, features or thresholds;
- exact cost/target/universe/horizon identity.

Forbidden research behavior includes choosing thresholds/features on Locked OOS, repeatedly observing OOS and redesigning the model around it, or redefining target/universe/cost after seeing poor results without creating a new experiment identity.

---

## 21. Reliability, Recovery and Replay

Implement reliability mechanisms only where they protect a real failure mode:

- idempotency for repeatable commands/side effects;
- transactions for atomic business invariants;
- bounded retry for genuinely transient failures;
- leases/fences where concurrent ownership or stale workers exist;
- checkpoints/resume for long-running work;
- append-only correction/supersession where history must remain auditable;
- versioning/migrations for durable schema/contract evolution;
- audit for privileged or economically material actions.

### Recovery

Recovery resumes the same authoritative operation from durable state. It does not invent a new business path.

### Replay

Replay reloads the exact frozen owners/inputs/code/config/strategy scope and re-executes the real business semantics. It must not call a replacement Provider to manufacture missing historical evidence. Replay proof is scoped; proving one workflow does not prove every runtime path.

---

## 22. Governance, Qualification and Production Admission

Qualification is multi-dimensional evidence, not one giant lifecycle enum.

| Dimension | Question |
|---|---|
| Engineering | Is the code/runtime correctly wired, tested, recoverable and replayable for its scope? |
| Data / PIT | Are the required facts genuinely usable at the decision-time boundary? |
| Statistical | Did the frozen hypothesis survive the declared validation/OOS protocol? |
| Economic | Does the strategy survive realistic costs, liquidity, capacity and constraints? |
| Prospective | Does it remain stable on future live-origin Shadow evidence? |
| Operational | Is it admitted for Research, Shadow, Manual or future broker execution? |

Production Admission is an explicit policy over independently owned evidence. Engineering completeness cannot substitute for empirical evidence.

### Evidence-language ladder

Implementation reporting uses:

```text
CODE_IMPLEMENTED
CANONICAL_WIRED
TEST_EXECUTED
RUNTIME_PROVEN
RESEARCH_QUALIFIED
PRODUCTION_QUALIFIED
```

Research status retains independent labels such as:

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

Examples of invalid upgrades:

```text
Mock/Fixture proof        ≠ RUNTIME_PROVEN
Historical backtest      ≠ PROSPECTIVE_PROVEN
Formal protocol mechanics ≠ FORMAL_OOS evidence
Model score              ≠ calibrated probability
Engineering PASS         ≠ ALPHA_PROVEN
```

### Champion / Challenger

Outcome can produce a finding or Challenger. It cannot silently modify the active Champion. Promotion requires a new, frozen, applicable evidence path.

---

## 23. Observability, Operations and Security

Operational inspection must answer business questions, not only process health.

Correlatable identities should include where applicable:

```text
Run / Session / Attempt
Experiment / Dataset
Model / Strategy Version
Code/config identity
Decision Time
Portfolio / Decision
Outcome / Attribution
Trace
```

Business observability should include:

- provider freshness, coverage and missingness;
- PIT/eligibility rejection reasons;
- eligible/candidate/selected counts and gate distributions;
- factor coverage and ranking diagnostics;
- Forecast estimability and calibration status;
- Shadow decision and settled-outcome counts;
- RankIC / Top-K / MFE / MAE / Gross / Net;
- turnover, drawdown, capacity and exposure;
- model/strategy drift when defined;
- runtime failure, retry, recovery and latency;
- current qualification/admission blockers.

Security for the current human-in-the-loop platform includes secret protection, least privilege, audited privileged operations and safe configuration. External authenticated subjects should bind to durable principals before production permissions rely on identity.

Broker credentials, trade permission, kill switch, order reconciliation and capital limits belong to the future controlled-execution program, not the present Alpha Proof campaign.

---

## 24. Testing, Validation and Proof Ladder

Engineering validation is layered:

1. **Unit** — local algorithms and invariants.
2. **Contract** — provider/repository/model/strategy contracts.
3. **Integration** — PostgreSQL, migrations and composed modules.
4. **Architecture** — dependency, canonical runtime and authority boundaries.
5. **E2E Runtime** — real composition and owner chain.
6. **Recovery / Replay** — interruption/resume/idempotency/determinism for the declared scope.
7. **Research Validation** — PIT/leakage, frozen dataset, statistical/economic methodology.
8. **Prospective Proof** — future live-origin Shadow behavior.
9. **Production Admission** — explicit operational authorization.

Tests prove only what they execute. Historical test output from another commit cannot be used to qualify the current HEAD.

---

## 25. Target Architecture

```text
┌──────────────────────── External Evidence ────────────────────────┐
│ Market/Reference Providers │ Events │ Manual/Broker boundaries  │
└───────────────────────────────┬───────────────────────────────────┘
                                ▼
                      Data / Evidence / PIT
                                ▼
                    Dataset / Feature / Factor
                                ▼
                    Shared Context / State
                                ▼
                Candidate / Signal / Path Forecast
                                ▼
                      Strategy Runtime Kernel
                   ┌────────────┼────────────┐
                   ▼            ▼            ▼
               Overnight      Swing       Future families
                   └────────────┼────────────┘
                                ▼
                         Portfolio / Risk
                                ▼
                     Authoritative Decision
                                ▼
                 Shadow / Human Manual Execution
                                ▼
                       Observed Fill / Position
                                ▼
                    Outcome / Attribution
                                ▼
                  Evidence / Qualification
                                ▼
                       Research Feedback
```

Cross-cutting: PostgreSQL Authority, identity/versioning, PIT, audit, observability, recovery/replay and security.

Artifact storage may hold large immutable datasets/reports/model binaries, but PostgreSQL retains canonical identity, lineage, binding and business state. There is no file/SQLite/memory fallback for canonical business authority.

---

## 26. Architecture Compression Guardrails

The project must actively remove accidental and AI-generated complexity.

Default **DEFER** unless a concrete current failure mode exists:

```text
new Authority abstraction
new Receipt hierarchy
new Evidence hierarchy
new generic Protocol/Policy layer
new Repository wrapper
new Approval/Qualification type
new generic Workflow engine
new Compatibility layer
new parallel Runtime
```

Regularly inventory:

- parallel schedulers or writers;
- duplicate domain concepts;
- interfaces with one implementation and no substitution need;
- repository wrappers with no invariant;
- unused receipts/evidence bindings;
- test-only production abstractions;
- fixture-driven pseudo-production paths;
- obsolete compatibility and legacy writers;
- dead code and stale design documents.

Disposition is explicit:

```text
KEEP | SIMPLIFY | MERGE | REFACTOR | RETIRE | DELETE | DEFER
```

A successful iteration may increase business capability while reducing concept count.

---

## 27. Evidence-driven Development Rules

The next engineering action is determined by the observed bottleneck:

```text
Candidate coverage too small
→ diagnose universe / gates / thresholds / ranking distribution

Forecast NOT_ESTIMABLE
→ diagnose sample coverage / conditioning / estimator / threshold

Gross alpha < 0
→ revisit factors / Candidate / target / horizon before execution optimization

Gross > 0 but Net < 0
→ focus on cost / turnover / liquidity / entry / portfolio

Historical positive but Prospective weak
→ investigate leakage / stability / drift / regime / data availability

Architecture has no consumer
→ simplify / merge / delete
```

Negative evidence must not trigger threshold tuning merely to obtain a positive backtest.

---

## 28. Current Development Strategy: Alpha Proof Campaign

The platform-building and model-building tracks are no longer separate sequential phases. The program is organized around one vertical proof loop with five concurrent concerns:

| Track | Purpose | Indicative emphasis |
|---|---|---:|
| Alpha Discovery | Feature, Factor, ranking, Forecast and incremental lift | 35% |
| Strategy Proof | Entry, holding, exit, cost, Portfolio and executable economics | 25% |
| Prospective Evidence | Frozen future decisions, outcomes, stability and drift | 15% |
| Data & Research Correctness | PIT, Dataset, evaluation and leakage controls | 15% |
| Architecture Compression | Runtime/authority convergence, legacy deletion and simplification | 10% |

The percentages are planning guidance, not runtime configuration.

---

## 29. Canonical Work Packages

### P0 — WP-GOLDEN-LOOP-01: Golden Alpha Proof Vertical Slice

**Goal:** prove one complete Decision-Time → Universe → Feature → Candidate → Strategy → Shadow Portfolio → T+1 Outcome → Attribution loop through canonical owners and runtime semantics.

**No future market window required for engineering:** yes. Historical replay/fixture-free engineering can be completed now; prospective evidence accumulates separately.

**Exit:** exact lineage, PostgreSQL authority, replayable historical slice, Shadow-ready freeze/settlement path, no parallel runtime.

### P0 — WP-BASELINE-ALPHA-01: Transparent Cross-sectional Baseline

**Goal:** establish a simple benchmark and report ranking information before complex models.

**Exit:** frozen baseline with quantile/RankIC/Top-K/MFE/MAE/gross/net/turnover diagnostics and honest missingness.

### P0 — WP-PROSPECTIVE-01: Prospective Evidence Clock

**Goal:** continuously freeze real future decisions and later settle outcomes without rewriting history.

**Requires real future windows:** yes for proof; no for supporting engineering.

**Exit:** immutable version-scoped cohorts, trusted decision clock/origin, settled outcomes and replayable lineage.

### P0 — WP-FACTOR-DISCOVERY-01: Factor Discovery, De-duplication and Ablation

**Goal:** quantify whether Price/Volume/RS/Liquidity/Breadth/Industry/ETF/Theme/Capital/Regime/technical structure provide independent information.

**Exit:** factor catalog, coverage, de-duplication, ablation, sensitivity and explicit rejected/inconclusive findings.

### P1 — WP-STRATEGY-PROOF-01: Prediction to Executable Strategy

**Goal:** translate predictive information into realistic Entry, Fillability, Sizing, Portfolio, Holding, Exit, Cost, Capacity and Risk economics.

**Exit:** gross-to-net decomposition under applicable A-share constraints; Strategy Version evidence separated from model metrics.

### P1 — WP-ATTRIBUTION-COMPRESSION-01: Diagnosis and Architecture Compression

**Goal:** explain where value is gained/lost and remove architecture with no distinct consumer or empirical value.

**Exit:** layered attribution plus proven simplification/retirement of redundant paths without losing replay/history.

### P2 — WP-FORMAL-RESEARCH-01: Formal PIT / Locked OOS / Calibration / Qualification

**Goal:** move surviving hypotheses from exploratory discovery to formal claims once qualified external evidence exists.

**External dependency:** qualified historical source/PIT evidence and untouched evaluation observations.

### P3 — WP-CONTROLLED-EXECUTION-01: Optional Controlled Broker Execution

**Goal:** authenticated, approved, reconciled and kill-switch-protected broker execution only after Blueprint A is empirically established and separately admitted.

**Deferred:** not part of current Alpha Proof completion.

---

## 30. Current-to-Target Gap Policy

Gaps are classified into three buckets so unavailable future/external evidence does not block useful engineering.

### A — Build now

Examples: Golden Loop closure, transparent baseline, factor diagnostics, gate coverage, Shadow freeze/settlement engineering, Outcome/Attribution, cost-model plumbing, query/observability and architecture compression.

### B — Engineering-ready, evidence must accumulate prospectively

Examples: sustained Shadow behavior, Provider/runtime reliability under real sessions, drift, strategy stability, operational recovery under consecutive market windows.

### C — External evidence/capability dependent

Examples: qualified historical provider archive, complete Formal PIT fact history, authenticated external identity and any broker connectivity/authority.

B and C must not block A, and A must not pretend to satisfy B or C.

---

## 31. Superseded Design Decisions

The following historical approaches are explicitly superseded:

| Superseded approach | Canonical decision |
|---|---|
| Build the whole platform before Alpha research | Run Alpha Proof vertical slices; add platform capability only when the loop exposes a real blocker |
| Stop platform work and jump directly to complex ML | Preserve research correctness and strategy realism while starting with transparent baselines |
| Governance-first roadmap | Freeze nonessential governance expansion; evidence and business closure drive work |
| Forecast-first architecture | Prove Universe/Feature/Ranking/Candidate information before treating Forecast as central |
| Candidate equals Entry | Candidate and Strategy action are separate unless evidence proves the layers redundant and they are deliberately merged |
| Regime/Theme/Capital directly decide trades | They are contextual evidence consumed by Strategy Versions and must prove incremental value |
| Multiple daily runtimes are acceptable | One canonical all-day control plane; historical/operator flows are bounded children/tools |
| Qualification is one giant state machine | Independent evidence dimensions plus explicit admission policy |
| Backtest/live use separate business logic | Reuse domain/strategy semantics; swap frozen evidence/clock/execution mode |
| Decision creates Position | Physical Position is Fill-derived |
| Broker automation defines production readiness | Human-in-the-loop production is valid; broker execution is future and separately admitted |
| More architecture means more maturity | Correct simple design with real consumers outranks unused sophistication |

The former `docs/constitution/00` through `09` set is superseded by this document and retained only in Git history.

---

## 32. Target Completion Criteria

Blueprint A is materially achieved when:

1. one or more Strategy Versions run through one canonical platform/runtime without parallel authority planes;
2. decisions are reproducible from then-knowable PIT evidence, frozen dataset/model/strategy/code identity and explicit decision clocks;
3. a transparent quantitative baseline and surviving factors demonstrate reproducible incremental information under declared protocols;
4. model/prediction value can be translated into realistic gross and net strategy economics;
5. Portfolio/Risk owns allocation rather than acting only as bookkeeping;
6. prospective Shadow accumulates immutable future cohorts and stable outcomes;
7. Outcome and Attribution can diagnose Data/Universe/Context/Model/Strategy/Portfolio/Cost/Execution failures;
8. negative and `NOT_ESTIMABLE` evidence remains durable and can cause rejection or simplification;
9. Formal PIT, OOS, calibration, economic and prospective claims are separately auditable and cannot be upgraded by engineering success;
10. runtime failure/recovery/replay semantics are proven for the relevant scope;
11. operators can explain why a strategy ran, did not run, selected no Candidate or could not estimate a Forecast;
12. adding another strategy requires a Strategy Version and evidence program rather than another platform/control plane.

Controlled broker execution remains outside these completion criteria.

---

## 33. Canonical Summary

Market Regime Alpha is not primarily an infrastructure project and not primarily a model-training project. It is an **evidence-driven research and decision operating system**.

The near-term organizing principle is:

```text
Freeze unnecessary infrastructure growth
        ↓
Run one Golden Alpha Proof loop end to end
        ↓
Use a transparent quantitative baseline
        ↓
Measure factor/context/model incremental value
        ↓
Translate prediction into executable Strategy/Portfolio economics
        ↓
Accumulate immutable prospective evidence
        ↓
Attribute failures and reject weak hypotheses
        ↓
Build only the platform capability the evidence shows is missing
        ↓
Continuously simplify redundant architecture
```

The standard for progress is not how much code or governance exists. The standard is whether research conclusions have evidence, decisions have a unique Authority, outcomes are replayable, qualifications are independently provable and Production Admission cannot be obtained by assertion.