# WP-13 Remaining Decision Support Closure Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Approved implementation contract for WP-13 only; not
> Runtime/CLI Cutover, Execution, Formal PIT/OOS/Prospective evidence, Alpha,
> trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Frozen At:** 2026-09-02
> **Execution-Time Origin Main:**
> `origin/main@6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **WP-12 Verified Implementation:**
> `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **Branch:** `agent/wp-13-remaining-decision-support-closure`
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP12_EXIT_GATE = PASS / MERGED
WP13_DESIGN = FROZEN
WP13_IMPLEMENTATION = NOT_STARTED
Model/Calibration = SKIPPED / OPTIONAL
Execution = NO-GO
Runtime/CLI Cutover = NO-GO
Formal PIT/OOS/Prospective = NOT_PROVEN
Production = NO-GO
```

## 1. Audit result and supersession boundary

WP-12 is an ancestor of execution-time main and supplies a concrete exact-ID,
cutoff-aware, generation-safe admitted-qualification read seam. The target
Decision Support package contains only WP-09 DecisionRun/Target/Commitment/
Reference. No target Context, Signal, Forecast, Opportunity, Thesis, Strategy,
Portfolio, or Risk relation exists. The sole target composition root constructs
WP-09 through WP-12 commands but no remaining Decision Support command.

The canonical architecture already freezes the one-way lifecycle and the
logical owner vocabulary. WP-13 supplies the implementation-level policy,
binding, roster, transaction, and recovery detail intentionally deferred by
WP-08. Historical `context`, `signals`, `forecasting`, `strategies`,
`portfolio`, `position`, daily, Shadow, formal-research, and Legacy SQL paths are
behavioral characterization only. They cannot be imported by target Domain or
Application, called by target Infrastructure, or dual-written.

The active Roadmap text that made optional Model/Calibration a prerequisite for
rule-based Decision Support is superseded. Model remains an optional later
branch and this package creates neither `model`, `model_version`,
`forecast_model_binding`, nor `evaluation_forecast_binding`.

## 2. Considered designs

### A. Reuse Legacy services and tables

This is rejected. Current paths mix artifacts, current-state selection,
caller-provided labels, pre-Strategy risk, mutable account/position projections,
and several composition roots. A compatibility facade or dual write would make
Authority depend on availability and prevent exact replay.

### B. One DecisionLifecycle aggregate and God UoW

This is rejected. One command/transaction spanning Context through Risk would
reverse existing lock order, make independent definitions inseparable, and
turn recovery into partial hidden state or an unmaintainable mega-aggregate.

### C. Cohesive Decision Support modules with complete relational rosters

This is approved. All ownership stays in
`market_regime_alpha.decision_support`; seven narrow UoWs protect independent
roots while concrete FKs and root-last closure preserve the one-way chain.
Definitions are registered before execution; calculation reads are prepared
outside short writes and revalidated under lock; no current/latest or caller
value becomes Authority.

## 3. Authority DAG and generation rule

```text
ResearchQualification(n)
  └→ DecisionRunQualificationRoster/Member(n+1)
        └→ DecisionRun(n+1)
              └→ ContextAssessment/Metric/Source
                    └→ Signal
                          └→ Forecast/Estimate
                                └→ Opportunity/ContextBinding
                                      └→ Thesis/Condition
                                            └→ PortfolioProposal/Line
                                                  └→ RiskDecision/Reason
```

Immutable definitions enter the graph without reversing it:

```text
ContextPolicy/MetricRule ───────────────→ ContextAssessment
Strategy/StrategyVersion/Rules ─────────→ Signal/Forecast/Opportunity
PortfolioPolicy ────────────────────────→ PortfolioProposal
RiskPolicy/Rule ────────────────────────→ RiskDecision
```

The cross-generation rule remains:

```text
Outcome(n) → Evaluation(n) → Qualification(n) → DecisionRun(n+1)
```

No same-generation Outcome, Evaluation, Evidence, Assessment, Qualification,
or Market correction can feed the already-open DecisionRun `(n)`. Every
downstream fact binds exact immutable IDs; no current/latest selector exists.

## 4. Risk and Execution boundary correction

WP-13 cannot create an Account, AccountAuthorityEpoch, Position, Intent, Fill,
or broker fact because Execution is explicitly non-scope. It therefore freezes
one unambiguous Risk contract:

- `RiskDecision` is the sole Decision Support authorization over one complete
  Portfolio Proposal under one immutable Risk Policy;
- V1 Risk rules consume only proposal, line, Strategy, Opportunity, Context,
  Signal, Forecast, Market-lineage, and qualification facts already frozen by
  the DecisionRun;
- `authority_scope = DECISION_SUPPORT_ONLY` is constant and relational;
- `AUTHORIZED` means the proposal passed this Decision Support policy only;
- `REJECTED`, `UNKNOWN`, and `NO_ACTION` are terminal and cannot be bypassed;
- no WP-13 status authorizes an Account, Execution Intent, broker request,
  Order, Fill, Position change, trading, or Production.

A later Execution package must bind a concrete accepted RiskDecision plus its
real Account/AuthorityEpoch and may only narrow capacity or block execution. It
cannot overwrite, replace, or reinterpret a WP-13 rejection. This is an
Execution authorization boundary, not a second Risk owner.

## 5. Closed vocabulary

Qualification inputs:

```text
role:       PRIMARY | SUPPORTING | LIMITATION
purpose:    DISCOVERY | VALIDATION | LOCKED_OOS | PROSPECTIVE
```

Context:

```text
kind:       MARKET_REGIME | ETF_ROTATION | THEME_ROTATION | CAPITAL_BREADTH
state:      POSITIVE | NEUTRAL | NEGATIVE | UNKNOWN
status:     AVAILABLE | UNKNOWN | NOT_ESTIMABLE | FAILED
measure:    RETURN | ADVANCE_RATE | TURNOVER | MEMBER_COVERAGE | FLOW_PROXY
reducer:    MEAN_DECIMAL | MEDIAN_DECIMAL | TRUE_RATE | SUM_DECIMAL
operator:   AT_LEAST | AT_MOST | BETWEEN
source:     MARKET_BAR | INSTRUMENT_FACT | CLASSIFICATION_MEMBERSHIP |
            SOURCE_GAP
```

Signal and Forecast:

```text
signal:       PRESENT | NO_SIGNAL | WAIT | UNKNOWN | NOT_ESTIMABLE
forecast:     AVAILABLE | WAIT | UNKNOWN | NOT_ESTIMABLE
estimate:     EXPECTED_VALUE | LOWER_BOUND | UPPER_BOUND | SCORE
calibration:  UNCALIBRATED | NOT_APPLICABLE
```

Opportunity, Thesis, Strategy, Portfolio, and Risk:

```text
opportunity: ACTIONABLE | NO_ACTION | WAIT | NOT_ESTIMABLE
action:      ENTER | ADD | HOLD | REDUCE | EXIT | NO_ACTION | WAIT |
             DATA_INSUFFICIENT
condition:   ENTRY | HOLD | INVALIDATE | REDUCE | EXIT
proposal:    PROPOSED | NO_ACTION | NOT_ESTIMABLE
line:        INCLUDED | EXCLUDED | NOT_ESTIMABLE
risk:        AUTHORIZED | REJECTED | UNKNOWN | NO_ACTION
rule result: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
```

`NO_ACTION != HOLD`. Signal and Forecast values are never probabilities.
WP-13 stores no calibrated-probability status.

## 6. DecisionRun qualification roster

`OpenDecisionRunRequest` adds a declared Research purpose and an ordered tuple
of exact `RequestedResearchQualification(decision_id, role)`. Empty is valid
and intentional. The command never searches by purpose, code, status, latest,
or current.

It atomically writes exactly one
`decision_run_research_qualification_roster` before the root and zero-or-more
contiguous `decision_run_research_qualification_member` rows. The roster stores
count/hash and a reconciliation hash even when empty. Each member concrete-FKs
the exact Research Qualification Decision and copies its purpose, Target,
Experiment, source-generation maximum, effective/known times, and content hash
under a composite FK/trigger guard.

The Decision-owned input adapter validates and the final transaction locks and
revalidates:

```text
decision_status = ADMITTED
qualification purpose = DecisionRun declared purpose
effective_at <= DecisionTime
known_at <= DecisionTime
source_generation_max_decision_time < DecisionTime
no direct successor effective and known by DecisionTime
```

The root-last Decision closure now requires exactly one complete roster. The
request hash and definition summary include declared purpose, every exact
Qualification ID/role/content hash, count, and roster hash. Exact replay never
re-reads Research Qualification. Changed roster or purpose fails closed.

## 7. Context Authority

`ContextPolicy` is an immutable code/version root with code/config Artifacts,
provenance, direct supersession, metric-rule count/hash, and content hash.
`ContextPolicyMetric` freezes kind, metric code/order, measure, reducer,
operator, thresholds, minimum source/available counts, missingness behavior,
and source role. No rule is hidden in config JSON.

`AssessContext` binds one DecisionRun and one Policy and creates exactly one
assessment per declared Policy kind. `ContextMetric` contains the deterministic
typed result of one rule. `ContextMetricSource` is the complete non-empty input
roster and concrete-FKs exactly one Decision-visible Market bar, instrument
fact, classification-membership revision, or SourceGap. Source known time must
not exceed DecisionTime. Values are loaded through a Decision-owned typed Market
port, never accepted from the caller.

Each assessment freezes the exact CandidateSet identity/hash and applies to its
complete scope. Context does not filter or mutate Candidate, Target, commitment,
or qualification rosters and does not access Outcome.

## 8. Strategy, Signal, Forecast, Opportunity, and Thesis

`Strategy` is a stable family. An immutable `StrategyVersion` freezes one
primary action policy, exact code/config Artifacts, required Context roster,
Signal rule, rule-based Forecast rules, Opportunity semantics, action mapping,
provenance, direct supersession, child counts/hashes, and content hash.

Relational children are:

- `strategy_context_requirement`: complete ordered required Context kinds;
- `strategy_signal_rule`: one typed rule over Context states and Candidate
  disposition;
- `strategy_forecast_rule`: complete ordered Target checkpoint/metric estimate
  rules and Decimal coefficients/bounds.

`ProduceSignal` derives one immutable Signal for every Candidate in the
DecisionRun CandidateSet under one StrategyVersion. The command derives the
complete Candidate roster in PostgreSQL and binds every required exact
ContextAssessment through `signal_context_binding`. It never accepts a caller
Candidate subset or a score/probability. Missing Context produces `WAIT`,
`UNKNOWN`, or `NOT_ESTIMABLE` according to the frozen rule; no row disappears.

`ProduceForecast` derives one Forecast for every Signal × matching Decision
Target Commitment required by the StrategyVersion. Each root concrete-FKs the
Signal, Commitment, DecisionRun qualification roster, StrategyVersion, exact
Target, algorithm/code/config, and status. `ForecastEstimate` binds one exact
Target checkpoint/metric and freezes Decimal estimate/bounds. Every output is
`UNCALIBRATED` or `NOT_APPLICABLE`; no probability field exists. No Model table
or nullable binding is created.

`CreateOpportunity` derives the complete Signal/Forecast Candidate roster for
one DecisionRun × StrategyVersion. Every row binds exact Candidate,
Commitment/Target, Signal, Forecast, and the complete required Context set in
`opportunity_context`. It contains no RiskDecision, quantity, or account fact.

`CreateThesis` creates one immutable Thesis revision for an Opportunity and a
complete non-empty ordered `thesis_condition` roster. Conditions are typed,
independently observable requirements with explicit source kind, operator,
threshold/value unit, missing behavior, and invalidation semantics. Revision
changes append and directly supersede; historical Thesis/conditions do not
change.

## 9. Portfolio and Risk closure

`PortfolioPolicy` freezes one immutable allocation contract with typed method,
minimum estimability, maximum line count, maximum single/gross/net weight,
cash-floor, turnover ceiling, Decimal rounding/normalization semantics,
code/config, provenance, direct supersession, and content hash. V1 allocation
is deterministic `EQUAL_WEIGHT_ACTIONABLE`; no caller line roster or weight is
accepted.

`ProposePortfolio` locks one DecisionRun × StrategyVersion and derives the
complete Opportunity roster. Every Opportunity receives exactly one
`PortfolioLine`, including excluded and not-estimable rows. Decimal weights are
computed purely outside the write transaction, then the final transaction
revalidates exact inputs and atomically closes line count/hash, included and
excluded counts, gross/net/cash totals, and proposal content hash. Empty or no
actionable input is a successful `NO_ACTION` proposal.

`RiskPolicy` freezes a complete non-empty ordered typed `RiskRule` roster.
Allowed V1 subjects are proposal status, line count, gross weight, net weight,
single-line weight, cash weight, estimability, and qualification presence.
Units, operator, threshold, severity, and missing behavior are relational.

`AssessRisk` accepts only exact Proposal and Policy IDs. It reloads the complete
Proposal/Line roster and all exact upstream bindings, evaluates every rule, and
writes one `RiskReason` for every global or line-scoped rule input. No failed,
unknown, excluded, or not-estimable line is omitted. Only complete reason/root
reconciliation permits terminal `AUTHORIZED`, `REJECTED`, `UNKNOWN`, or
`NO_ACTION`.

## 10. Persistence and concrete FK closure

Only unreleased `MRA_REFOUNDATION_1/001_baseline.sql` is extended. WP-13 adds
these real Decision Support relations:

```text
decision_run_research_qualification_roster
decision_run_research_qualification_member
context_policy
context_policy_metric
context_assessment
context_metric
context_metric_source
strategy
strategy_version
strategy_context_requirement
strategy_signal_rule
strategy_forecast_rule
signal
signal_context_binding
forecast
forecast_estimate
opportunity
opportunity_context
thesis
thesis_condition
portfolio_policy
portfolio_proposal
portfolio_line
risk_policy
risk_rule
risk_decision
risk_reason
```

All roots and children are append-only. Root-last or equivalent deferred
closure validates contiguous order, complete non-empty/intentional-empty
rosters, concrete same-run/Target/Strategy/Policy identities, counts, hashes,
time, and provenance. Every FK has a leading index. No `002+`, Model,
Calibration, Account, Execution, TradeOutcome, Attribution, generic registry,
polymorphic `(kind,id)`, JSON business owner, compatibility path, nullable
future FK, or placeholder is created.

## 11. Units of work, commands, and composition

The narrow owners are:

```text
DecisionRun UoW:
  DecisionRun + Target/Commitment/Reference + Qualification roster/member

Context UoW:
  ContextPolicy/Metric + ContextAssessment/Metric/Source

Strategy UoW:
  Strategy/Version + ContextRequirement/SignalRule/ForecastRule

Inference UoW:
  Signal/ContextBinding + Forecast/Estimate

Opportunity UoW:
  Opportunity/ContextBinding + Thesis/Condition

Portfolio UoW:
  PortfolioPolicy + PortfolioProposal/Line

Risk UoW:
  RiskPolicy/Rule + RiskDecision/Reason
```

The sole target composition root constructs:

```text
OpenDecisionRun
RegisterContextPolicy / AssessContext
RegisterStrategyVersion / ProduceSignal / ProduceForecast
CreateOpportunity / CreateThesis
RegisterPortfolioPolicy / ProposePortfolio
RegisterRiskPolicy / AssessRisk
DecisionSupportVerifier
```

WP-13 adds no production Runtime dispatcher or business CLI. It may extend only
the target Runtime step vocabulary and dependency specifications required for
real claims in focused tests. WP-14 owns controlled orchestration/scheduling.

## 12. Transactions, concurrency, and recovery

Every command follows:

```text
prepare immutable inputs and pure result outside transaction
→ open owning narrow UoW
→ Runtime fence first when participating
→ exact idempotency/advisory identity lock
→ immutable inputs in global (kind, UUID) order
→ upstream DecisionRun/Commitment
→ Context → Signal/Forecast → Opportunity/Thesis → Portfolio → Risk
→ children + closing root + reconciliation
→ receipt + audit + matching Runtime finalization
→ one PostgreSQL commit
```

No Provider, network, broker, filesystem, Artifact-byte, Market-current,
Outcome, or Legacy call occurs inside a business transaction. No nested
transaction exists. PostgreSQL supplies all Authority times.

Concurrent identical commands produce one root and exact replay. Changed
requests fail closed. Only `40001`/`40P01` receive bounded whole-transaction
retry. Unknown commit probes exact receipt/root and replays; it never blindly
mutates. Injected failures at every child roster roll back the entire owner.
A deterministic failure uses the same narrow UoW in a fresh transaction; stale
fence causes zero business, receipt, audit, or failure writes.

## 13. Read-only verification and reconciliation

`DecisionSupportVerifier` recomputes:

- WP-09 Decision Target/Commitment/Reference closure;
- exact qualification roster, purpose, admission, supersession-at-DecisionTime,
  generation and count/hash;
- Context Policy and complete Assessment/Metric/Source rosters, PIT cutoffs,
  values, status and hashes;
- Strategy definition child rosters and every Candidate Signal/Context binding;
- every expected Commitment Forecast/Estimate and uncalibrated semantics;
- complete Opportunity/Context and Thesis/Condition rosters;
- complete Opportunity → PortfolioLine roster and Decimal totals;
- every Risk Policy rule, global/line RiskReason, terminal decision and scope;
- receipt, audit, optional Runtime claim/fence, Artifact and provenance facts.

Passing is only:

```text
matched = true
mismatch_count = 0
```

The verifier performs no Provider call, current/latest selection, Market or
Outcome reconstruction, Artifact business-payload inference, or mutation.

## 14. TDD seams and qualification

The explicit user contract freezes these public seams for TDD:

1. extended `OpenDecisionRun` exact qualification roster;
2. `RegisterContextPolicy` / `AssessContext`;
3. `RegisterStrategyVersion` / `ProduceSignal` / `ProduceForecast`;
4. `CreateOpportunity` / `CreateThesis`;
5. `RegisterPortfolioPolicy` / `ProposePortfolio`;
6. `RegisterRiskPolicy` / `AssessRisk`;
7. sole `bootstrap_application(...)` composition;
8. read-only `DecisionSupportVerifier`.

Tests use public Domain/Application commands and typed ports. PostgreSQL
specification tests directly prove database constraints and closure because the
database is itself an Authority boundary. Private helper/method behavior is not
the test seam.

Qualification must cover Domain/Application/PostgreSQL behavior, exact replay,
changed requests, real concurrency, stale fence, unknown commit, injected
mid-roster failure and recovery, read-only reconciliation/fault detection,
clean PostgreSQL 16 bootstrap/verify/exact-OID recreate, representative
`EXPLAIN (ANALYZE, BUFFERS)`, full repository tests, Ruff, mypy, build,
documentation/navigation, architecture/import, and diff checks at one exact
implementation SHA.

## 15. Exit gate and evidence ceiling

Only complete code, composition, schema, exact-SHA engineering qualification,
immutable Verification, clean branch, PR, and merged-main recheck permit:

```text
WP13_EXIT_GATE = PASS
```

That state proves deterministic Decision Support engineering only. It does not
prove or authorize Model/Calibration, Execution, Account, Fill/Position,
TradeOutcome/Attribution, Runtime/CLI Cutover, Formal PIT, Formal OOS,
Prospective value, Provider qualification, Alpha, trading, Production, or
Legacy deletion. WP-14 may begin only after the exact verified WP-13 branch is
merged and latest `origin/main` is fetched into a new worktree.
