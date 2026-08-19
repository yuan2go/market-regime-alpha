# Roadmap

> **Status:** CURRENT_ROADMAP  
> **Authority:** Dependency-ordered forward work  
> **Baseline:** `main@ab35a32ab857819153b665d5bf72301f7db46ede`  
> **Last Updated:** 2026-08-19

The project has left the platform-first phase. The next program is an **Alpha Proof Campaign**: one vertical research/strategy loop drives the engineering backlog, while formal/prospective evidence remains independently gated.

The roadmap is not a promise that every work package will be implemented unchanged. After each package, actual evidence may reorder or eliminate later work.

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

The initial Golden Strategy Question should use the existing frozen decision/execution protocol where authoritative. Conceptually it is a late-session decision with T+1 morning realization, evaluated through MFE/MAE, gross/cost/net, fillability, turnover, capacity and drawdown.

---

# P0 Work Packages

## WP-GOLDEN-LOOP-01 — Golden Alpha Proof Vertical Slice

**Current problem**  
The repository contains most individual capabilities, but next-stage progress is still too easy to measure by platform feature completion instead of one complete economic proof chain.

**Goal**  
Make one Strategy Version the reference vertical slice from decision-time evidence through immutable outcome and attribution.

**Business value**  
Exposes the real bottleneck: data, factor information, candidate policy, forecast, strategy economics, cost or architecture.

**Technical scope**  
Use existing canonical owners/runtime wherever possible. Close only real gaps in dataset/feature lineage, ranking, strategy/shadow decision freeze, outcome settlement, query and attribution. Do not create a parallel runtime.

**Dependencies**  
Existing PostgreSQL authority, Historical Research and Strategy runtime.

**Real market window required?**  
No for engineering/historical proof. Yes later for prospective evidence.

**Acceptance**

- one frozen Strategy/Experiment/Target/Decision-Time identity;
- one exact PIT-labelled historical research slice;
- one replayable owner chain from input through outcome/attribution;
- explicit blocked/missing states rather than fabricated values;
- no second scheduler, business authority or fixture-only production path.

**System capability gained**  
A single Golden Research Loop that can expose the next highest-information problem.

---

## WP-BASELINE-ALPHA-01 — Transparent Quantitative Baseline

**Current problem**  
Complex State/Candidate/Signal/Forecast machinery exists without one mandatory simple benchmark governing incremental-value claims.

**Goal**  
Freeze a small interpretable cross-sectional baseline appropriate to the Golden Strategy and use it as the comparison floor.

**Technical scope**  
Reuse existing feature/factor/evaluation infrastructure. The exact factor list is chosen from valid current data; do not hard-code architecture around a particular formula.

**Real market window required?**  
No.

**Acceptance**

- frozen feature/baseline identity;
- coverage/missingness report;
- RankIC/IC stability where applicable;
- quantile monotonicity and Top-K diagnostics;
- MFE/MAE and gross/cost/net connection to the Golden target;
- results persisted as positive/negative/inconclusive/not-estimable without threshold tuning.

**System capability gained**  
A benchmark that complex Context/Forecast/ML must actually beat.

---

## WP-FACTOR-DISCOVERY-01 — Factor Discovery, De-duplication and Context Ablation

**Current problem**  
Current historical evidence contains negative, inconclusive and not-estimable results, but the architecture still contains many context/factor layers whose independent value is unclear.

**Goal**  
Systematically identify which features/context layers carry incremental information for the frozen target and which add only complexity.

**Technical scope**

```text
Price / Trend
Volume / Turnover
Relative Strength
Liquidity / Volatility
Breadth / Industry
ETF / Theme
Capital or explicitly labelled Capital Proxy
Market Regime
technical structure where quantifiable
```

Evaluate baseline versus additions/combinations through existing research owners.

**Real market window required?**  
No.

**Acceptance**

- versioned factor catalog/coverage;
- de-duplication/correlation or equivalent redundancy analysis;
- predeclared ablation and sensitivity results;
- explicit reject/inconclusive decisions;
- no `NOT_ESTIMABLE` converted to zero;
- no layer retained as mandatory merely because code already exists.

**System capability gained**  
An evidence-based factor/context spine and a list of architecture candidates for simplify/merge/retire.

---

## WP-PROSPECTIVE-01 — Prospective Evidence Clock

**Current problem**  
The platform has Shadow/prospective mechanics but no sustained future-time evidence proving model/strategy stability.

**Goal**  
Begin immutable, version-scoped future decision cohorts as soon as the Golden baseline can run honestly.

**Technical scope**  
Freeze decision-time evidence, dataset/feature identity, model/strategy version, code/config identity, Candidate/Signal/Forecast/Portfolio and later bind settled outcomes. Preserve historical predictions unchanged.

**Real market window required?**  
Yes for proof. Engineering, rehearsal and inspection can be completed without waiting.

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
A strategy research platform rather than a prediction-only platform.

---

## WP-ATTRIBUTION-COMPRESSION-01 — Attribution and Architecture Compression

**Current problem**  
Strong engineering foundations coexist with legacy/compatibility shapes and decision layers whose current business value may overlap.

**Goal**  
Use Golden Loop evidence to explain failure sources and safely reduce unnecessary architecture.

**Technical scope**

Attribution categories:

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

Architecture inventory:

```text
parallel runtime/writer
unused interface/protocol
repository wrapper
receipt/evidence wrapper
legacy candidate-to-entry path
duplicate Shadow/Portfolio shape
obsolete compatibility reader
stale docs
```

**Real market window required?**  
No for most work.

**Acceptance**

- failure diagnosis query/report is usable by research/operator workflows;
- each retained abstraction names its consumer/failure mode;
- safe deletions have consumer inventory and replay/differential proof where historical compatibility matters;
- no Big Bang rewrite.

**System capability gained**  
More research value with a smaller, clearer architecture surface.

---

# P2 Work Package

## WP-FORMAL-RESEARCH-01 — Formal PIT / Locked OOS / Calibration / Qualification

**Current problem**  
Formal engineering owners exist, but qualified source/PIT/OOS/calibration/economic evidence does not.

**Goal**  
Move only surviving exploratory hypotheses into formal qualification when the required independent evidence is available.

**Technical scope**  
Qualified Provider facts, Formal PIT, frozen Dataset/Protocol, purge/embargo, untouched Locked OOS, multiplicity control, calibration where probability is claimed, economic/cost/capacity evidence and qualification decisions.

**External dependency**  
Yes — qualified historical/PIT evidence and untouched observations.

**Acceptance**

- no reuse of exploratory/OOS observations outside frozen policy;
- every result-affecting owner resolved by exact identity/hash;
- formal statistical and economic floors independently evaluated;
- failure remains rejected/blocked rather than relaxed.

**System capability gained**  
Credible formal research claims rather than engineering-complete formal machinery.

---

# P3 / Future Work Package

## WP-CONTROLLED-EXECUTION-01 — Optional Controlled Broker Execution

**Precondition**  
Blueprint A has credible Alpha/Strategy/Prospective evidence and Manual production has a separately approved operational case for automation.

**Scope**  
Broker adapter, authenticated order authority, preview, reconciliation, duplicate-order prevention, cancellation semantics, capital/risk limits, approval and kill switch.

**Status**  
`DEFERRED`. It is not required to complete the current Alpha Research OS.

---

# Evidence gates between work packages

The roadmap is conditional, not a conveyor belt.

```text
Baseline has no ranking information
→ do not jump to complex ML; revisit target/data/features

Candidate sample is starved
→ fix/diagnose gate and coverage before Forecast work

Forecast remains NOT_ESTIMABLE
→ diagnose sample/estimator/conditioning; do not lower the floor just to obtain output

Gross economics are negative
→ return to factor/candidate/target/horizon

Gross positive but Net negative
→ prioritize cost/turnover/liquidity/entry/portfolio

Historical survives, prospective fails
→ investigate leakage/stability/drift/availability before qualification
```

---

# Top 5 highest-value actions

If only five things can be funded next:

1. **WP-GOLDEN-LOOP-01** — make one complete decision-to-attribution path the project’s proof spine.
2. **WP-BASELINE-ALPHA-01** — establish a transparent benchmark before additional model sophistication.
3. **WP-FACTOR-DISCOVERY-01** — use ablation/de-duplication to learn which existing Context/Factor layers actually add information.
4. **WP-PROSPECTIVE-01** — start the future evidence clock early because lost prospective time cannot be reconstructed.
5. **WP-STRATEGY-PROOF-01** — convert any surviving predictive information into executable net economics.

`WP-ATTRIBUTION-COMPRESSION-01` runs alongside these where the Golden Loop reveals redundant architecture.

---

# Roadmap guardrails

- Do not add a new top-level Runtime.
- Do not introduce a new business Authority when an existing owner can preserve the invariant.
- Do not treat engineering completion as Alpha proof.
- Do not use Formal/OOS/Prospective labels without owner evidence.
- Do not tune negative results until they become positive without creating a new frozen experiment.
- Do not build all Future Scope in one release.
- Do not preserve an abstraction solely because it already exists.
- Prefer one complete Work Package over many disconnected TODOs.

After each Work Package, update `Current-State.md`, `Capability-Matrix.md`, `Gap-Register.md` and this roadmap from the new executable/evidence baseline.