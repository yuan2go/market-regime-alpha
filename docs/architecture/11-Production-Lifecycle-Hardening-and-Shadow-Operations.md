# Production Lifecycle Hardening and Shadow Operations

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Architecture for hardening the implemented production-decision lifecycle and preparing non-broker Shadow operations
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** 09-Platform-Architecture-V2.md, 10-Production-Decision-Lifecycle.md, decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../audit/Production-Lifecycle-Hardening-Baseline.md, ../audit/Production-Lifecycle-Hardening-Delivery.md, ../operations/Production-Decision-Lifecycle-Runbook.md
> **Code Evidence:** `a7ce0b444e77506a85e1c1c7b240c22c8421580d`; target changes require phase delivery evidence before they become implementation facts

## 1. Purpose and evidence ceiling

Phases 0–7 established an exploratory, manual-only engineering chain. This
architecture hardens that chain without redesigning it, creating a second
authority, or authorizing a broker mutation path.

The evidence ceiling remains:

```text
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

`Shadow Ready` means that the repository can operate a recoverable,
fully-traced, synthetic or manual-record workflow without LIVE broker writes.
It does not mean that formal data, model parameters, Alpha, calibration,
production risk limits, or a sustained real shadow run have been approved.

## 2. Confirmed baseline weaknesses

At the audited baseline:

- Portfolio construction accepts current positions only for allocation symbols
  and rejects additional account positions;
- independent Risk computes gross, symbol, theme and loss exposure from the
  proposed `target_positions`, not a complete post-trade account;
- ManualTradeRecord binds RiskDecision, PortfolioDecision and TargetPosition,
  but not Opportunity or Thesis;
- Fill binds ManualTradeRecord, while PositionSnapshot merges all Fill events
  in an `account_id + symbol` scope;
- PositionSnapshot lacks authoritative available, frozen, today-acquired and
  sellable-session quantities;
- Portfolio Risk accepts caller-constructed `CurrentPositionInput` values;
- REDUCE and EXIT use the same new Portfolio/Risk requirement as increasing
  exposure;
- callers directly construct ThesisHealthObservation support booleans;
- operational evidence is labelled `HISTORICAL_IMMUTABLE_ARCHIVE`, and the
  downstream bundle retains the Daily SourceManifest as its single manifest;
- Holding and Exit history has no durable repository;
- no continuous ShadowRun, queue, metrics, alert or acknowledgement authority
  exists.

These are implementation facts, not claims that the earlier architecture was
invalid. The prior phases delivered a deliberately small engineering slice;
this work closes its production-mechanics gaps.

## 3. Authority map after hardening

| Authority | Owns | Must not own |
|---|---|---|
| Immutable evidence | source and derived evidence identities, hashes, availability and replay | mutable workflow state |
| Account Portfolio Snapshot | complete reconciled account cash and all current positions at an identified time | research scores or a broker mutation |
| Portfolio construction | explicit proposed deltas and resulting post-trade portfolio | risk approval or actual position |
| Risk Authority | complete-account increasing-risk permission and structured rejection | Fill or position truth |
| Risk-reducing gate | executability of a strictly reducing delta | permission to increase risk |
| Manual execution ledger | manual intent and observed or explicitly synthetic Shadow Fill history | broker authority |
| Position Authority | deterministic account/symbol/book state derived from effective Fill and the trading calendar | Provider reads or target-position mutation |
| Assessment journal | append-only Holding/Exit assessments, schedules, blocked actions and acknowledgements | immutable market evidence |
| ShadowRun journal | recoverable orchestration receipts, queues, metrics and alerts | DailyRun acquisition authority |
| Evaluation | versioned outcomes and validation diagnostics | automatic model or limit mutation |

The Daily Runtime Journal remains the acquisition-stage authority. ShadowRun
is a lifecycle orchestration aggregate and shall reference DailyRun/Artifacts;
it shall not reacquire sources or replace DailyRun state.

## 4. Full-account Portfolio and Risk

The input to portfolio construction is an
`AuthoritativeAccountPortfolioSnapshot`, not an allocation-local position map.
It contains an account identity, time, source reference, net asset value,
available cash, all positions, reconciliation state, version and content hash.
Completeness is an explicit invariant. Missing, stale, unreconciled or
partially scoped account state fails closed.

Each intended change is a `ProposedTradeDelta` bound to one Thesis. Applying
the ordered deltas to the complete account produces a content-addressed
`PostTradePortfolioSnapshot`:

```text
Current complete account
+ Proposed trade deltas
= Resulting complete account
```

Gross exposure, per-symbol exposure, theme concentration and maximum loss use
all resulting positions. Cash and liquidity use the proposed deltas. T+1 uses
Position Authority quantities, not an unrelated caller field. The repository
persists exact input and resulting snapshot identities so Risk can be
recomputed on restore.

### H1 implementation status

The V2 path is implemented with content-addressed account, risk-configuration
and post-trade snapshots, immutable Portfolio/Risk decisions, migration 005 and
CLI/restart support. The original allocation-local V1 schema remains readable
but is not a full-account authority. H1 preserves source Position IDs/hashes;
H2/H3 must still establish book identity and Fill/calendar-derived sellability.

## 5. One traceable position book

The first hardening version supports one open Thesis book for each
`account_id + symbol`. This is a deliberate scope restriction, not a general
multi-strategy allocation model.

```text
Opportunity
→ Thesis
→ PortfolioDecision
→ RiskDecision or RiskReducingDecision
→ ManualTradeRecord
→ Fill
→ Position book
→ Assessment
→ TradeOutcome
```

ManualTradeRecord stores the complete upstream identities and the exact target
or reducing-decision hash. Fill inherits the immutable position-book scope.
PositionSnapshot stores the active Thesis/book identity, contributing manual
trade IDs and Fill IDs. TradeOutcome validates the complete chain rather than
accepting symbol equality as attribution proof.

A database constraint and domain validation prevent two open Thesis books for
one account and symbol. Closing the historical book permits a later Thesis
without merging its fills into the prior outcome.

### H2 implementation status

The traceable V2 path implements this first-version restriction with
`PositionBook`, migration 006 and an immutable binding index. Fill continues
to live only in the migration-004 append-only ledger. V2 ManualTrade and
PositionSnapshot schemas add exact authority identities without altering V1
canonical field sets. `TraceableTradeOutcomeEvaluator` recomputes each Risk
decision and validates each ManualTrade target delta before delegating metric
calculation to the existing evaluator. The design intentionally does not yet
support concurrent strategy sleeves in one account/symbol.

## 6. Fill-derived A-share T+1 authority

For ordinary long-only A-share stock, each PositionLot records trade date,
acquisition time, remaining quantity, available quantity, frozen quantity,
the first sellable trading session, unit cost and settlement state.

The sellable session is resolved by `TradingCalendarArtifact`, which contains
explicit identified sessions. Natural-day or weekday inference is forbidden.
Missing calendar coverage, suspension/orderability uncertainty, stale position
or reconciliation mismatch fails closed.

Corrections never mutate a Fill. Replaying effective Fill plus the same
calendar produces exactly the same lot availability, realized PnL and
PositionSnapshot identity.

### H3 implementation status

V3 PositionSnapshot implements the settlement fields and retains exact
calendar ID/hash plus typed symbol-session status IDs. Its projector consumes
only a traceable book's effective Fill ledger. A sell exceeding quantities
whose explicit next session has arrived creates reconciliation-required state;
suspension or unknown status yields zero available quantity with a distinct
sellability reason. `PositionAuthoritativePortfolioRiskApplicationService`
enumerates repository OPEN books and removes caller-authored availability from
the hardened Risk route. Existing H1 and V1/V2 inputs remain compatibility
readers, not H3 sellability authority.

## 7. Increasing risk versus reducing risk

Increasing exposure (`OPEN`, `ADD`, or a larger target) requires the complete
account Portfolio and independent hard-risk decision.

Reducing exposure (`REDUCE`, `EXIT`) uses a separate
`RiskReducingExecutionGate`. This gate does not require unused opening-risk
budget or the increasing-risk service to be available, but it requires a
current Position Authority snapshot, reconciliation, a strictly non-increasing
absolute position, available quantity, T+1 sellability, market executability,
liquidity and a manual actor/reason.

The gate returns structured states such as:

```text
RISK_REDUCTION_ALLOWED
EXIT_BLOCKED_BY_MARKET_CONSTRAINT
T_PLUS_ONE_NOT_SELLABLE
POSITION_RECONCILIATION_REQUIRED
EXECUTION_STATE_UNKNOWN
```

An execution constraint is not a Holding signal. The increasing-risk service
cannot invoke the reducing gate to bypass hard-risk approval.

## 8. Derived Thesis health

External commands submit verified Artifact references and an explicit,
versioned health configuration. `ThesisHealthObservationBuilder` verifies
Thesis, Position, Market Regime, Theme Rotation, Capital Evolution,
SignalSnapshot and price evidence, including hash, symbol/theme scope,
DecisionTime and AvailabilityTime.

Only the builder derives support states, triggered invalidation condition IDs,
missingness and evidence references. There is no command or CLI field for a
caller-supplied final `signal_support`, `theme_support` or `capital_support`
value.

## 9. Composite operational evidence index

Daily and supplemental SourceManifests remain independent authorities. A new
`CompositeOperationalInputManifest` indexes them without copying their source
facts. It binds both Artifact/manifest identities and hashes, DecisionTime,
AvailabilityTime, per-field authority references, DataEligibility,
missingness and its own content hash.

Current operational exploratory evidence uses the explicit kind:

```text
OPERATIONAL_EXPLORATORY_ARCHIVE
```

This label cannot be promoted to LIVE, formal PIT or formal OOS by replay. A
composite manifest is a lineage index, not a replacement SourceManifest.

## 10. Durable assessment and Shadow operation

Assessment history is append-only. A rebuildable projection owns the latest
Holding/Exit state, review schedule, pending reduction, blocked execution,
reconciliation requirement, stale-evidence state and operator acknowledgement.
Every command has an idempotency key, actor, reason, time and optimistic
version.

ShadowRun provides CLI-first recoverable orchestration:

```text
Scheduled Research
→ Opportunity queue
→ Human Thesis approval
→ Portfolio/Risk proposal
→ Manual intent
→ Manual-recorded or synthetic Shadow Fill
→ Position review
→ Holding/Exit assessment
→ Exception/reconciliation queues
→ Outcome/scorecard
→ Daily operations report
```

Each stage has a receipt and correlation ID. Metrics, structured logs, alerts
and operator acknowledgements are durable enough to recover after restart.
`SYNTHETIC_SHADOW_FILL` is explicitly labelled with its price source,
availability, slippage assumption, eligibility and limitations; it is never
reported as a real Fill or broker authority.

## 11. Model-validation boundary

The current path implementation is an empirical unconditional research
baseline and shall be named `EmpiricalPathBaselineV1` in validation output.
Validation infrastructure may compare Candidate-only, Candidate+Signal,
simple control and random-timing groups under PIT, cost, purging, embargo,
walk-forward and segmentation protocols.

Infrastructure output may calculate return, MFE, MAE, capture, giveback, hit
rate, profit factor, drawdown, turnover, exposure, duration, tail loss,
capacity, monotonicity, calibration error and incremental value. It shall not
claim Alpha or probability calibration without qualified external evidence.

## 12. Persistence, migration and recovery

- PostgreSQL 16 is the sole durable database adapter; repository Protocols
  preserve bounded-domain interfaces without permitting backend selection.
- New hardening tables use migrations after versions 001–004 and do not alter
  `daily_runs` semantics.
- Mutable aggregates use optimistic versions and command idempotency.
- Append-only event/Fill/assessment history is never overwritten by a
  projection repair.
- Published migrations are forward-only and verified in isolated PostgreSQL
  schemas. Operational rollback stops writes, retains append-only evidence, and
  rebuilds projections after forward repair.
- Immutable Artifact content is not copied into operational tables.

## 13. Shadow readiness criteria

The repository can be labelled `SHADOW_READY_ENGINEERING` only after:

1. all repository quality gates pass;
2. a complete synthetic E2E passes;
3. restart and replay reconstruct identical authority state;
4. every Fill is traceable and every Position reconciles to Fill;
5. all failure paths have structured state and queue visibility;
6. no LIVE broker mutation exists;
7. missing real data fails closed;
8. migration and recovery tests pass.

Real operation for 20–60 trading days, qualified Provider/PIT evidence,
validated parameters, formal OOS Alpha, production authentication and any
broker authority remain separate admission evidence.
