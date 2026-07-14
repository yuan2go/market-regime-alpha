# The Constitution of Market Regime Alpha

# Volume VIII — Validation Constitution

> **Document:** `docs/constitution/07-Validation-Constitution.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide validation design, sample isolation, out-of-sample evidence, sealed-test governance, statistical and economic proof, robustness, promotion, degradation, quarantine and retirement rules  
> **Applies to:** Research hypotheses, datasets in assigned research roles, features, factors, Candidate Discovery models, probability models, Market Regime models, ETF and Theme Rotation models, Entry policies, Position Lifecycle policies, Exit policies, complete strategies, portfolio-facing proposals, execution-aware simulations, experiment runners, metrics, reports, agents, Legacy migration and future production candidates  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, `02-Architecture-Blueprint.md`, `03-Research-Framework.md`, `04-Data-Constitution.md`, `05-Factor-Constitution.md`, and `06-Strategy-Constitution.md`

---

## 0. Purpose

`market-regime-alpha` is an Alpha Research Operating System for the China A-share market.

Its purpose is not to produce the largest number of backtests, the highest historical return discovered after repeated iteration, or the most persuasive chart.

Its purpose is to create a controlled process in which research objects can earn, lose and recover authority through evidence.

A research result can look strong and still be invalid because:

- the target was changed after seeing results;
- the universe was selected after observing winners;
- thresholds were tuned on the reported test set;
- overlapping labels leaked across sample boundaries;
- the same sample was repeatedly inspected until a favorable model appeared;
- a probability was evaluated only by hit rate and never calibrated;
- a Candidate model was judged only by strategy P&L;
- an Exit model was judged by one universal sell-point hit rate despite different exit intents;
- a factor was strong standalone but added nothing beyond existing information;
- a backtest ignored T+1, suspension, price limits, transaction costs or execution delay;
- hundreds of rules were tried while only the winning configuration was reported;
- a sealed test was opened, failed, modified against, and reused until it passed;
- a result was reproducible only on one mutable local directory;
- a strategy was promoted because one metric improved while coverage, turnover, drawdown or tail risk deteriorated materially.

The purpose of this Validation Constitution is therefore to answer one governing question:

> **What evidence is required before a research object may claim higher authority, and how must that authority be constrained, monitored, degraded, quarantined or retired?**

The central rule is:

> **No research object is trusted because it backtested well. It earns authority only through identity-stable, point-in-time-correct, sample-isolated, reproducible, decision-aligned, economically realistic and scope-specific evidence.**

This document defines:

- the distinction between research result, validation evidence and authority;
- canonical sample roles;
- sample-isolation and test-reuse rules;
- time-series, cross-sectional and panel split principles;
- walk-forward validation;
- purging and embargo where applicable;
- experiment identity and immutable evidence artifacts;
- baseline and benchmark requirements;
- object-specific validation protocols;
- probability calibration;
- statistical uncertainty and dependence;
- multiple testing and selection-bias governance;
- ablation and attribution;
- robustness and stress testing;
- economic and A-share execution validation;
- promotion, shadow, degradation, quarantine and retirement gates;
- sealed-test governance;
- agent-assisted validation rules;
- Legacy validation migration.

This document intentionally does **not** define:

- provider-specific data contracts;
- feature formulas;
- permanent strategy thresholds;
- one universal numeric Sharpe, IC, hit-rate or p-value threshold;
- final portfolio optimization mathematics;
- broker-specific live execution APIs.

Those responsibilities belong to the Data, Factor, Strategy, Portfolio, Execution and lower-level specification layers.

---

# 1. Constitutional Position of Validation

## 1.1 Validation is a claim-to-evidence contract

A validation result must always answer:

```text
What exact claim
about what exact object
for what exact scope
was tested
using what exact evidence
under what exact protocol?
```

The project does not accept a context-free statement such as:

```text
The model works.
```

A valid claim is closer to:

```text
Candidate Model C
for PIT-eligible liquid A-shares
at decision time T
for Target Y and Horizon H
using Dataset D
under Split Policy S
with Feature Set F
and Model Artifact M
achieved Evidence E
relative to Baseline B
under Validation Protocol V.
```

Authority is therefore attached to a scoped claim, not to a model name.

---

## 1.2 Validation does not create truth beyond the tested scope

Evidence obtained for:

```text
Liquid A-shares
14:55 decision time
next-session MFE target
2022–2026 market conditions
```

does not automatically authorize:

```text
all A-shares
09:30 decisions
multi-month holding
future unseen regimes
```

Generalization must be demonstrated, not assumed.

---

## 1.3 Research evidence and operational authority are different

A research object may have strong historical evidence and still lack operational authority because of:

- unavailable production data;
- unstable latency;
- unreconciled state ownership;
- execution incompatibility;
- data licensing constraints;
- monitoring gaps;
- unresolved implementation risk.

Therefore:

```text
Research Validation
        ≠
Operational Readiness
        ≠
Live Capital Authority
```

The project is research-first.

Promotion to production or live capital, if ever pursued, requires additional controls beyond historical evidence.

---

# 2. The Validation Authority Model

The project separates the following concepts:

```text
Research Object
    ↓
Research Claim
    ↓
Validation Protocol
    ↓
Evidence Artifact
    ↓
Evidence Review
    ↓
Authority Decision
    ↓
Monitoring
    ↓
Degradation / Quarantine / Retirement
```

These stages must not be collapsed.

---

## 2.1 Research Object

A research object may be:

- a feature;
- a factor;
- a Candidate model;
- a calibration model;
- an Entry policy;
- a Hold policy;
- an Add policy;
- a Reduce policy;
- a Rotation policy;
- an Exit policy;
- a Market Regime model;
- an ETF or Theme Rotation model;
- a complete strategy;
- a strategy composition;
- a risk policy;
- an execution assumption set.

Different object types require different metrics.

---

## 2.2 Research Claim

The claim must identify, as applicable:

```text
target
horizon
population
universe
instrument type
decision time
role
market context
strategy state
data eligibility
```

A result without a defined claim is descriptive output, not formal validation evidence.

---

## 2.3 Validation Protocol

The protocol defines:

- sample roles;
- split policy;
- leakage controls;
- baselines;
- metrics;
- statistical treatment;
- economic assumptions;
- robustness tests;
- promotion conditions;
- sealed-test rules where applicable.

A protocol should be frozen before final evaluation.

---

## 2.4 Evidence Artifact

Formal evidence must be identifiable and reconstructable.

An evidence artifact should preserve, as applicable:

- experiment identity;
- dataset identity;
- split identity;
- target identity;
- feature set identity;
- model or policy identity;
- execution assumptions;
- metric definitions;
- result tables;
- diagnostics;
- logs;
- checksums;
- code revision;
- dependency environment;
- review decision.

---

## 2.5 Authority Decision

The result of validation is not only a metric.

It is a decision such as:

```text
REJECT
REVISE
REPRODUCIBLE_ONLY
VALIDATED_FOR_SCOPE
PROMOTION_CANDIDATE
SHADOW_QUALIFIED
PROMOTED_FOR_SCOPE
DEGRADED
QUARANTINED
RETIRED
```

The exact workflow state may be represented by future registries.

The constitutional rule is that authority state must be explicit.

---

# 3. Evidence Authority Levels

The project uses an evidence ladder rather than a binary valid/invalid label.

A logical evidence ladder is:

```text
E0 — IDEA
E1 — EXPLORATORY
E2 — REPRODUCIBLE
E3 — CONTROLLED_VALIDATION
E4 — OOS_VALIDATED
E5 — SEALED_TESTED, where required
E6 — PROMOTION_CANDIDATE
```

Operational states such as:

```text
SHADOW
PROMOTED_FOR_SCOPE
DEGRADED
QUARANTINED
RETIRED
```

are authority or lifecycle states, not evidence levels.

---

## 3.1 `E0 — IDEA`

The object has a concept or hypothesis but no meaningful empirical evidence.

Allowed:

- design discussion;
- feature proposal;
- theory translation;
- exploratory planning.

Not allowed:

- predictive claims;
- promotion claims;
- calibrated probability claims.

---

## 3.2 `E1 — EXPLORATORY`

The object has been examined on exploratory data or flexible research samples.

Useful for:

- hypothesis screening;
- debugging;
- rough directionality;
- metric design;
- finding obvious failure modes.

Exploratory evidence may be heavily biased by iteration.

It must not be presented as final OOS evidence.

---

## 3.3 `E2 — REPRODUCIBLE`

The object can be rerun from identified inputs and produce the same semantic result.

This requires, as applicable:

- experiment identity;
- dataset identity;
- code revision;
- deterministic or controlled randomness;
- stable config;
- preserved artifacts.

Reproducibility is necessary.

It is not proof of Alpha.

---

## 3.4 `E3 — CONTROLLED_VALIDATION`

The object has been evaluated under predeclared or controlled sample roles and baselines without using the final untouched evidence for routine tuning.

This level may support:

- model selection;
- feature selection;
- policy comparison;
- calibration design;
- robustness screening.

It is still not necessarily final OOS authority.

---

## 3.5 `E4 — OOS_VALIDATED`

The object has been evaluated on data that was not used to fit or select the final object under the declared protocol.

The OOS evidence must remain scoped to:

- target;
- population;
- decision time;
- data contract;
- model or policy identity;
- evaluation period.

Repeated adaptation to the same OOS sample reduces its independence.

---

## 3.6 `E5 — SEALED_TESTED`

A promotion candidate has been evaluated on a restricted, previously uninspected final holdout under a readiness gate.

Sealed testing is a scarce evidence resource.

It must not become the normal development loop.

Not every exploratory feature requires a sealed test.

High-authority promotion claims may.

---

## 3.7 `E6 — PROMOTION_CANDIDATE`

The object has sufficient evidence to enter a formal promotion review.

This does not mean automatic promotion.

Promotion additionally considers:

- operational feasibility;
- risk;
- monitoring;
- dependency readiness;
- unresolved incidents;
- interaction with current promoted systems.

---

# 4. Data Eligibility and Sample Role Are Independent

The Data Constitution defines **what data is eligible to support what class of claim**.

The Validation Constitution defines **what role a dataset or partition plays in a validation protocol**.

The two dimensions are independent.

```text
Data Eligibility Class
        +
Sample / Research Role
        =
Allowed Validation Use
```

For example:

```text
Eligibility: FORMAL_RESEARCH
Role: SEALED_TEST
```

means:

- the data may be eligible for formal research;
- the partition is access-restricted;
- the Validation System controls when it may be opened.

---

## 4.1 Canonical sample roles

The platform-level sample roles are:

```text
DEVELOPMENT
TRAIN
VALIDATION
CALIBRATION
OOS_TEST
SEALED_TEST
SHADOW_OBSERVATION
```

Not every experiment requires every role.

The roles used must be explicit.

---

## 4.2 `DEVELOPMENT`

Used for:

- exploration;
- debugging;
- feature design;
- metric design;
- early hypothesis iteration.

Development data may be inspected repeatedly.

Its repeated use means it cannot later be treated as untouched evidence without explicit reclassification and justification.

---

## 4.3 `TRAIN`

Used to fit learned parameters such as:

- model coefficients;
- trees;
- neural weights;
- embeddings;
- empirical priors;
- learned thresholds;
- learned normalization parameters.

Anything learned from TRAIN becomes part of the model or research artifact identity.

---

## 4.4 `VALIDATION`

Used for controlled model or policy selection, such as:

- hyperparameter comparison;
- feature selection;
- architecture comparison;
- threshold selection;
- early stopping;
- strategy-component selection.

Repeated optimization against VALIDATION is permitted within the declared protocol.

It consumes validation independence.

---

## 4.5 `CALIBRATION`

Used to fit probability or score calibration artifacts where required.

Examples:

- Platt-style calibration;
- isotonic calibration;
- empirical calibration maps;
- probability bin mapping.

Calibration data must not be the final untouched test by default.

If VALIDATION is also used for calibration, that dual role must be explicit.

---

## 4.6 `OOS_TEST`

Used to evaluate a frozen or selected object outside the data used for fitting and routine selection.

OOS_TEST should not become a hidden tuning set.

If repeated inspection changes model or policy design, the sample has become part of the development feedback loop and its future authority must be reduced.

---

## 4.7 `SEALED_TEST`

Used as a restricted final holdout for high-authority evaluation.

Before access:

- candidate identity is frozen;
- readiness checks pass;
- metrics are defined;
- baselines are defined;
- the access event is logged.

After access, the sample is no longer untouched for the same research lineage.

---

## 4.8 `SHADOW_OBSERVATION`

Used for forward observation without granting automatic capital authority.

It may measure:

- live data availability;
- proposal frequency;
- decision drift;
- calibration drift;
- execution feasibility;
- state stability;
- operational failures.

Shadow data can become future research data, but its use and availability timeline must remain explicit.

---

# 5. Terminology Migration from Current MACD OOS Assets

The current repository contains useful local terminology that must be preserved without becoming conflicting platform ontology.

---

## 5.1 Legacy `rehearsal_range` is not the Data Constitution eligibility class

Current `macd_oos.py::DataSplitManifest` contains:

```text
train_range
validation_range
rehearsal_range
test_range
```

The `rehearsal_range` is a MACD-specific sample role in that implementation.

The Data Constitution also defines:

```text
REHEARSAL
```

as a **data eligibility class**.

These are different concepts.

The future platform must not reuse one ambiguous field name for both.

Migration should map the Legacy sample role to an explicit Validation role or workflow stage while preserving historical manifests.

---

## 5.2 Legacy `FORMAL_FINAL_CANDIDATE` is not a new global data eligibility class

Current `macd_oos.py::DatasetClassification` contains:

```text
FIXTURE
REHEARSAL
FORMAL_FINAL_CANDIDATE
```

This is a useful local MACD OOS contract.

The global Data Constitution defines the canonical eligibility model:

```text
UNQUALIFIED
EXPLORATORY
REHEARSAL
FORMAL_RESEARCH
```

Future migration should separate:

```text
Data Eligibility
```

from:

```text
Validation / Promotion Role
```

rather than creating parallel platform-wide eligibility ontologies.

---

# 6. Sample Isolation Constitution

Sample isolation is a core anti-leakage requirement.

The project must be able to answer:

```text
Which observations influenced fitting?
Which influenced selection?
Which influenced calibration?
Which were used only for evaluation?
Which remained sealed?
```

---

## 6.1 Random row splits are not a safe default for market data

Market observations are dependent across:

- time;
- symbols;
- sectors;
- themes;
- overlapping labels;
- common market events.

A random row split may place nearly identical market states on both sides of a split.

Therefore random row splitting requires explicit justification.

---

## 6.2 Chronology is the default constraint for predictive market research

Where the claim concerns future decisions, evaluation should normally preserve historical order.

The system must not train on information from dates later than the evaluation decision period unless the experiment is explicitly non-causal and labeled accordingly.

---

## 6.3 Cross-sectional panel data requires date-aware splitting

Candidate Discovery operates on cross-sections.

The validation design should preserve the fact that all securities at one decision time share market context.

The project must not create artificial independence by randomly distributing rows from the same trade date across train and test.

---

## 6.4 Symbol holdout is supplementary, not a substitute for time OOS

Holding out symbols can test cross-sectional transfer.

It does not, by itself, prove future-time generalization.

A robust design may combine:

- chronological holdout;
- symbol holdout;
- regime analysis;
- board or liquidity segment analysis.

---

## 6.5 Target overlap must be considered

When labels use future windows, nearby observations may share future returns.

For example:

```text
Decision at T
Target uses T+1 ... T+N
```

and:

```text
Decision at T+1
Target uses T+2 ... T+N+1
```

may have overlapping label information.

The validation protocol must assess whether this overlap creates leakage or materially inflated independence assumptions.

---

# 7. Purging and Embargo

Purging and embargo are tools for controlling boundary leakage where observations or labels overlap.

They are not mandatory rituals for every experiment.

They must be used when justified by the target and data structure.

---

## 7.1 Purging

Purging may remove observations whose label-information windows overlap across a train/evaluation boundary.

The required purge logic depends on:

- prediction horizon;
- label construction;
- feature availability;
- event windows;
- position path dependence.

The Constitution does not impose one universal number of bars.

---

## 7.2 Embargo

An embargo may create a gap after a training or selection period before the next evaluation period when dependence or information carryover requires it.

The embargo length must be justified by the research design.

---

## 7.3 Purging and embargo do not repair fundamentally leaked data

They cannot fix:

- future-adjusted features;
- current universe backfilled into history;
- future publication data;
- labels accidentally included as features;
- test-set tuning.

Those are upstream validity failures.

---

# 8. Walk-Forward Validation

Walk-forward validation is a first-class project capability.

A canonical pattern may be:

```text
Train Window
    ↓
Validation / Calibration Window
    ↓
Forward Evaluation Window
    ↓
Advance Time
    ↓
Repeat
```

The exact window structure depends on the object.

---

## 8.1 Expanding and rolling windows are distinct protocols

The project may use:

```text
Expanding Training Window
```

or:

```text
Rolling Training Window
```

These imply different assumptions about:

- regime persistence;
- concept drift;
- memory length;
- retraining frequency.

The choice is part of experiment identity.

---

## 8.2 Walk-forward folds must remain individually visible

A final average must not hide fold instability.

Reports should preserve, as applicable:

- per-fold metrics;
- per-fold sample counts;
- per-fold regimes;
- worst fold;
- dispersion;
- sign consistency;
- degradation over time.

---

## 8.3 Re-fitting is allowed only under the declared protocol

A walk-forward experiment may re-fit models or calibration artifacts at each fold.

The fitting schedule must be deterministic and reproducible.

A model must not receive future information because the research runner happened to materialize the full dataset in advance.

---

## 8.4 Walk-forward does not eliminate model-selection bias

Trying hundreds of model variants and reporting only the best walk-forward result still creates selection bias.

Experiment history and candidate count remain relevant.

---

# 9. Experiment Identity Constitution

Every formal validation result must have an immutable or reconstructable experiment identity.

A project-wide `ExperimentIdentity` should eventually generalize the strengths of the current `MACDExperimentIdentity`.

A logical identity includes, as applicable:

```text
experiment_id
parent_experiment_id
research_program_id
research_charter_version
hypothesis_id
target_id
universe_id
dataset_id
dataset_manifest_hash
split_policy_id
split_manifest_hash
feature_set_id
factor_versions
model_id
model_artifact_hash
calibration_artifact_id
strategy_id
entry_policy_id
lifecycle_policy_id
exit_policy_id
portfolio_assumption_id
execution_config_hash
metric_contract_version
random_seed
git_commit
dependency_lock_hash
runtime_environment
run_mode
sealed_test_access_state
```

Not every object uses every field.

Every result-affecting field must be captured somewhere in identity or referenced artifacts.

---

## 9.1 Identity drift invalidates comparison

Two experiments cannot be treated as a controlled comparison when unintended fields differ.

The project should be able to distinguish:

```text
Intended Experimental Variable
```

from:

```text
Uncontrolled Context Change
```

---

## 9.2 Current MACD identity is a valuable implementation pattern

The current `MACDExperimentIdentity` already captures:

- Git commit;
- dataset version;
- data-split hash;
- pipeline identity;
- algorithm versions;
- bar contract;
- price adjustment;
- data quality rules;
- sizing owner;
- execution config;
- MACD parameters;
- policy configuration.

This pattern should be generalized.

It should not remain limited to MACD research.

---

## 9.3 Config hash is evidence identity, not display metadata

The project should use canonical serialization and content hashes for result-affecting configuration where practical.

A human-readable profile name such as:

```text
balanced
```

or:

```text
aggressive
```

is not sufficient experiment identity.

---

# 10. Immutable Validation Artifacts

Formal runs should produce immutable or non-overwritable evidence artifacts.

A completed artifact may include:

```text
run manifest
experiment identity
dataset references
split manifest
config hashes
metrics
predictions
trade / proposal traces
counterfactual events
quality report
logs
checksums
review decision
```

---

## 10.1 A result directory is not authoritative if it can silently change

The project rejects:

```text
reports/latest/
```

as the only evidence record for formal promotion.

A mutable convenience pointer may exist.

The underlying run artifact must remain identifiable.

---

## 10.2 Current immutable-run pattern is valuable

The current `write_immutable_run_artifact()` pattern:

- rejects duplicate run IDs;
- stages output atomically;
- validates artifact layout;
- writes checksums;
- marks completion only after successful construction.

This is a strong pattern to generalize.

---

# 11. Baseline Constitution

No research object may claim improvement without an appropriate baseline.

The correct baseline depends on the decision problem.

A baseline ladder may include:

```text
Null / No-Signal Baseline
Naive Persistence Baseline
Cash / Hold Baseline
Market or Benchmark Baseline
Simple Deterministic Rule
Current Legacy Model
Current Promoted Model
Ablated Parent Model
```

Not every experiment needs every baseline.

The selected baseline must make the claimed improvement meaningful.

---

## 11.1 Baseline strength must match the claim

A complex Candidate model should not claim success merely by beating a deliberately weak random model when a simple momentum or current Legacy model is the real practical alternative.

---

## 11.2 Baseline changes must be explicit

The project must not compare a new model against an older weak baseline while silently ignoring a stronger currently promoted baseline.

---

## 11.3 No-action and hold baselines are different

For strategy research:

```text
NO_ACTION
```

and:

```text
HOLD EXISTING POSITION
```

represent different counterfactuals.

The baseline must reflect the actual decision state.

---

# 12. Metric-to-Decision Alignment

A metric is valid only when it measures the decision problem being studied.

The project rejects one universal metric for all research objects.

---

## 12.1 Prediction metrics do not replace strategy metrics

A Candidate model may improve ranking quality without improving a specific Entry policy.

A strategy may improve P&L because of sizing or risk rules even if Candidate ranking is unchanged.

Both layers must be measured separately.

---

## 12.2 Strategy P&L does not prove every component

A profitable complete strategy does not prove that:

- every factor adds value;
- every Entry gate helps;
- every Add rule helps;
- every Exit rule helps.

Component evidence and integrated evidence are both required.

---

## 12.3 Hit rate is not universal proof

A high hit rate can coexist with:

- poor payoff ratio;
- large tail losses;
- excessive turnover;
- weak capacity;
- low coverage;
- negative expected value after costs.

A low hit rate can coexist with positive expectancy.

Hit rate must be interpreted in context.

---

# 13. Candidate Discovery Validation Protocol

Candidate Discovery is the current first strategic research priority.

It is a cross-sectional prediction and ranking problem.

A Candidate validation package should define:

```text
Decision Time
PIT Universe
Target
Horizon
Candidate Population
Ranking Direction
Top-K or Quantile Scope
Benchmark
Execution Assumption, if economic outcomes are reported
```

---

## 13.1 Candidate metrics may include

As applicable:

- coverage;
- eligible-universe coverage;
- IC;
- RankIC;
- IC stability;
- top-K hit rate;
- top-K average forward return;
- top-K excess return;
- top-K MFE;
- top-K MAE;
- quantile spread;
- monotonicity;
- precision and recall for explicit events;
- calibration for probability outputs;
- ranking turnover;
- sector and theme concentration;
- overlap with prior top-K sets;
- uncertainty quality.

No single metric is sufficient.

---

## 13.2 Candidate validation must preserve all eligible candidates

The project must not report only selected winners.

Where practical, validation should preserve:

- all eligible instruments;
- predictions;
- ranks;
- realized targets;
- rejection or missingness states.

This is necessary for correct ranking and calibration analysis.

---

## 13.3 Candidate P&L is policy-dependent

A Candidate model can be evaluated economically through a standardized portfolio or Entry baseline.

That result must be labeled as:

```text
Candidate Model
+
Evaluation Policy
```

not as pure Candidate quality.

---

## 13.4 Cross-sectional dependence must remain visible

Thousands of stock rows on one date do not create thousands of independent market experiments.

Date-level and market-level dependence should be considered in uncertainty analysis.

---

# 14. Factor Validation Protocol

Factor validation follows the Factor Constitution.

A formal factor claim should evaluate, as applicable:

- definition correctness;
- PIT materialization;
- standalone relationship;
- IC / RankIC;
- monotonicity;
- quantile spread;
- stability across folds;
- population stability;
- regime interaction;
- redundancy;
- incremental value;
- economic value;
- missingness sensitivity;
- operational cost.

---

## 14.1 Standalone evidence is not enough

A factor with attractive standalone IC may add no information to the current model.

A weak standalone factor may add useful conditional information.

Therefore formal evaluation should distinguish:

```text
Standalone Value
Incremental Predictive Value
Incremental Economic Value
```

---

## 14.2 Factor-family concentration affects interpretation

A model with many OHLCV transformations may show stable performance.

Validation must still disclose concentration by source-information family where relevant.

The number of columns is not the number of independent information sources.

---

# 15. Entry Policy Validation Protocol

Entry is evaluated conditional on an opportunity set.

The core question is not merely:

```text
Did the accepted entry make money?
```

It is:

> **Did the Entry policy improve decisions relative to a defined Candidate or baseline opportunity set?**

---

## 15.1 Entry validation should preserve accepted and rejected opportunities

Where practical, compare:

```text
Candidate Opportunities
        ↓
Accepted by Entry
Rejected by Entry
```

Relevant metrics may include:

- accepted coverage;
- rejected coverage;
- avoided losses;
- missed profits;
- change in expected return;
- change in MFE / MAE;
- execution feasibility;
- timing slippage;
- opportunity capture;
- turnover;
- concentration.

---

## 15.2 Gate attribution is required

For gates such as:

- MACD confirmation;
- ETF context;
- Theme context;
- flow confirmation;
- Chan structure;
- Tuishen-inspired confirmation;
- risk gate;

the project should preserve controlled comparisons where practical.

A gate that blocks many losses and many larger winners must not be judged only by block accuracy.

---

# 16. Position Lifecycle Validation Protocol

Position Lifecycle is path-dependent.

It cannot be validated as a collection of isolated buy/sell points only.

The canonical lifecycle actions are:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Each action requires an appropriate counterfactual.

---

## 16.1 HOLD validation

A HOLD decision should be evaluated relative to alternatives such as:

```text
Hold
versus
Reduce
Exit
Rotate
```

Relevant evidence may include:

- remaining return;
- remaining MFE / MAE;
- drawdown after hold;
- opportunity cost;
- regret relative to eligible alternatives;
- state duration;
- thesis persistence.

Hindsight-optimal exit is a diagnostic, not an executable baseline.

---

## 16.2 ADD validation

ADD must be evaluated as marginal exposure.

The relevant counterfactual is not only:

```text
Position after ADD
versus
No position
```

but often:

```text
Existing position + ADD
versus
Existing position without ADD
```

Relevant evidence may include:

- marginal P&L;
- marginal drawdown;
- added MAE;
- incremental utility;
- concentration impact;
- follow-through success;
- failed-add clustering.

---

## 16.3 REDUCE validation

REDUCE may be evaluated through:

- avoided loss;
- missed upside;
- volatility reduction;
- drawdown reduction;
- capital released;
- opportunity-cost improvement;
- remaining-position outcome.

The intent must be explicit.

---

## 16.4 ROTATE validation

ROTATE requires a comparative counterfactual:

```text
Hold Current Position
```

versus:

```text
Exit / Reduce Current
+
Enter Alternative
-
Switching Costs
```

Validation should consider:

- relative return improvement;
- switching cost;
- execution feasibility;
- turnover;
- concentration change;
- risk change;
- alternative availability at the actual decision time.

---

## 16.5 Path-level attribution is required

A lifecycle policy can change later opportunities because earlier actions changed position state.

Therefore event-level metrics should be supplemented by path-level evaluation where practical.

---

# 17. Exit Validation Protocol

Exit is not one universal event.

The project distinguishes intents such as:

```text
PROFIT_TAKING
RISK_STOP
THESIS_INVALIDATION
TREND_INVALIDATION
STRUCTURE_BREAK
DISTRIBUTION_EXHAUSTION
TIME_EXPIRY
ROTATION
FORCED_EXIT
```

Each intent may require different metrics.

---

## 17.1 Profit-taking validation

Possible diagnostics include:

- realized profit;
- subsequent opportunity retained or missed;
- drawdown avoided after exit;
- capture ratio relative to an executable benchmark;
- opportunity cost.

An ex-post perfect high is not an executable target and must not be treated as the primary benchmark.

---

## 17.2 Risk-stop validation

Possible evidence includes:

- tail loss avoided;
- MAE reduction;
- false-stop frequency;
- rebound missed;
- risk-event severity;
- survival or ruin protection.

A good risk stop may intentionally have a low ordinary hit rate if it protects against rare severe losses.

---

## 17.3 Thesis-invalidation validation

The research question may be:

```text
After the declared thesis invalidates,
does expected remaining value materially deteriorate?
```

This differs from ordinary sell-point direction prediction.

---

## 17.4 Time-expiry validation

A fixed time exit may be compared as a deterministic baseline against:

- alternative fixed times;
- dynamic hold;
- dynamic exit;
- no-action continuation.

The project does not assume one fixed next-morning time is universally optimal.

---

## 17.5 No universal sell-point hit rate

The current Legacy `point_hit_rate.py` correctly marks itself as:

```text
Legacy timing hit-rate diagnostics;
not a sell-side evaluation contract.
```

That distinction is constitutionally correct.

A single metric such as:

```text
future return < 0 after sell point
```

cannot validate all Exit intents.

---

# 18. Market Regime Validation Protocol

A Market Regime model may be used as:

- descriptor;
- context;
- interaction term;
- strategy gate;
- risk input;
- direct strategy input.

Validation must match the role.

---

## 18.1 Classification accuracy is not enough

A regime label can be statistically stable but economically useless.

The project should evaluate, as applicable:

- state persistence;
- transition behavior;
- target separation by regime;
- conditional Candidate quality;
- conditional strategy performance;
- risk differentiation;
- decision improvement relative to no-regime baseline.

---

## 18.2 Regime-conditioned models require interaction evidence

If a factor or strategy is claimed to work only in `RISK_ON`, the project should evaluate:

```text
Factor / Strategy without Regime Conditioning
```

versus:

```text
Factor / Strategy with Regime Conditioning
```

and preserve coverage changes.

---

# 19. ETF and Theme Rotation Validation Protocol

ETF and Theme systems may serve as context or direct strategies.

Validation must declare the role.

---

## 19.1 Context validation

When ETF or Theme information is used upstream, evaluate whether it improves:

- Candidate ranking;
- top-K quality;
- Entry quality;
- regime interaction;
- risk control;
- universe efficiency.

The correct comparison is against the same downstream model without the context component.

---

## 19.2 Direct rotation strategy validation

A direct ETF rotation strategy should evaluate, as applicable:

- relative return;
- turnover;
- switching cost;
- drawdown;
- concentration;
- persistence;
- defensive behavior;
- benchmark-relative performance;
- robustness across ETF universe definitions.

---

## 19.3 Theme labels require PIT-valid membership

A strong historical theme result built from retrospective membership is not valid formal rotation evidence.

Data eligibility remains a prerequisite to validation authority.

---

# 20. Probability and Calibration Constitution

A probability output is a stronger semantic claim than a score.

The project must define:

```text
Event
Horizon
Population
Decision Time
Calibration Method
Calibration Sample
```

before claiming probability authority.

---

## 20.1 Discrimination and calibration are different

A model may rank opportunities well but produce poor probabilities.

The project should distinguish:

```text
Ranking Quality
```

from:

```text
Probability Calibration
```

---

## 20.2 Calibration metrics may include

As applicable:

- Brier score;
- log loss;
- reliability curves;
- calibration slope and intercept;
- expected calibration error or equivalent diagnostics;
- calibration by probability bin;
- calibration by regime;
- calibration by population segment.

No one metric is universally sufficient.

---

## 20.3 Calibration must be out-of-sample relative to the calibration fit

A calibration map evaluated on the same sample used to fit it is not final calibration evidence.

---

## 20.4 Probability drift requires monitoring

A probability model can retain rank quality while losing calibration.

Monitoring must be able to distinguish those failure modes.

---

# 21. Statistical Uncertainty Constitution

Market data is noisy, dependent and non-stationary.

A point estimate without uncertainty can create false precision.

The project should quantify uncertainty where practical and decision-relevant.

---

## 21.1 Sample count is not effective sample size

Ten thousand rows may represent far fewer independent market events because of:

- same-date cross-sectional dependence;
- overlapping horizons;
- repeated symbols;
- common sector shocks;
- common market shocks.

Validation should not imply independence merely from row count.

---

## 21.2 Confidence intervals should respect dependence where possible

Possible approaches may include:

- block bootstrap;
- date-clustered resampling;
- symbol-clustered analysis;
- two-way clustering where appropriate;
- fold-level aggregation;
- regime-stratified analysis.

The method must fit the research object.

---

## 21.3 Statistical significance is not economic significance

A tiny stable effect may be untradeable after:

- costs;
- slippage;
- turnover;
- capacity limits;
- concentration constraints.

Conversely, a large economically meaningful effect with few rare risk events may require different evidence than a high-frequency factor.

---

## 21.4 Absence of significance is not proof of no effect

The project must distinguish:

- evidence of no useful effect;
- insufficient sample;
- unstable effect;
- poor measurement;
- excessive noise.

Negative results should record the reason for uncertainty where possible.

---

# 22. Multiple Testing and Researcher Degrees of Freedom

A serious Alpha research system must account for how many choices were tried.

The project creates selection bias when it repeatedly varies:

- features;
- thresholds;
- windows;
- targets;
- universes;
- decision times;
- exit times;
- strategy states;
- factor combinations;
- metric definitions;

and reports only the winner.

---

## 22.1 Experiment history is evidence context

The project should preserve:

- parent experiment;
- variants tried;
- major rejected variants;
- selection criterion;
- final selection path.

A winning result after 500 attempts is not interpreted the same way as a predeclared single test.

---

## 22.2 Test-set optimization is prohibited

The project must not:

```text
Run Test
    ↓
Change Threshold
    ↓
Run Same Test
    ↓
Repeat Until Good
```

while continuing to call the sample an independent test.

---

## 22.3 Metric shopping is a form of multiple testing

Changing the primary metric after seeing results can create the same selection bias as changing model parameters.

Primary and secondary metrics should be declared before final evaluation where practical.

---

## 22.4 Statistical correction methods are tools, not substitutes for governance

Methods such as:

- false-discovery control;
- reality-check procedures;
- deflated performance statistics;
- multiple-comparison adjustments;

may be useful depending on the research program.

No correction can fully compensate for undocumented research iteration.

---

# 23. Ablation and Attribution Constitution

Ablation is mandatory whenever a claim depends on the incremental value of a component.

The canonical question is:

```text
What changes when this component is present versus absent,
with other relevant conditions controlled?
```

---

## 23.1 Controlled arms must differ only in intended variables

The current MACD four-arm design is a strong pattern:

```text
Baseline
Score Only
Policy Only
Full
```

This allows estimation of:

- score effect;
- policy effect;
- interaction effect;
- total effect.

The current `validate_four_arm_contexts()` and `validate_four_arm_identities()` patterns correctly reject unintended context differences.

This principle should be generalized.

---

## 23.2 Ablation is not only feature removal

Ablation may compare:

- feature present / absent;
- gate on / off;
- lifecycle component on / off;
- fixed exit / dynamic exit;
- real flow / OHLCV proxy;
- ETF context / no ETF context;
- regime-conditioned / unconditional;
- current model / simplified model.

---

## 23.3 Interaction effects must remain visible

The full system may perform better than the sum of isolated components.

It may also perform worse because components conflict.

The interaction is itself evidence.

---

# 24. Counterfactual Validation Constitution

Many policy components are best evaluated through counterfactuals.

Examples include:

- a gate that blocked an Entry;
- a REDUCE that lowered exposure;
- an ADD that increased exposure;
- an EXIT that ended a path;
- a ROTATE that replaced one opportunity with another.

---

## 24.1 Counterfactuals must be executable

The project must not evaluate a blocked decision using an impossible same-bar price or future extreme.

A counterfactual should respect:

- candidate time;
- next eligible execution time;
- tradability;
- lot size;
- price limits;
- costs;
- slippage;
- available state.

---

## 24.2 Current MACD counterfactual pattern is valuable

The current code already preserves:

- candidate time;
- next eligible execution time;
- original and adjusted paths;
- blocked and resized policies;
- avoided loss;
- missed profit;
- holding period;
- MAE;
- execution cost.

This should be generalized beyond MACD.

---

## 24.3 Counterfactual certainty must not be overstated

A counterfactual is a model of what would have happened under another feasible decision path.

Path dependence, market impact and later state changes may limit exactness.

The assumptions must remain explicit.

---

# 25. Economic Validation Constitution

Statistical predictiveness is not sufficient for strategy authority.

The project must evaluate whether the effect can survive economic reality.

---

## 25.1 Economic metrics may include

As applicable:

- net return;
- excess return;
- drawdown;
- volatility;
- downside risk;
- turnover;
- transaction cost;
- slippage;
- capacity;
- concentration;
- holding period;
- exposure;
- tail loss;
- hit rate;
- payoff ratio;
- expectancy;
- opportunity cost.

No single portfolio metric is universal.

---

## 25.2 Gross edge and net edge are different

Reports should distinguish:

```text
Model / Signal Edge Before Costs
```

from:

```text
Economic Edge After Realistic Costs
```

A model whose edge disappears under modest realistic costs has limited trading authority even if its predictive relationship is statistically real.

---

## 25.3 Cost sensitivity is required where turnover matters

A strategy should not rely on one exact cost assumption when small changes in slippage reverse the conclusion.

Sensitivity analysis may include:

- lower cost;
- base cost;
- stressed cost.

The exact scenarios belong to lower-level validation designs.

---

# 26. A-Share Execution Validation Constitution

A-share market structure is part of economic validation.

Where relevant, research must account for versioned rules and facts such as:

- T+1 sellability;
- lot size;
- suspension;
- ST and board-specific rules;
- price limits;
- previous close;
- next eligible execution;
- commissions;
- stamp duty;
- slippage;
- liquidity;
- corporate actions.

---

## 26.1 Signal time and execution time are distinct

A decision generated at time T must not be evaluated as if it filled before or at T unless the execution contract explicitly permits it.

The current counterfactual check requiring execution after candidate time is directionally correct.

---

## 26.2 Unfilled actions remain part of validation

A strong theoretical signal that frequently cannot execute is operationally weaker than its signal-only metrics suggest.

Validation should preserve:

- executable actions;
- blocked actions;
- block reasons;
- delayed actions;
- partial or modified execution where modeled.

---

## 26.3 Execution assumptions are versioned

Changing:

- slippage;
- fee schedule;
- fill model;
- price-limit handling;
- lot handling;

may materially change results.

These assumptions belong to experiment identity.

---

# 27. Robustness Constitution

A result should not earn high authority from one narrow configuration unless the claim itself is intentionally narrow.

Robustness asks whether the result survives reasonable variation.

---

## 27.1 Time robustness

Evaluate, as applicable:

- different periods;
- walk-forward folds;
- bull, bear and range conditions;
- high- and low-volatility regimes;
- changing liquidity conditions.

---

## 27.2 Population robustness

Evaluate, as applicable:

- market-cap segments;
- boards;
- industries;
- liquidity segments;
- symbol holdouts;
- ETF universes.

---

## 27.3 Parameter robustness

A strategy that works only at one exact threshold may be fragile.

Reasonable local perturbation can reveal:

- stable plateaus;
- cliffs;
- threshold overfitting;
- interaction sensitivity.

The project does not require every parameter to be insensitive.

It requires fragility to be visible.

---

## 27.4 Target and horizon robustness

A factor may genuinely be horizon-specific.

Validation should distinguish:

```text
Narrow but stable effect
```

from:

```text
Randomly selected winning horizon
```

---

## 27.5 Data-source robustness

Where equivalent independently sourced data exists, cross-source comparison may reveal:

- provider artifacts;
- timestamp differences;
- revision sensitivity;
- hidden data assumptions.

Cross-source agreement is useful but not mandatory when only one formally eligible source exists.

---

# 28. Stress and Failure-Mode Validation

Validation must look for how a system fails, not only how it succeeds.

Possible stress dimensions include:

- missing data;
- stale data;
- delayed bars;
- unavailable flow data;
- provider failure;
- market gap;
- limit-up / limit-down;
- suspension;
- regime transition;
- volatility spike;
- concentration shock;
- execution-cost increase;
- state corruption;
- model unavailability.

---

## 28.1 Fail-closed behavior is itself testable

A model that claims fail-closed behavior should be tested to ensure it does not silently substitute:

- neutral values;
- current data;
- fallback providers;
- stale state;
- permissive eligibility.

---

## 28.2 Risk controls require failure-mode tests

A risk control should not be validated only during ordinary profitable periods.

It should be evaluated in the conditions it is intended to protect against.

---

# 29. Sealed Test Constitution

A sealed test is a controlled final evidence event.

It is not another tuning loop.

---

## 29.1 Preconditions for sealed-test access

Before a sealed test may be opened, the project should require, as applicable:

```text
Candidate Identity Frozen
Dataset Manifest Valid
Split Manifest Valid
Data Eligibility Sufficient
PIT Checks Passed
Code Revision Identified
Working Tree / Build State Controlled
Tests / Lint / Type Checks Passed
Baseline Frozen
Metrics Frozen
Execution Assumptions Frozen
Ablation Context Valid
Run Artifact Path Ready
Access Authorized
```

The exact readiness schema may vary by research program.

---

## 29.2 Current `FinalTestReadiness` is a valuable pattern

The existing MACD OOS implementation already checks, among other things:

- clean working tree;
- tests, lint and type checks;
- finalized bars;
- no provisional bars;
- PIT adjustment;
- dataset manifest validity;
- split validity;
- four-arm identity integrity;
- cache identity integrity;
- baseline production profile;
- formal final-candidate classification.

This is a strong local readiness model.

The future platform should generalize the gate while aligning terminology with the Data Constitution.

---

## 29.3 Test access is an event

Opening a sealed sample must be traceable.

The project should record:

- who or what requested access;
- candidate identity;
- readiness result;
- access time;
- run ID;
- artifact location;
- outcome;
- post-test decision.

---

## 29.4 A failed sealed test must not be tuned against repeatedly

The project rejects:

```text
Open Sealed Test
    ↓
Fail
    ↓
Adjust Threshold
    ↓
Re-run Same Sealed Test
    ↓
Repeat Until Pass
```

After exposure, the sample has influenced research.

Further development may continue.

A new independent final holdout may be required for a new high-authority claim.

---

## 29.5 Material post-sealed changes create a new candidate

Changes to:

- target;
- feature set;
- model architecture;
- thresholds;
- Entry policy;
- Lifecycle policy;
- Exit policy;
- execution assumptions;

may invalidate the previous sealed-test claim for the changed object.

---

## 29.6 Genuine data corrections require incident governance

If a sealed dataset contains a real data defect, correction may be necessary.

The correction must not be disguised as ordinary tuning.

The project should preserve:

- original artifact;
- defect report;
- corrected artifact identity;
- affected result status;
- rationale for any re-evaluation.

---

# 30. Promotion Constitution

Promotion is a scope-specific governance decision.

It is not an automatic consequence of one passing metric.

A logical promotion condition is:

```text
PromotableForScope =
    DataEligible
    AND PITCorrect
    AND IdentityStable
    AND Reproducible
    AND BaselineRelevant
    AND DecisionMetricsAdequate
    AND IncrementalValueSupported
    AND OOSSupported
    AND EconomicRealitySupported
    AND RiskBounded
    AND RobustnessAcceptable
    AND Traceable
    AND NoCriticalUnresolvedIncident
```

Additional sealed-test or shadow requirements may apply to higher authority levels.

---

## 30.1 Promotion is object-specific

A factor may be promoted as:

```text
VALIDATED_FOR_SCOPE as a Candidate ranking input
```

without being authorized as:

```text
hard Entry gate
```

A Candidate model may be promoted while a new Exit policy remains exploratory.

---

## 30.2 Promotion scope must be explicit

Scope includes, as applicable:

- target;
- horizon;
- population;
- decision time;
- data class;
- strategy role;
- market regime;
- instrument type.

---

## 30.3 Promotion can be conditional

A result may be accepted with explicit limits such as:

- only liquid A-shares;
- only when required data is available;
- only as context, not a hard gate;
- only in shadow mode;
- only below a defined exposure cap.

Conditional authority must remain visible.

---

# 31. Promotion Review Outcomes

A promotion review may conclude:

```text
PASS
CONDITIONAL_PASS
REVISE
FAIL
QUARANTINE
```

The exact registry vocabulary may evolve.

The decision must include reason codes and evidence references.

---

## 31.1 `PASS`

Evidence supports the requested authority for the declared scope.

---

## 31.2 `CONDITIONAL_PASS`

Evidence supports limited authority with explicit constraints.

---

## 31.3 `REVISE`

The hypothesis remains plausible, but evidence or implementation is incomplete.

---

## 31.4 `FAIL`

The requested claim is not supported.

A failed result is preserved.

---

## 31.5 `QUARANTINE`

Authority is suspended because evidence integrity, data, implementation or operational safety is uncertain.

Quarantine is not the same as permanent retirement.

---

# 32. Shadow and Forward Validation

Historical OOS evidence cannot fully reproduce future operating conditions.

A promotion candidate may require shadow observation before higher authority.

---

## 32.1 Shadow validation should compare expected and observed behavior

Monitor, as applicable:

- data availability;
- prediction distribution;
- rank distribution;
- calibration;
- proposal frequency;
- action mix;
- state transitions;
- execution feasibility;
- latency;
- failures;
- regime mix.

---

## 32.2 Forward observation is not automatically statistically independent

A model may be changed during shadow observation.

If shadow results influence design, later claims must identify which data was used as development feedback.

---

# 33. Degradation Constitution

Promoted authority is revocable.

A factor, model or strategy may degrade because of:

- data drift;
- concept drift;
- calibration drift;
- market-structure change;
- provider change;
- execution-cost change;
- strategy crowding;
- implementation regression;
- regime shift;
- interaction with new portfolio components.

---

## 33.1 Monitoring must reflect original claims

A Candidate model should monitor Candidate metrics.

A calibrated probability should monitor calibration.

An Exit policy should monitor its intent-specific outcomes.

A strategy should monitor economic and risk outcomes.

One global P&L chart is not sufficient monitoring for every component.

---

## 33.2 Degradation thresholds should be predeclared where practical

The project should avoid deciding only after performance deteriorates whether the deterioration “counts.”

Possible triggers may include:

- sustained calibration error;
- sign reversal;
- coverage collapse;
- execution-feasibility decline;
- abnormal action distribution;
- unacceptable tail risk;
- data-quality incident;
- reproducibility failure.

Exact thresholds belong to object-specific monitoring specifications.

---

## 33.3 Degradation does not require immediate retirement

Possible responses include:

```text
Monitor
Reduce Authority
Shadow Only
Recalibrate
Retrain
Redesign
Quarantine
Retire
```

The response depends on failure mode.

---

# 34. Quarantine and Retirement Constitution

## 34.1 Quarantine

Use quarantine when:

- data integrity is uncertain;
- a serious implementation bug is discovered;
- a result cannot be reproduced;
- a provider changes semantics;
- sealed-test governance is violated;
- live behavior materially diverges from expected semantics.

Quarantined objects must not silently retain prior authority.

---

## 34.2 Retirement

Retirement is appropriate when:

- the hypothesis is no longer supported;
- a superior replacement exists;
- maintenance cost exceeds research value;
- the required data is no longer available;
- market structure invalidates the premise;
- the object is redundant.

Retirement preserves:

- identity;
- historical evidence;
- failure reason;
- replacement links;
- affected experiments or strategies.

---

# 35. Negative Results Constitution

Negative results are first-class research assets.

The project should preserve evidence that:

- a factor had no incremental value;
- a gate blocked too many winners;
- a timing rule increased turnover;
- an Exit policy reduced returns;
- a regime filter reduced coverage without sufficient benefit;
- a Level 2 feature added no value beyond OHLCV;
- a complex model failed to beat a simple baseline.

Deleting failed experiments encourages repeated rediscovery of the same failure.

---

# 36. Validation of Learned Priors, Thresholds and Calibration Artifacts

Any value learned from historical outcomes is a research artifact.

Examples include:

- empirical buy-point priors;
- learned subtype hit rates;
- thresholds selected from validation;
- calibration maps;
- learned factor weights;
- regime boundaries;
- similarity-memory outcomes.

---

## 36.1 Learned values must obey sample isolation

A prior estimated from one sample may be applied to later evaluation only if the estimation sample is part of the declared model-development process.

The evaluation sample must remain independent of the learned prior.

---

## 36.2 Hard-coded empirical priors are not timeless constants

The current `BUY_POINT_5D_PRIORS` are explicitly derived from a local 20-symbol, one-year, 5-minute report.

They are useful Legacy research artifacts.

They must not be interpreted as universal market constants.

Future migration should represent them as:

```text
Versioned Learned Artifact
+
Estimation Sample Identity
+
Target Definition
+
Validity Scope
```

---

# 37. Current Legacy Validation Audit

This Constitution is informed by the current repository.

The following interpretations are binding until superseded by more specific designs or specifications.

---

## 37.1 `macd_experiments.py::MACDExperimentIdentity`

**Current value:** rich result-affecting identity across code, dataset, split, pipeline, algorithm, policy, bar semantics, adjustment, data quality, sizing and execution.  
**Risk:** currently MACD-specific and not yet the universal experiment contract.  
**Constitutional interpretation:** strong implementation pattern for project-wide Experiment Identity.  
**Required evolution:** generalize to Candidate, Factor, Lifecycle, Exit, ETF and Market Regime research.  
**Action:** **Preserve + Generalize.**

---

## 37.2 MACD four-arm ablation

Current arms:

```text
baseline
score-only
policy-only
full
```

**Current value:** separates score effect, policy effect and interaction; validates that non-experimental context remains equal.  
**Risk:** valuable pattern may remain isolated to MACD.  
**Constitutional interpretation:** preferred controlled-attribution pattern for multi-role components.  
**Required evolution:** generalize factorial or controlled ablation where applicable.  
**Action:** **Preserve + Generalize.**

---

## 37.3 `macd_oos.py`

**Current value:** dataset manifests, split manifests, run manifests, immutable artifacts, checksums, final-test readiness, sealed test access control and identity linking.  
**Risk:** local terms such as `rehearsal_range` and `FORMAL_FINAL_CANDIDATE` can conflict with the newer project-wide Data Constitution ontology.  
**Constitutional interpretation:** strong Legacy OOS governance implementation, not the final universal vocabulary.  
**Required evolution:** preserve mechanisms while separating Data Eligibility, Sample Role and Promotion Status.  
**Action:** **Preserve governance mechanics + Normalize ontology.**

---

## 37.4 `formal_dataset_builder.py`

**Current value:** fail-closed rehearsal builder requiring PIT adjustment evidence, finalized bars, sidecars, manifest identity and immutable artifacts.  
**Risk:** current 5–10 symbol and 3–6 month MVP constraints could be mistaken for formal Alpha validation scope.  
**Constitutional interpretation:** data-pipeline rehearsal and contract-validation asset.  
**Required evolution:** keep its governance pattern; do not treat rehearsal success as predictive validation.  
**Action:** **Preserve + Generalize under Data Platform.**

---

## 37.5 `point_hit_rate.py`

**Current value:** useful forward-return diagnostics for Legacy timing points.  
**Risk:** buy and heterogeneous sell intents can be collapsed into one directional hit-rate interpretation.  
**Constitutional interpretation:** Legacy diagnostic only, consistent with its own module declaration.  
**Required evolution:** replace universal sell-side interpretation with intent-specific validation protocols.  
**Action:** **Preserve as diagnostic + Do not use as universal promotion metric.**

---

## 37.6 `buy_point_quality.py`

**Current value:** explicit subtype taxonomy and empirical historical priors.  
**Risk:** sample-derived priors are hard-coded into source and may contaminate later evaluation or become timeless rules.  
**Constitutional interpretation:** useful learned research artifact embedded in Legacy code.  
**Required evolution:** separate taxonomy from versioned prior artifact and estimation sample.  
**Action:** **Preserve taxonomy + Externalize learned priors.**

---

## 37.7 `backtest.py`

**Current value:** extensive integrated simulation and many real strategy hypotheses.  
**Risk:** very large threshold and state surface creates high researcher degrees of freedom, multiple-testing risk and attribution difficulty.  
**Constitutional interpretation:** Legacy behavior-preservation laboratory, not proof that every embedded rule is validated.  
**Required evolution:** characterize, extract components, register experiments, compare against baselines and preserve negative variants.  
**Action:** **Freeze uncontrolled rule accumulation + Extract under formal validation.**

---

## 37.8 `trend_snapshot.py`

**Current value:** practical research reporting and live-like observation.  
**Risk:** displayed probability-like fields and historical hit rates may be interpreted as formal predictive authority without target, calibration and OOS evidence.  
**Constitutional interpretation:** research interface and observation output, not automatic validation authority.  
**Required evolution:** attach model identity, target identity, calibration status and evidence status to predictive outputs.  
**Action:** **Preserve interface utility + Strengthen evidence semantics.**

---

# 38. V2 Validation System Direction

The future V2 Validation System should support:

```text
Research Charter
        ↓
Validation Protocol
        ↓
Dataset Role Assignment
        ↓
Experiment Identity
        ↓
Controlled Run
        ↓
Immutable Evidence Artifact
        ↓
Metric / Statistical / Economic Review
        ↓
Ablation / Robustness / OOS
        ↓
Sealed Test, when required
        ↓
Promotion Decision
        ↓
Shadow Monitoring
        ↓
Degradation / Quarantine / Retirement
```

The Validation System owns:

- sample-role semantics;
- split protocols;
- test-access governance;
- validation manifests;
- metric contracts;
- evidence artifacts;
- promotion evidence;
- degradation evidence;
- quarantine evidence.

It does not own:

- source data truth;
- feature definitions;
- strategy actions;
- portfolio allocation;
- broker execution.

---

# 39. Minimum Formal Validation Package

Before a research object can claim formal validation authority, it should have, at minimum, as applicable:

```text
1. Research Object Identity
2. Research Claim / Hypothesis Identity
3. Target Identity
4. Population / Universe Scope
5. Decision-Time and Horizon Semantics
6. Dataset Identity and Eligibility
7. Sample Roles
8. Split Policy and Split Identity
9. Leakage Review
10. Experiment Identity
11. Baseline(s)
12. Primary Metric Contract
13. Secondary / Risk Metrics
14. Reproducible Run Artifact
15. OOS Evidence, where required
16. Calibration Evidence, for probabilities
17. Ablation / Incremental Evidence
18. Robustness Evidence
19. Economic / Execution Evidence, where strategy-relevant
20. Failure Modes
21. Known Limitations
22. Promotion Scope Requested
23. Review Decision
24. Monitoring / Degradation Plan, for promoted objects
```

Higher authority may require sealed-test and shadow evidence.

---

# 40. Validation Anti-Patterns

The following patterns are constitutionally prohibited or must remain explicitly exploratory.

---

## 40.1 Backtest winner equals truth

```text
Highest historical return
=
Best model
```

without accounting for selection process, risk, robustness or OOS evidence.

---

## 40.2 Test-set tuning

Repeatedly changing the model after inspecting the reported test set while continuing to call it independent OOS.

---

## 40.3 Sealed-test grinding

Repeatedly modifying a candidate against the same sealed sample until it passes.

---

## 40.4 Random row split by default

Ignoring time, same-date dependence, overlapping labels or shared market context.

---

## 40.5 Full-sample preprocessing

Using future data to fit normalization, winsorization, PCA, clustering, calibration or priors.

---

## 40.6 Metric shopping

Changing the primary success metric after seeing which metric looks favorable.

---

## 40.7 Horizon shopping

Testing many future horizons and reporting only the winning horizon without preserving the selection context.

---

## 40.8 Universe shopping

Changing stock or ETF universe after observing which population produces favorable results.

---

## 40.9 Rule accumulation

Adding thresholds, gates and states after every failure without controlled attribution.

---

## 40.10 Standalone-factor theater

Promoting a factor because standalone IC is high even though it adds no incremental value to the current system.

---

## 40.11 P&L proves every component

Treating profitable integrated strategy results as proof that every internal factor and policy is useful.

---

## 40.12 Hit-rate absolutism

Using hit rate as universal proof regardless of payoff, tail risk, coverage, costs or decision intent.

---

## 40.13 Universal sell-point metric

Evaluating profit-taking, risk stop, thesis invalidation, rotation and forced exit with one identical future-direction metric.

---

## 40.14 Probability without calibration

Publishing a score as a probability because it lies between 0 and 1 or 0 and 100.

---

## 40.15 Row count as independent sample count

Ignoring temporal, cross-sectional and overlapping-horizon dependence.

---

## 40.16 Gross-return promotion

Ignoring transaction costs and execution feasibility for a high-turnover strategy.

---

## 40.17 Hindsight-optimal execution

Evaluating decisions at future high, low or same-bar unavailable prices.

---

## 40.18 Mutable evidence artifacts

Overwriting the exact data, config or result artifact supporting a formal claim.

---

## 40.19 Rehearsal success equals Alpha proof

Treating a pipeline rehearsal or fixture test as predictive market evidence.

---

## 40.20 Negative-result deletion

Discarding failed experiments so the same ideas are repeatedly rediscovered and selection history disappears.

---

## 40.21 Promotion by one attractive metric

Ignoring deterioration in coverage, drawdown, turnover, capacity, calibration or tail risk.

---

## 40.22 Agent-induced validation drift

An agent silently changes:

- target;
- metric;
- split;
- universe;
- sample role;
- baseline;
- execution assumption;
- threshold;
- sealed-test access;

in order to obtain a better result.

---

# 41. Agent Governance for Validation

Agents may assist with:

- experiment generation;
- split construction;
- metric computation;
- robustness runs;
- ablation;
- report generation;
- artifact validation;
- anomaly detection;
- promotion-review preparation.

Agents must not silently:

- inspect sealed data;
- change target after results;
- reclassify sample roles;
- replace a baseline;
- optimize against OOS while calling it untouched;
- suppress failed experiments;
- change execution assumptions;
- promote an object;
- rewrite negative evidence;
- alter metric definitions;
- bypass readiness gates.

Any agent-driven change affecting research identity must create traceable evidence.

---

# 42. Validation Review Questions

Every serious validation package should be reviewable through the following questions.

## Claim

- What exact claim is being tested?
- What is explicitly outside the claim?

## Object

- Is this a factor, model, policy, strategy or composite?
- What exact version is under review?

## Target

- What event or outcome is predicted?
- What is the horizon?
- Is the target aligned with the decision?

## Data

- Is the dataset eligible for this claim?
- Is point-in-time correctness established?
- Which dataset and sidecar versions were used?

## Sample Roles

- What is DEVELOPMENT?
- What is TRAIN?
- What is VALIDATION?
- What is CALIBRATION?
- What is OOS_TEST?
- What remains SEALED_TEST?

## Leakage

- Are labels overlapping?
- Is purging or embargo required?
- Were future normalization parameters used?
- Was current truth backfilled into history?

## Identity

- Can the exact experiment be reconstructed?
- Are code, config, data, split and execution identities fixed?

## Baseline

- What practical alternative is the object compared against?
- Is the baseline strong enough for the claim?

## Metrics

- Do the metrics match the decision problem?
- Are primary and secondary metrics explicit?
- Are risk and coverage visible?

## Statistics

- What is the effective sample structure?
- Are uncertainty estimates appropriate for dependence?
- How many variants were tried?

## Incremental Value

- What happens when the component is removed?
- Does it add predictive and economic value?

## Robustness

- Does the effect persist across time, population and reasonable parameter variation?
- Where does it fail?

## Economics

- Are costs and A-share execution constraints modeled where relevant?
- Does the edge survive realistic assumptions?

## Probability

- Is the output truly a probability?
- Was calibration fitted and tested correctly?

## OOS / Sealed Test

- Was the candidate frozen before final evaluation?
- Has the sample been inspected before?
- Is the access event traceable?

## Promotion

- What authority is being requested?
- For what exact scope?
- What unresolved risks remain?

## Monitoring

- How will degradation be detected?
- What triggers reduced authority, quarantine or retirement?

---

# 43. Current Refoundation Validation Constraints

Until explicitly changed by new evidence and a traceable decision, the following posture remains binding:

```text
Do not treat exploratory backtests as formal OOS evidence.
Do not use the same sample for fitting, selection, calibration and final proof without explicit role disclosure.
Do not tune against a reported OOS or sealed test while preserving its untouched label.
Do not treat a random row split as the default for market panel data.
Do not ignore overlapping target windows at sample boundaries.
Do not call a score a probability without event definition and calibration evidence.
Do not use one universal sell-point hit rate for all Exit intents.
Do not treat Candidate strategy P&L as pure Candidate-model proof.
Do not treat integrated strategy profit as proof that every component adds value.
Do not promote a factor on standalone IC alone when incremental value is unknown.
Do not ignore the number of experiments, thresholds or variants tried.
Do not let rehearsal or fixture success become Alpha evidence.
Do not let current hard-coded empirical priors become timeless constants.
Do not let sealed-test access become an ordinary development operation.
Do not overwrite formal evidence artifacts.
Do not promote an object with unresolved critical data or implementation incidents.
Do not grant permanent authority; monitor for degradation.
```

Exploratory research may continue rapidly.

The authority of conclusions must remain bounded by the evidence process actually used.

---

# 44. Relationship to the Remaining Constitution

## `08-Roadmap.md`

Will sequence implementation and migration priorities such as:

- global Experiment Identity;
- Validation Protocol registry;
- canonical sample-role vocabulary;
- split manifests;
- walk-forward runner;
- sealed-test controller;
- immutable evidence registry;
- metric contracts;
- Candidate Discovery baseline validation;
- Factor Registry validation integration;
- Lifecycle counterfactual framework;
- Exit intent-specific evaluation;
- Legacy backtest decomposition;
- promotion and degradation governance.

The Roadmap may prioritize delivery.

It may not weaken validation authority to accelerate implementation.

---

## `09-Glossary.md`

Will freeze terms such as:

- Validation;
- Evidence;
- Authority;
- Sample Role;
- Development;
- Train;
- Validation Set;
- Calibration Set;
- OOS Test;
- Sealed Test;
- Walk-Forward;
- Purging;
- Embargo;
- Experiment Identity;
- Baseline;
- Ablation;
- Counterfactual;
- Incremental Value;
- Calibration;
- Promotion;
- Degradation;
- Quarantine;
- Retirement.

---

# 45. Constitutional Validation Commitments

The project commits to the following validation model.

1. **Validation is a contract between a scoped research claim and identified evidence.**
2. **A strong backtest is not, by itself, formal evidence of Alpha.**
3. **Data eligibility and sample role are independent dimensions.**
4. **Development, Train, Validation, Calibration, OOS Test and Sealed Test must not be silently conflated.**
5. **Repeated inspection consumes sample independence.**
6. **Random row splitting is not the default for dependent market panel data.**
7. **Chronology, same-date dependence and overlapping labels must be considered.**
8. **Purging and embargo are applied when justified by target overlap or information carryover, not as empty rituals.**
9. **Walk-forward evidence must preserve fold-level behavior, not only aggregate averages.**
10. **Every formal result requires stable experiment identity and reproducible artifacts.**
11. **Baselines must represent meaningful practical alternatives.**
12. **Metrics must match the decision object.**
13. **Candidate, Factor, Entry, Lifecycle, Exit, Regime and Rotation objects require different validation protocols.**
14. **Candidate ranking quality and strategy P&L are different evidence layers.**
15. **Entry gates must preserve accepted and rejected opportunity evidence where practical.**
16. **HOLD, ADD, REDUCE, ROTATE and EXIT require path-appropriate counterfactuals.**
17. **Exit intents must not be collapsed into one universal sell-point hit rate.**
18. **Probability authority requires explicit event semantics and calibration evidence.**
19. **Row count must not be confused with independent sample size.**
20. **Statistical significance does not replace economic significance.**
21. **Researcher degrees of freedom and multiple testing are part of evidence context.**
22. **Ablation and attribution are required for incremental component claims.**
23. **Counterfactuals must respect actual decision and execution chronology.**
24. **Economic validation must include realistic costs and A-share constraints where relevant.**
25. **Robustness must examine time, population, parameter and failure-mode sensitivity as appropriate.**
26. **Sealed tests are scarce final evidence resources, not tuning loops.**
27. **Material post-test changes create new research candidates.**
28. **Promotion is scope-specific and revocable.**
29. **Promoted objects require monitoring for degradation.**
30. **Quarantine protects evidence integrity when data, implementation or semantics become uncertain.**
31. **Negative results are preserved as project knowledge.**
32. **Learned priors, thresholds and calibration maps are versioned artifacts, not timeless constants.**
33. **Current MACD identity, ablation, sealed-test and immutable-artifact mechanisms are valuable patterns to generalize.**
34. **Legacy terminology must not create parallel global ontologies for data eligibility and sample role.**
35. **Agents may execute validation work but may not silently change the claim, sample, metric, baseline or authority.**

---

# 46. Validation System Acceptance Criteria

The project-wide Validation System is directionally correct only when it can answer, for any formal promoted claim:

```text
What exact object was tested?
What exact claim was made?
What target and horizon were used?
What data was eligible?
What sample roles were assigned?
What split policy was used?
What leakage controls applied?
What experiment identity was run?
What baseline was used?
What metrics matched the decision?
What variants were tried?
What did ablation show?
What did OOS show?
What did robustness show?
What did realistic execution change?
Was a sealed test used, and when was it opened?
What exact scope was promoted?
What monitoring can revoke that authority?
```

If these questions cannot be answered, the project has produced a result, not a validated research asset.

---

# 47. Closing Declaration

The first phase of `market-regime-alpha` accumulated useful trading logic and increasingly sophisticated backtests.

The refoundation phase must distinguish:

```text
A result that looks good
```

from:

```text
A claim that survived a controlled evidence process
```

and:

```text
A claim that survived validation
```

from:

```text
A system that deserves continuing authority
```

The target Validation System is one in which:

```text
Every claim has scope.
Every sample has a role.
Every experiment has identity.
Every metric has decision meaning.
Every comparison has a baseline.
Every component claim has attribution.
Every final test has access governance.
Every promotion has conditions.
Every promoted object can degrade.
Every failure remains knowledge.
```

The project will not define rigor by the number of statistical tests it can run.

It will define rigor by whether attractive results remain trustworthy after the project accounts for how they were produced.

The constitutional validation principle is therefore:

> **Do not ask only whether the result is good. Ask whether the evidence process was strong enough for the authority being requested.**
