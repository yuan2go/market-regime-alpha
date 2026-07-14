# The Constitution of Market Regime Alpha

# Volume VII — Strategy Constitution

> **Document:** `docs/constitution/06-Strategy-Constitution.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide strategy identity, decision-policy, Candidate, Entry, Position Lifecycle, Exit, strategy-state, position-proposal, risk, composition and decision-authority rules  
> **Applies to:** Candidate Discovery consumers, entry policies, holding policies, add/reduce/rotate/exit policies, long-term strategies, dividend strategies, T overlays, ETF strategies, theme strategies, market-regime-conditioned strategies, position-state machines, portfolio proposals, research backtests, shadow/paper workflows, agents, Legacy migration and future live decision systems  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, `02-Architecture-Blueprint.md`, `03-Research-Framework.md`, `04-Data-Constitution.md`, and `05-Factor-Constitution.md`

---

## 0. Purpose

`market-regime-alpha` is not being refounded to create one larger trading rule engine.

It is being refounded to create an Alpha Research Operating System in which validated information can be converted into explicit, independently testable decision policies.

The current repository contains valuable strategy knowledge, including:

- dividend and long-term position logic;
- base-position and active/T-position concepts;
- mean-reversion and trend-following intents;
- Candidate setup classifications;
- entry and exit confirmations;
- MACD score and policy gates;
- risk-reduction semantics;
- attack and beta-hold state machines;
- risk-on add logic;
- trailing-profit and distribution logic;
- A-share execution assumptions;
- detailed decision traces.

The problem is not that these ideas exist.

The problem is that several distinct responsibilities are currently coupled inside the same classes, enums, snapshots and backtest loops.

For example, a single Legacy strategy path may perform:

```text
Feature Aggregation
    ↓
Candidate Selection
    ↓
Policy Gate
    ↓
Position Sizing
    ↓
Signal Generation
    ↓
Order Intent Construction
```

while a second timing engine produces another action semantic for the same symbol and decision time.

The target Strategy System must replace this ambiguity with explicit ownership.

The purpose of this Strategy Constitution is therefore to answer one governing question:

> **How may validated information be converted into Candidate, Entry, Hold, Add, Reduce, Rotate and Exit decisions without collapsing prediction, strategy policy, portfolio allocation and execution into another God Object?**

The central rule is:

> **A strategy owns a defined decision policy for a defined scope. It does not automatically own prediction, total portfolio capital, execution, or every stage of the position lifecycle.**

This document defines:

- the canonical decision chain;
- strategy identity and registry requirements;
- Candidate Discovery boundaries;
- Entry policy rules;
- Position Lifecycle rules;
- Exit policy rules;
- strategy-state ownership;
- strategy composition;
- context and regime use;
- risk and invalidation semantics;
- position-proposal versus portfolio-allocation boundaries;
- execution boundaries;
- multi-strategy and multi-sleeve ownership;
- backtest, live-observation and review requirements;
- Legacy strategy migration;
- agent governance for strategy changes.

This document intentionally does **not** define:

- provider qualification or data eligibility;
- feature formulas or factor-promotion thresholds;
- exact statistical acceptance thresholds;
- final portfolio optimization mathematics;
- broker-specific order APIs;
- permanent numeric values for strategy thresholds.

Those responsibilities belong to the Data, Factor, Validation, Portfolio, Execution and lower-level specification layers.

---

# 1. Constitutional Position of Strategy

## 1.1 A strategy is a policy, not the whole system

Within `market-regime-alpha`, a strategy is:

> **A versioned decision policy that consumes explicit information and state, operates within a defined scope, and produces traceable proposals subject to portfolio and execution authority.**

A strategy may consume:

- Candidate predictions;
- market regime;
- ETF or theme context;
- validated factors;
- current position state;
- original entry thesis;
- risk evidence;
- opportunity-cost information;
- strategy-specific state.

A strategy may produce:

- no action;
- entry proposal;
- hold proposal;
- add proposal;
- reduce proposal;
- rotation proposal;
- exit proposal;
- strategy-specific risk or invalidation status.

A strategy does not automatically own:

- the historical data truth;
- feature definitions;
- Candidate ranking;
- final capital allocation;
- cross-strategy conflict resolution;
- broker order construction;
- fill simulation;
- account-level risk.

---

## 1.2 Strategy authority is scope-specific

A strategy's authority is always bounded by a scope such as:

```text
Market
Instrument Type
Universe
Decision Time
Holding Horizon
Target Family
Position State
Strategy Sleeve
Data Eligibility
Research Status
```

A strategy validated for:

```text
Liquid A-shares
at 14:55
for late-session entry
with next-session opportunity targets
```

is not automatically authorized for:

```text
All A-shares
at the open
for multi-month holding
```

Likewise, a strategy validated for ETFs is not automatically valid for individual stocks.

---

## 1.3 The platform is strategy-neutral

The project must support multiple strategy families, including:

- cross-sectional Candidate Discovery;
- overnight or next-session opportunity strategies;
- multi-session trend continuation;
- ETF rotation;
- theme rotation;
- market-regime-conditioned strategies;
- long-term and dividend strategies;
- base-position plus active-overlay strategies;
- mean reversion;
- trend following;
- risk reduction;
- future event or policy strategies.

No current strategy may redefine the entire project by inheritance.

---

# 2. Canonical Decision Chain

The authoritative end-to-end decision chain is:

```text
Qualified Data
    ↓
Registered Features / Factors
    ↓
Market / ETF / Theme Context
    ↓
Candidate Prediction or Opportunity Assessment
    ↓
Strategy Policy
    ↓
Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
    ↓
Authoritative Position / Portfolio State Update
```

These stages must not be collapsed merely for implementation convenience.

---

## 2.1 Prediction is not action

The following are not equivalent:

```text
High Candidate Rank
High Expected Return
High Probability of Threshold Hit
Strong Trend Descriptor
```

and:

```text
BUY
ADD
HOLD
REDUCE
EXIT
```

Prediction describes an expected outcome.

Strategy action describes a decision under:

- current position state;
- risk;
- cost;
- timing;
- context;
- opportunity cost;
- strategy mandate.

A high prediction may legitimately lead to no action.

---

## 2.2 Strategy proposal is not portfolio allocation

A strategy may propose:

```text
ENTER
ADD
REDUCE
ROTATE
EXIT
```

or a desired exposure range.

The Portfolio System remains the unique owner of:

- final account-level position size;
- aggregate exposure;
- cross-strategy capital allocation;
- concentration;
- sector/theme exposure;
- cash allocation;
- portfolio risk budget;
- conflict resolution between simultaneous opportunities.

---

## 2.3 Portfolio decision is not execution

A Portfolio Decision may authorize a target or delta.

The Execution System remains the owner of:

- order construction;
- order type;
- executable quantity;
- A-share market constraints;
- lot rules;
- suspension checks;
- price-limit constraints;
- transaction costs;
- slippage assumptions;
- broker routing;
- fill state.

A Strategy Proposal must never imply that a fill occurred.

---

# 3. Canonical Decision Objects

The project distinguishes the following objects.

## 3.1 Candidate Prediction

A **Candidate Prediction** describes an opportunity estimate for an eligible instrument at a defined decision time.

It may include:

```text
symbol
candidate_model_id
decision_time
target_id
horizon
raw_prediction
rank
percentile
calibrated_probability, if valid
expected_return, if modeled
expected_MFE, if modeled
expected_MAE, if modeled
uncertainty
context references
feature / model artifact references
expiry
trace
```

It does not own capital allocation or execution.

---

## 3.2 Entry Proposal

An **Entry Proposal** is a strategy-level recommendation to establish a new exposure.

It should distinguish:

```text
Why this opportunity is eligible
Why entry should occur now
What evidence supports entry
What price/time convention is assumed
What invalidates the entry thesis
What risk is accepted
When the proposal expires
```

Entry is a policy decision, not a synonym for Candidate ranking.

---

## 3.3 Position Lifecycle Proposal

A **Position Lifecycle Proposal** is a recommendation about an existing strategy exposure.

Canonical lifecycle actions are:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

These actions are not a mandatory linear sequence.

---

## 3.4 Strategy Proposal

A **Strategy Proposal** is the canonical output of an authoritative strategy policy.

A logical contract should be able to represent, as applicable:

```text
strategy_id
strategy_version
decision_scope
symbol or instrument
decision_time
current_position_state_ref
strategy_action
strategy_intent
setup / trigger reference
candidate_prediction_ref
context_refs
reason_codes
risk_state
invalidation_state
proposal_expiry
proposed_target_exposure or delta range
urgency
trace
model / rule artifact refs
```

The exact schema belongs to a lower-level specification.

---

## 3.5 Portfolio Decision

A **Portfolio Decision** resolves one or more Strategy Proposals into account-level capital decisions.

It owns final allocation authority.

---

## 3.6 Execution Request and Execution Result

An **Execution Request** translates an approved Portfolio Decision into an executable instruction.

An **Execution Result** records what actually happened.

Strategy code must not silently treat an intended order as a completed transaction.

---

# 4. Canonical Strategy Actions

The platform-level action vocabulary is:

```text
NO_ACTION
ENTER
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Strategy-specific actions may exist below this level.

They must map explicitly to canonical actions when crossing platform boundaries.

---

## 4.1 `NO_ACTION` and `HOLD` are different

`NO_ACTION` means:

```text
No authoritative position action is proposed.
```

`HOLD` means:

```text
An existing position has been evaluated and continued exposure is the current strategy proposal.
```

The project must not use `HOLD` as a universal null value for:

- no candidate;
- no position;
- insufficient data;
- blocked execution;
- missing model output;
- unchanged position after evaluation.

These states have different semantics.

---

## 4.2 `ENTER` and `ADD` are different

`ENTER` establishes a new exposure.

`ADD` increases an existing exposure.

The evidence required for ADD may differ because the system must consider:

- current position size;
- current unrealized path;
- original thesis;
- new evidence;
- concentration;
- marginal expected value;
- opportunity cost.

A successful Entry model does not automatically authorize Add decisions.

---

## 4.3 `REDUCE` and `EXIT` are different

`REDUCE` preserves some exposure.

`EXIT` terminates the strategy exposure for the relevant scope.

A system must not treat every sell-like action as one universal event.

---

## 4.4 `ROTATE` is not merely `EXIT + ENTER`

Rotation is a comparative decision.

It should evaluate, as applicable:

```text
Expected remaining value of current position
        versus
Expected value of eligible alternative
        minus
Switching cost
        adjusted for
Risk and concentration
```

A higher-ranked alternative does not automatically force rotation.

---

# 5. Strategy Registry and Strategy Identity

The project shall establish a canonical Strategy Registry.

Every formal strategy must have stable identity.

A recommended logical identity includes, as applicable:

```text
strategy_id
strategy_name
strategy_version
strategy_family
objective
applicable_market
instrument_types
universe_contract
candidate_model_refs
context_model_refs
feature / factor requirements
decision_times
entry_policy_id
position_lifecycle_policy_id
exit_policy_id
risk_policy_id
state_schema_version
position_proposal_semantics
portfolio_interface_version
execution_assumption_ref
target_refs
benchmark_refs
data_eligibility_requirements
research_status
owner
```

A result-affecting semantic change requires a new version or identity.

---

## 5.1 Strategy name is not strategy identity

The following is insufficient:

```text
ETF Rotation Strategy
```

A formal identity must distinguish materially different definitions such as:

```text
ETF Rotation based on 20-day momentum
```

and:

```text
ETF Rotation based on share growth + breadth + leader resonance
```

Likewise:

```text
Overnight Strategy
```

is not a stable identity unless its decision time, target, entry, lifecycle and exit semantics are explicit.

---

## 5.2 Threshold changes may create a new strategy version

A threshold is not “just configuration” when it changes decision behavior.

Material changes to:

- entry threshold;
- exit threshold;
- hold rule;
- add rule;
- risk gate;
- target position logic;
- regime gate;
- time expiry;

must be versioned and evaluated.

---

# 6. Minimum Strategy Definition

Every formal strategy must define the following twelve elements.

## 6.1 Strategy Objective

The strategy must state the decision problem it is trying to improve.

Examples:

```text
Discover and enter short-horizon positive-upside opportunities.
```

```text
Rotate toward ETFs with stronger expected relative performance.
```

```text
Maintain a long-term dividend exposure while using a controlled active overlay.
```

The objective must not be a guaranteed return claim.

---

## 6.2 Applicable Market

The strategy must define its applicable market and instrument type.

Examples may include:

- A-share stocks;
- ETFs;
- a specific board or liquidity segment;
- long-only positions;
- strategy-specific overlays.

---

## 6.3 Stock Pool / ETF Pool

The strategy must reference a reproducible universe contract.

The strategy may define additional eligibility rules.

It must not reconstruct historical eligibility from current truth.

---

## 6.4 Signal Sources

The strategy must identify which information objects it consumes.

Examples:

- Candidate Prediction;
- Market Regime;
- ETF / Theme Context;
- registered factors;
- position state;
- risk evidence;
- lifecycle evidence.

Signal sources must be identifiable and versioned.

---

## 6.5 Entry Conditions

Entry conditions must define:

- decision time;
- required Candidate or opportunity state;
- required context;
- required confirmations or gates;
- invalidating conditions;
- proposal expiry;
- assumed next eligible execution convention.

---

## 6.6 Exit Conditions

Exit conditions must distinguish intent where relevant:

- profit taking;
- risk stop;
- thesis invalidation;
- trend invalidation;
- structure break;
- distribution or exhaustion;
- time expiry;
- rotation;
- forced exit.

---

## 6.7 Position Management

The strategy must define how an existing exposure is evaluated for:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Position management must not be left as an implicit consequence of Entry.

---

## 6.8 Risk Rules

The strategy must define:

- thesis risk;
- hard invalidation where applicable;
- soft risk reduction;
- unsupported-data behavior;
- state corruption behavior;
- strategy-specific exposure constraints.

Account-level risk remains the Portfolio System's responsibility.

---

## 6.9 Backtest Requirements

The strategy must state what must be simulated or validated, including as applicable:

- decision timing;
- next eligible execution;
- A-share constraints;
- transaction cost;
- state transitions;
- position lifecycle;
- benchmark;
- baseline;
- required ablations;
- target and metric alignment.

The exact proof thresholds belong to `07-Validation-Constitution.md`.

---

## 6.10 Live / Shadow Observation

The strategy must define what should be monitored outside historical backtests.

Examples:

- Candidate coverage;
- proposal frequency;
- action distribution;
- rejected opportunities;
- data failures;
- execution feasibility;
- calibration drift;
- lifecycle transition frequency;
- regime exposure;
- missed opportunity;
- unexpected behavior.

Observation is not automatic production authority.

---

## 6.11 Invalidation Conditions

The strategy must identify what would invalidate:

- an individual position thesis;
- a strategy assumption;
- a research conclusion;
- an operational deployment.

These are distinct levels.

---

## 6.12 Review Method

The strategy must define how it will be reviewed.

A review should be able to reconstruct:

```text
What the strategy knew
What it predicted
What action it proposed
What Portfolio decided
What Execution achieved
What happened afterward
What assumption succeeded or failed
```

---

# 7. Candidate Discovery Constitution

Candidate Discovery is the current first strategic research priority.

It is an upstream opportunity-discovery system.

---

## 7.1 Candidate Discovery is cross-sectional prediction

At a defined decision time, Candidate Discovery asks:

> **Among instruments that were actually eligible, which ones have the strongest target-specific opportunity profile?**

It may output:

- scores;
- expected returns;
- expected MFE / MAE;
- calibrated probabilities;
- ranks;
- top-K sets;
- uncertainty;
- rejection reasons.

It does not directly own:

- Entry;
- capital allocation;
- portfolio concentration;
- execution.

---

## 7.2 Candidate ranking is not an entry command

A top-ranked candidate may still be rejected by Entry because of:

- poor execution conditions;
- unfavorable current price location;
- thesis conflict;
- excessive risk;
- stale context;
- insufficient confirmation;
- portfolio concentration;
- duplicate exposure;
- low marginal value versus current holdings.

---

## 7.3 Candidate validity has an expiry

A Candidate Prediction is tied to:

- decision time;
- target horizon;
- market state;
- data state.

It must not remain actionable indefinitely merely because it was once highly ranked.

---

## 7.4 Candidate Discovery must not be implemented as mass repetition of a symbol-specific timing score without proof

A within-symbol timing score is not automatically cross-sectionally comparable.

A Candidate model requires:

- PIT universe;
- comparable features;
- target-specific ranking evidence;
- cross-sectional normalization where appropriate;
- population-aware validation.

---

# 8. Entry Constitution

Entry is an independent strategy policy.

---

## 8.1 Entry answers a different question from Candidate Discovery

Candidate Discovery asks:

```text
Which opportunities are attractive?
```

Entry asks:

```text
Should a new position be established now, under this strategy and current context?
```

These are not the same question.

---

## 8.2 Entry must define decision-time semantics

An Entry policy must define, as applicable:

```text
Candidate Decision Time
Entry Evaluation Time
Current-Bar Finalization Requirement
Next Eligible Execution Time
Proposal Expiry
Reference Price Convention
```

A late-session strategy may evaluate at 14:30, 14:45, 14:55 or another time.

No one decision time is a universal project rule.

---

## 8.3 Confirmation is a strategy hypothesis

A Candidate may be filtered or upgraded by confirmation such as:

- support hold;
- VWAP reclaim;
- intraday reversal;
- trend continuation;
- structure confirmation;
- observed flow confirmation.

A confirmation is not automatically valuable.

Its incremental effect must be researchable.

---

## 8.4 Entry gates must remain attributable

The project rejects:

```text
Candidate
  + Trend Gate
  + MACD Gate
  + ETF Gate
  + Theme Gate
  + Flow Gate
  + Chan Gate
  + Tuishen Gate
  + Risk Gate
  = Entry
```

without controlled attribution.

A gate is a behavioral intervention.

Its blocked opportunities, missed profits, avoided losses and coverage impact should be measurable where practical.

---

# 9. Position Lifecycle Constitution

Position management is a repeated decision problem.

The canonical lifecycle actions are:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

The Strategy System must evaluate these actions using explicit state and evidence.

---

## 9.1 HOLD is an active lifecycle decision

The system must not assume:

```text
No exit signal
therefore
HOLD is correct
```

A HOLD proposal should mean that the position was evaluated and continued exposure remains justified under the strategy.

---

## 9.2 ADD is not a repeated Entry

An Add policy should consider, as applicable:

- current exposure;
- current profit/loss path;
- original thesis;
- new evidence;
- marginal expected value;
- risk concentration;
- recent failed adds;
- follow-through quality;
- alternative opportunities.

A strategy must not repeatedly re-trigger the original Entry rule until the position reaches a maximum cap without a separate Add hypothesis.

---

## 9.3 REDUCE is partial risk or opportunity management

Reduce may be motivated by:

- deteriorating expected value;
- rising risk;
- concentration;
- partial profit protection;
- weakening structure;
- distribution;
- need to fund a superior opportunity.

The intent must be explicit.

---

## 9.4 ROTATE is first-class

Rotation is especially important for:

- ETF rotation;
- theme rotation;
- cross-sectional Candidate Discovery;
- opportunity-cost-aware portfolios.

Rotation research must distinguish:

```text
Current position still positive
```

from:

```text
Current position remains the best use of scarce risk capital
```

---

## 9.5 Lifecycle state must be explicit

A lifecycle policy may require state such as:

- entry thesis;
- entry time;
- entry reference price;
- current exposure;
- holding age;
- peak favorable excursion;
- adverse excursion;
- prior add/reduce events;
- recent failed transitions;
- current risk status;
- strategy-specific mode.

State must be owned, versioned and traceable.

Hidden mutable state inside a backtest loop is not sufficient for future platform authority.

---

# 10. Exit Constitution

Exit is independent from Entry.

The project explicitly rejects:

```text
Entry condition becomes false
therefore
Exit
```

as a universal design.

---

## 10.1 Exit intents are distinct

Exit-like behavior may represent:

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

These intents may require different targets and metrics.

---

## 10.2 Time-based exit is a valid policy, not a universal law

For a specific overnight strategy, fixed exits such as:

```text
09:35
10:00
10:30
```

may be valid deterministic baselines.

The project does not define all positions as fixed next-morning exits.

A position may continue when the lifecycle policy still supports holding.

---

## 10.3 Exit models are not inverse Entry models

An Entry model may estimate:

```text
P(positive next-session opportunity)
```

An Exit model may estimate:

```text
Expected remaining return
```

or:

```text
P(thesis invalidation within N bars)
```

or:

```text
Expected opportunity improvement from rotation
```

These targets are not logical negations of one another.

---

## 10.4 Hard and soft exits are different

A hard invalidation may require a stronger downstream response than a soft deterioration signal.

The policy must distinguish:

- evidence strength;
- intent;
- remaining exposure;
- override level.

---

# 11. Strategy Context Constitution

Market Regime, ETF Rotation and Theme Rotation may influence strategies in several roles.

Possible roles include:

```text
CONTEXT
FEATURE
INTERACTION_TERM
UNIVERSE_FILTER
STRATEGY_GATE
RISK_INPUT
DIRECT_STRATEGY
PORTFOLIO_INPUT
```

The role must be explicit.

---

## 11.1 Context does not silently become authority

For example:

```text
ETF relative strength improves Candidate quality
```

is different from:

```text
Reject all stock entries whenever ETF relative strength is below X
```

The latter is a separate strategy hypothesis.

---

## 11.2 ETF and Theme Rotation may be both upstream and direct strategies

The platform supports both:

```text
ETF / Theme Context
    ↓
Candidate Universe Narrowing
    ↓
Stock Candidate Discovery
```

and:

```text
ETF Candidate Discovery
    ↓
ETF Entry / Lifecycle / Exit
```

These roles must not be collapsed into one ambiguous model.

---

# 12. Strategy Composition Constitution

Complex strategies may be composed from independently testable components.

A canonical composition may be:

```text
Candidate Model
    +
Entry Policy
    +
Position Lifecycle Policy
    +
Exit Policy
    +
Strategy Risk Policy
```

The resulting strategy remains a versioned composition.

---

## 12.1 One authoritative policy per decision scope

Multiple models may coexist as:

- research models;
- shadow models;
- diagnostics;
- ensemble inputs;
- veto inputs;
- alternative baselines.

But for a given authoritative decision scope there must be one explicit final Strategy Proposal path.

The system must not expose two independent final action fields and expect the UI or human to reconcile semantics silently.

---

## 12.2 Ensemble does not mean undefined authority

If several models are combined, the ensemble rule itself becomes a versioned strategy component.

It must define:

- members;
- weights or voting rule;
- conflict rule;
- missing-member behavior;
- output semantics.

---

## 12.3 Circular decision dependencies are prohibited

The project must avoid structures such as:

```text
Entry score depends on position target
Position target depends on final signal
Final signal depends on entry score
```

without an explicit deterministic resolution model.

---

# 13. Risk and Invalidation Constitution

Risk exists at several layers.

The project must preserve layer ownership.

```text
Data Risk
    ↓
Strategy / Thesis Risk
    ↓
Portfolio Risk
    ↓
Execution / Market Feasibility Risk
```

Each layer may block or downgrade downstream action.

It must not silently rewrite upstream truth.

---

## 13.1 Strategy risk owns thesis and strategy-specific invalidation

Examples:

- setup failure;
- structural break;
- trend invalidation;
- loss of required context;
- model unavailable;
- unsupported data state;
- strategy-specific stop condition.

---

## 13.2 Portfolio risk owns aggregate exposure

Examples:

- total leverage;
- sector concentration;
- theme concentration;
- correlated exposure;
- portfolio drawdown policy;
- cash reserve;
- account-level risk budget.

A strategy may declare exposure preferences or caps for its own scope.

It does not own final aggregate risk.

---

## 13.3 Execution owns feasibility

Execution may block or modify an authorized action because the market action is not executable under the applicable rules.

It must report the reason rather than changing the strategy's historical proposal.

---

## 13.4 `RiskEnforcement` is a useful Legacy pattern, not the final universal ontology

The current distinction between:

```text
NONE
SOFT
HARD
```

is valuable because it makes risk intent explicit.

Future V2 contracts may generalize this pattern.

The project should preserve the principle:

> **Risk severity and override authority must be explicit and traceable.**

---

# 14. Position Sizing and Portfolio Boundary

The Strategy System may propose exposure.

The Portfolio System allocates capital.

---

## 14.1 Strategy may express desired exposure semantics

A strategy may output, as appropriate:

- target exposure;
- target exposure range;
- maximum strategy-local exposure;
- desired delta;
- priority;
- expected utility;
- risk-adjusted attractiveness.

These are proposals.

---

## 14.2 Final position percentage belongs to Portfolio

The following pattern is prohibited in the target architecture:

```text
Strategy calculates suggested_trade_pct
    ↓
Strategy constructs order intent
    ↓
Execution assumes this is final portfolio authority
```

The correct target flow is:

```text
Strategy Proposal
    ↓
Portfolio Reconciliation
    ↓
Portfolio Decision
    ↓
Execution Request
```

---

## 14.3 Base and active/T position concepts may remain strategy-specific sleeves

The existing concepts of:

```text
Base Position
Active / T Position
```

may remain useful for specific dividend or overlay strategies.

They are not universal account-state semantics.

If preserved, they must be represented as explicit strategy sleeves or virtual allocations that reconcile to the authoritative physical portfolio.

---

# 15. Multi-Strategy and Multi-Sleeve Ownership

The same security may be relevant to multiple strategies.

Examples:

```text
Long-term dividend strategy
+
Short-horizon active overlay
+
Cross-sectional trend strategy
```

The project must prevent multiple strategies from each pretending to own the same physical shares independently.

---

## 15.1 Strategy state and physical position are different

A strategy may own:

```text
Virtual Strategy Exposure
Strategy Thesis
Strategy Cost Basis for Attribution
Strategy Lifecycle State
```

The Portfolio System owns:

```text
Physical Account Position
Final Net Exposure
Cross-Strategy Reconciliation
```

---

## 15.2 Cross-strategy conflicts are portfolio problems

For example:

```text
Strategy A: ADD
Strategy B: EXIT
```

must not be resolved by whichever strategy runs last.

The Portfolio System must apply an explicit conflict and allocation policy.

---

## 15.3 Strategy attribution requires sleeve identity

When multiple strategies influence the same instrument, research should preserve enough identity to determine:

- which strategy proposed what;
- which proposal Portfolio accepted;
- which exposure was attributable to which strategy;
- how realized outcomes are assigned for research.

---

# 16. Strategy State Constitution

Stateful strategies are permitted.

Hidden state is not.

---

## 16.1 State has one owner

Each state field must have an authoritative owner.

Examples:

```text
Position Lifecycle State → Position Lifecycle System
Portfolio Exposure → Portfolio System
Execution Fill State → Execution System
Market Regime State → Market Context System
```

A backtest should not maintain competing copies of the same authoritative state without reconciliation.

---

## 16.2 State transitions are decision events

A transition should be reconstructable as:

```text
Previous State
    +
New Evidence
    +
Policy Version
    ↓
Proposed Transition
    ↓
Portfolio / Execution Consequence
    ↓
New Authoritative State
```

---

## 16.3 Backtest-only hidden state cannot become production truth by accident

State machines developed inside `backtest.py` may contain valuable research knowledge.

Before platform promotion they must be:

- identified;
- named;
- assigned an owner;
- given explicit transition contracts;
- characterized with tests;
- separated from simulation-only bookkeeping.

---

# 17. Strategy Confidence, Score and Probability

Strategy outputs may include several numerical concepts.

They must remain semantically distinct.

```text
Factor Score
Model Score
Candidate Rank
Expected Return
Calibrated Probability
Strategy Utility
Policy Confidence
Risk Severity
```

A value in `[0, 100]` is not automatically a probability.

A strategy must not convert:

```text
Composite Score = 78
```

into:

```text
78% chance of profit
```

without a defined event and calibration evidence.

---

# 18. Strategy Research and Backtest Constitution

Every strategy must pass through the Research Framework.

A typical research structure is:

```text
Strategy Objective
    ↓
Decision Problem
    ↓
Component Hypotheses
    ↓
Candidate / Entry / Lifecycle / Exit Targets
    ↓
Baseline Strategy
    ↓
Component Experiments
    ↓
Integrated Strategy Experiment
    ↓
Walk-Forward / OOS
    ↓
Economic / Execution Review
    ↓
Promotion Decision
```

---

## 18.1 Component quality and integrated quality are both required

A strategy may contain:

- strong Candidate model;
- weak Entry policy;
- strong Hold policy;
- harmful Exit policy.

A profitable integrated result does not prove that every component is valuable.

---

## 18.2 Strategy backtests must preserve decision chronology

The backtest must preserve:

```text
Information available at decision time
    ↓
Strategy Proposal
    ↓
Next eligible Portfolio / Execution action
    ↓
State transition
```

A strategy must not use the fill outcome to rewrite the historical proposal that preceded it.

---

## 18.3 A-share execution realism remains mandatory

Where relevant, the research environment must account for versioned A-share execution constraints.

The exact rules belong to the Execution System and Validation Constitution.

Strategy logic must not assume guaranteed fills.

---

# 19. Live, Shadow and Paper Observation

A strategy may move through research states before any live capital authority.

Possible observation stages include:

```text
Historical Research
Shadow Evaluation
Paper Decisioning
Manual Observation
Future Controlled Live Use
```

The exact promotion gates belong to `07-Validation-Constitution.md`.

---

## 19.1 Shadow output must preserve authority boundaries

A shadow model may produce a competing proposal.

It must not silently influence the authoritative strategy unless promoted.

---

## 19.2 Live observation should include rejected actions

Research should not monitor only executed winners.

Where practical it should preserve:

- proposed but rejected entries;
- blocked adds;
- held positions;
- reductions;
- rotations not taken;
- execution failures;
- data failures;
- risk overrides.

This is necessary to study opportunity cost and policy quality.

---

# 20. Invalidation Constitution

The project distinguishes several invalidation levels.

## 20.1 Position Thesis Invalidation

The reason for holding a specific position is no longer supported.

This may trigger Reduce or Exit.

---

## 20.2 Strategy-State Invalidation

A strategy mode or state transition becomes invalid.

Example:

```text
Trend-following state
    ↓
confirmed structural breakdown
```

---

## 20.3 Research-Hypothesis Invalidation

New evidence no longer supports the strategy's claimed relationship.

This may trigger degradation, quarantine or retirement.

---

## 20.4 Operational Invalidation

The strategy cannot operate reliably because of:

- data failure;
- model artifact failure;
- provider change;
- state corruption;
- execution incompatibility;
- implementation regression.

Operational invalidation may reduce authority even if the economic hypothesis remains plausible.

---

# 21. Review and Post-Decision Learning

A mature strategy should support review at several levels.

## 21.1 Decision Review

For each meaningful decision:

```text
What information was available?
What prediction existed?
What state existed?
What policy fired?
What proposal was produced?
What risk or invalidation applied?
```

---

## 21.2 Portfolio Review

```text
Was the proposal accepted?
Was it resized?
Was it blocked by portfolio constraints?
Was another strategy prioritized?
```

---

## 21.3 Execution Review

```text
Was the decision executable?
What fill occurred?
What cost occurred?
What constraint prevented execution?
```

---

## 21.4 Outcome Review

```text
What happened afterward?
Was the target realized?
Was the lifecycle action beneficial?
What was the opportunity cost?
Which assumption failed?
```

---

## 21.5 Strategy Review must distinguish fact from interpretation

Reports should distinguish:

```text
Fact
Inference
Model Assumption
Strategy Proposal
Risk
Invalidation Condition
Observation Metric
```

---

# 22. Strategy-Specific Use of Technical and Theory-Derived Information

MACD, moving averages, volume-price structures, Chan-derived features and Tuishen-inspired features are information inputs.

They do not own strategy decisions by themselves.

---

## 22.1 MACD

MACD may be used as:

- predictor;
- confirmation;
- gate input;
- sizing input;
- exit evidence.

Each role is a separate strategy intervention.

---

## 22.2 Chan-derived structures

A Chan buy point may be:

- descriptor;
- Candidate feature;
- Entry confirmation;
- strategy gate.

A Chan sell point may be:

- risk evidence;
- Reduce trigger;
- Exit trigger.

These are different roles.

---

## 22.3 Tuishen-inspired constructs

Attention, force, memory, sell pressure, leader ignition and exhaustion may inform strategy policies.

They must remain measurable proxies or models with explicit lineage.

The Strategy System must not grant them authority merely because the underlying theory is persuasive.

---

# 23. Current Legacy Strategy Audit

This Constitution is informed by the current repository.

The following interpretations are binding until superseded by more specific designs or specifications.

---

## 23.1 `signal_intent.py`

**Current value:** introduces explicit `SignalIntent`, `PrimarySetupCode`, entry/exit confirmations, risk severity, Candidate validation and DecisionTrace.  
**Risk:** Legacy Candidate contracts still combine setup discovery with action-oriented `Signal` values such as `BUY_T`, `SELL_T`, `CLEAR` and `REDUCE`.  
**Constitutional interpretation:** strong semantic and traceability asset, but not yet the universal V2 Candidate contract.  
**Required evolution:** preserve intent, setup identity, confirmation and trace concepts while separating Candidate Prediction from Strategy Action.  
**Action:** **Preserve design principles + Adapt contracts.**

---

## 23.2 `models.py::Signal`

Current values include:

```text
BUILD_BASE
HOLD
BUY_T
SELL_T
SELL_REVERSE_T
BUY_BACK_REVERSE_T
STOP_T
REDUCE
CLEAR
```

**Current value:** useful vocabulary for the Legacy dividend-T strategy.  
**Risk:** strategy-specific actions may be mistaken for platform-wide universal semantics.  
**Constitutional interpretation:** Legacy strategy action enum.  
**Required evolution:** map strategy-specific actions to canonical platform actions plus explicit strategy intent / sleeve semantics.  
**Action:** **Preserve for Legacy replay + Do not universalize.**

---

## 23.3 `DividendTStrategy`

**Current value:** deterministic integrated baseline with explicit scoring, Candidate selection, MACD policy, sizing and trace.  
**Risk:** one class currently performs Candidate selection, policy gating, strategy sizing and order-intent construction.  
**Constitutional interpretation:** valuable Legacy integrated strategy baseline, not the target Strategy architecture.  
**Required evolution:** extract Candidate, strategy policy, exposure proposal and execution translation into explicit owners.  
**Action:** **Freeze platform expansion + Characterize + Extract incrementally.**

---

## 23.4 `StrategyDecision`

Current fields include:

```text
signal
score
base_position_limit_pct
suggested_trade_pct
order_intent
DecisionTrace
```

**Current value:** useful end-to-end Legacy decision record.  
**Risk:** combines strategy decision, sizing proposal and order intent.  
**Constitutional interpretation:** migration source, not the final platform contract.  
**Required evolution:** split into Strategy Proposal, Portfolio Decision and Execution Request/Result contracts.  
**Action:** **Adapt through compatibility boundary.**

---

## 23.5 `PositionState` and `PositionBudget`

**Current value:** explicit base/T position and account-percentage concepts.  
**Risk:** strategy-local sleeve semantics may be confused with authoritative portfolio state.  
**Constitutional interpretation:** useful strategy-specific exposure model for dividend/T research.  
**Required evolution:** represent strategy sleeve state separately from physical account portfolio state.  
**Action:** **Preserve where useful + Re-scope ownership.**

---

## 23.6 `CoscoTimingEngine`

**Current value:** integrated research engine containing many Candidate, timing, risk and lifecycle hypotheses.  
**Risk:** feature extraction, context, Candidate logic, Entry, Exit and policy behavior are tightly coupled.  
**Constitutional interpretation:** Legacy integrated research engine, not the V2 Strategy System.  
**Required evolution:** extract only evidence-backed strategy components through explicit contracts.  
**Action:** **Freeze expansion + Selective extraction.**

---

## 23.7 `trend_snapshot.py`

**Current value:** useful public research snapshot and operational integration point.  
**Risk:** currently runs both `DividendTStrategy` and `CoscoTimingEngine`, exposing `signal` and `timing_action` as separate action semantics in one row.  
**Constitutional interpretation:** current application flow with two decision authorities.  
**Required evolution:** consume one authoritative strategy decision path per decision scope; alternative models may remain shadow or diagnostic outputs.  
**Action:** **Unify authority at the application layer.**

---

## 23.8 `backtest.py`

**Current value:** contains extensive knowledge about A-share simulation, attack state, beta-hold state, risk-on adds, position targets, follow-through, trailing profit, distribution and execution constraints.  
**Risk:** lifecycle policy, portfolio state, execution, research configuration and reporting are highly coupled; large threshold surfaces encourage rule accumulation.  
**Constitutional interpretation:** Legacy behavior-preservation laboratory containing multiple future bounded contexts.  
**Required evolution:** extract lifecycle policies, strategy-state contracts, portfolio rules and execution simulation by explicit owner.  
**Action:** **Characterize + Extract incrementally; do not add new platform responsibilities.**

---

# 24. V2 Strategy System Direction

The future V2 flow is:

```text
Market / ETF / Theme Context
        +
Candidate Predictions
        +
Registered Features / Model Outputs
        +
Current Strategy State
        ↓
Entry Policy
Position Lifecycle Policy
Exit Policy
Strategy Risk Policy
        ↓
One Authoritative Strategy Proposal
        ↓
Portfolio System
        ↓
Execution System
```

The Strategy System owns:

- strategy registry;
- strategy identity;
- decision policy;
- strategy-local state;
- action semantics;
- proposal trace;
- strategy-level risk and invalidation.

It does not own:

- data truth;
- factor definitions;
- final portfolio allocation;
- physical account position truth;
- broker execution.

---

# 25. Minimum Formal Strategy Package

Before a strategy can become a formal strategy candidate rather than an informal rule collection, it should have, at minimum:

```text
1. Strategy Identity and Version
2. Strategy Objective
3. Applicable Market and Instrument Type
4. PIT Universe / Stock Pool / ETF Pool Reference
5. Signal / Candidate / Context Sources
6. Entry Conditions and Decision-Time Semantics
7. Exit Conditions by Intent
8. Position Lifecycle Rules: Hold / Add / Reduce / Rotate / Exit
9. Position Proposal Semantics and Portfolio Boundary
10. Strategy Risk Rules
11. Invalidation Conditions
12. State Contract
13. Baseline Strategy
14. Backtest Requirements
15. Execution Assumption Reference
16. Live / Shadow Observation Plan
17. Review Method
18. Required Ablations / Attribution
19. Known Failure Modes
20. Research Status and Owner
```

The exact proof standard belongs to `07-Validation-Constitution.md`.

---

# 26. Strategy Anti-Patterns

The following patterns are constitutionally prohibited or must remain explicitly Legacy / exploratory.

## 26.1 Candidate-to-order shortcut

```text
High Candidate Score
    ↓
Immediate Order
```

without Entry, Portfolio and Execution boundaries.

---

## 26.2 One universal `signal`

Using one field to mean:

- prediction;
- candidate;
- entry;
- reduce;
- exit;
- risk;
- execution.

---

## 26.3 Multiple final decision authorities

Exposing two independent final action fields and expecting downstream consumers to decide which one is “real.”

---

## 26.4 `HOLD` as null

Using HOLD for:

- no candidate;
- no data;
- no position;
- blocked execution;
- unchanged evaluated position.

---

## 26.5 Fixed next-morning exit as project law

A fixed exit may be a strategy baseline.

It is not the universal lifecycle model.

---

## 26.6 Entry rule reused as Add rule

Repeatedly buying because the original Entry condition remains true, without marginal-position logic.

---

## 26.7 Exit as inverse Entry

Treating a weakening Entry score as sufficient universal Exit logic.

---

## 26.8 Sell-action collapse

Treating:

```text
Profit Taking
Risk Stop
Reduce
Rotation
Full Exit
```

as one identical event.

---

## 26.9 Strategy-owned final portfolio allocation

A strategy directly determines account-level capital without Portfolio reconciliation.

---

## 26.10 Strategy-owned broker execution

Strategy code creates or assumes completed broker orders without Execution authority.

---

## 26.11 Hidden state machine in backtest

Lifecycle state exists only through scattered mutable variables inside a simulation loop.

---

## 26.12 Rule accumulation without component attribution

```text
Performance weakens
    ↓
Add another gate
    ↓
Add another state
    ↓
Add another threshold
```

without controlled experiments.

---

## 26.13 Context role drift

An ETF or Market Regime feature silently changes from context to hard gate without a new strategy hypothesis.

---

## 26.14 Cross-strategy last-writer-wins

Two strategies propose conflicting actions and whichever runs last overwrites the other.

---

## 26.15 Physical-position double ownership

Multiple strategies each assume they exclusively own the same account shares.

---

## 26.16 Probability theater in strategy confidence

A strategy score is presented as a probability of profit without a calibrated event.

---

## 26.17 Per-symbol timing score used as market-wide Candidate rank without evidence

Within-symbol comparability does not imply cross-sectional comparability.

---

## 26.18 Agent-induced strategy drift

An agent silently changes:

- target;
- entry time;
- exit time;
- action semantics;
- risk level;
- threshold;
- strategy role;
- portfolio authority;
- execution authority;

because another path is easier to implement.

---

# 27. Strategy Review Questions

Every serious strategy addition or change should be reviewable through the following questions.

## Identity

- What exact strategy and version is this?
- What scope does it claim authority over?

## Objective

- What decision problem is it trying to improve?
- What is explicitly outside its objective?

## Market / Universe

- Which market and instrument types apply?
- Which PIT universe does it use?

## Information

- Which Candidate, factors, model outputs and context variables does it consume?
- Are their identities and roles explicit?

## Candidate

- Is the strategy consuming a ranking, prediction, probability or descriptor?
- Is Candidate output being confused with action?

## Entry

- Why should a new position be established now?
- What is the decision time and next eligible execution convention?

## Lifecycle

- How are HOLD, ADD, REDUCE and ROTATE evaluated?
- Is ADD distinct from repeated Entry?

## Exit

- What exit intent is being evaluated?
- Is Exit independent from Entry?

## State

- What state is required?
- Who owns it?
- Can every transition be reconstructed?

## Position / Portfolio

- What exposure does the strategy propose?
- What remains the Portfolio System's authority?

## Risk

- What invalidates the position thesis?
- What invalidates the strategy?
- What is soft versus hard risk?

## Execution

- Is the strategy assuming a fill?
- Are execution constraints modeled downstream?

## Research

- What is the baseline?
- Which components are independently attributable?
- What must be backtested?

## Observation

- What should be monitored in shadow or manual use?
- What would trigger degradation or quarantine?

## Review

- Can the full chain from prediction to realized outcome be reconstructed?

---

# 28. Current Refoundation Strategy Constraints

Until explicitly changed by new evidence and a traceable decision, the following posture remains binding:

```text
Do not redefine the project as one overnight strategy.
Do not define fixed next-morning exit as the universal lifecycle rule.
Do not let Candidate Discovery directly own orders.
Do not treat Candidate rank as automatic Entry.
Do not use one overloaded signal field for prediction, action and risk.
Do not expose two independent authoritative action paths for the same scope.
Do not expand CoscoTimingEngine into the V2 Strategy platform.
Do not add new platform lifecycle state to the backtest God Object.
Do not let Strategy own final account allocation.
Do not let Strategy own broker execution.
Do not treat suggested_trade_pct as final portfolio authority.
Do not treat BUY_T / SELL_T / STOP_T as universal platform actions.
Do not collapse Reduce, Rotation and Exit into one sell metric.
Do not use Entry logic as the default Add policy.
Do not infer Exit by simply negating Entry.
Do not use sealed-test outcomes to tune strategy thresholds or action policies.
Do not claim guaranteed returns or deterministic future direction.
```

Exploratory strategy research may continue.

Authority must remain bounded by evidence and architecture.

---

# 29. Relationship to the Remaining Constitution

## `07-Validation-Constitution.md`

Will define the proof standard for:

- train / validation / calibration / test roles;
- walk-forward;
- OOS;
- sealed test;
- predictive metrics;
- calibration;
- economic significance;
- execution realism;
- robustness;
- strategy-component attribution;
- promotion gates;
- degradation criteria.

The Strategy Constitution defines what a strategy is and what must be tested.

The Validation Constitution defines how much evidence is sufficient.

---

## `08-Roadmap.md`

Will sequence:

- canonical strategy contracts;
- Candidate Prediction schema;
- Strategy Proposal schema;
- Strategy Registry;
- Position Lifecycle extraction;
- Legacy action mapping;
- portfolio boundary implementation;
- execution boundary implementation;
- Candidate Discovery strategy integration;
- ETF / Theme context integration;
- Legacy strategy migration.

The Roadmap may prioritize.

It may not weaken decision ownership for speed.

---

## `09-Glossary.md`

Will freeze terms such as:

- Candidate Prediction;
- Strategy;
- Strategy Proposal;
- Entry;
- Hold;
- Add;
- Reduce;
- Rotate;
- Exit;
- Strategy State;
- Position Lifecycle;
- Strategy Sleeve;
- Portfolio Decision;
- Execution Request;
- Invalidation;
- Risk Enforcement.

---

# 30. Constitutional Strategy Commitments

The project commits to the following strategy model.

1. **A strategy is a scoped decision policy, not the entire research and trading system.**
2. **Candidate Prediction, Strategy Proposal, Portfolio Decision and Execution are distinct authority layers.**
3. **Candidate Discovery remains the current first strategic priority but does not directly own Entry or capital.**
4. **Candidate rank or probability is not an automatic trading action.**
5. **Entry is an independent policy with explicit decision-time and execution-time semantics.**
6. **Position Lifecycle is a repeated decision problem covering HOLD, ADD, REDUCE, ROTATE and EXIT.**
7. **HOLD is an active evaluated decision, not a universal null value.**
8. **ADD is not repeated Entry and requires marginal-position reasoning.**
9. **REDUCE, ROTATE and EXIT have distinct semantics.**
10. **Exit is independent from Entry and may use different targets and evidence.**
11. **Fixed time exits are permitted as strategy-specific policies or baselines, not universal project rules.**
12. **Market Regime, ETF and Theme models may act as context, gates, portfolio inputs or direct strategies only through explicit roles.**
13. **One authoritative strategy decision path exists for each decision scope.**
14. **Alternative models may coexist as research, shadow, diagnostic or ensemble inputs without creating competing final authorities.**
15. **Strategy-local state must be explicit, owned and traceable.**
16. **Strategy-local sleeves are distinct from authoritative physical portfolio positions.**
17. **Portfolio owns final capital allocation and cross-strategy conflict resolution.**
18. **Execution owns order construction, market constraints and fill state.**
19. **A strategy may propose exposure but may not silently assume final account allocation.**
20. **Risk severity, invalidation intent and override authority must be explicit.**
21. **Every formal strategy must define objective, market, universe, signals, entry, exit, position management, risk, backtest requirements, live observation, invalidation and review.**
22. **Strategy components must be attributable; a profitable full system does not prove every rule adds value.**
23. **Legacy strategy knowledge is preserved through characterization and extraction, not by universalizing Legacy enums or God Objects.**
24. **Agents may assist with strategy research and implementation but may not silently change action semantics, authority boundaries, thresholds, targets or promotion status.**
25. **No strategy output constitutes a deterministic return guarantee.**

---

# 31. Closing Declaration

The first phase of `market-regime-alpha` learned how to generate many signals and encode many trading rules.

The next phase must learn how to distinguish:

```text
Prediction
from
Decision
```

and:

```text
Decision
from
Capital Allocation
```

and:

```text
Capital Allocation
from
Execution
```

The target Strategy System is one in which:

```text
Every strategy has a mandate.
Every Candidate has a target.
Every Entry has a decision-time contract.
Every position has explicit state.
Every HOLD is evaluated.
Every ADD has marginal justification.
Every REDUCE has an intent.
Every ROTATE compares opportunity cost.
Every EXIT has an invalidation or objective.
Every proposal has a trace.
Every portfolio allocation has one owner.
Every execution has one owner.
Every strategy can be tested, compared, degraded and retired.
```

The constitutional strategy principle is therefore:

> **Predict explicitly. Decide explicitly. Allocate explicitly. Execute explicitly. Never let one signal silently become all four.**
