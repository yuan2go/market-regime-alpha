# PostgreSQL-Only Decision Closure Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** User-approved design for WP-PGSQL-01 and WP-DECISION-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Supersedes:** 2026-08-05-postgresql-authority-migration-design.md for active database architecture
> **Superseded By:** None
> **Related Documents:** ../../audit/WP-PGSQL-01-SQLite-Inventory.md, ../plans/2026-08-06-wp-pgsql-decision-closure.md
> **Code Evidence:** Design baseline `547ddfba39df155a8b53611e1ce9200bf789de60`; implementation claims require later commits and tests

## Objective and authority ceiling

Converge the modular monolith on PostgreSQL 16 as its only operational
database, then add a research/manual-decision-support closure from the existing
State System to an immutable Daily Decision Summary, observed account,
reconciliation, research portfolio proposal and independently reloaded risk
decision.

The delivered authority ceiling is `RESEARCH / MANUAL_DECISION_SUPPORT`.
Nothing in this design grants Entry, Order, Fill, Position mutation, Broker,
formal PIT, OOS, Shadow or production authority.

## Considered approaches

1. **Native PostgreSQL convergence, then one decision child — selected.**
   Every durable repository uses psycopg and PostgreSQL semantics directly.
   The decision stages are added to the existing Continuous Runtime as one
   ordered `DECISION_SYSTEM` child.
2. **Keep the DB-API bridge and add decision tables — rejected.** It would
   preserve SQLite algorithms, shared emulation locks and a re-enable path,
   contradicting PostgreSQL-only authority.
3. **Create a separate decision database/runtime — rejected.** It would add a
   second scheduler, account authority and recovery protocol and would weaken
   lineage and transaction fencing.

## PostgreSQL-only architecture

```text
Application / Domain
  -> bounded Repository Protocol
  -> Native PostgreSQL Repository
  -> PostgresConnectionFactory
  -> PostgreSQL 16
```

`DatabaseSettings` holds exactly one PostgreSQL URL. Construction validates a
PostgreSQL scheme, host and database name. Missing or unreachable PostgreSQL
raises typed `DATABASE_UNAVAILABLE`; no path, backend enum, feature flag or
fallback exists.

Each bounded repository owns its SQL and domain restoration. Shared
persistence code is limited to connection pooling, migration execution,
credential redaction, native row/time validation and narrow transaction/lock
helpers. It does not translate SQLite SQL or impersonate another DB-API.

Transactions use the smallest aggregate scope:

- `FOR UPDATE` for existing aggregate/account/date pointers;
- `FOR UPDATE SKIP LOCKED` only for claim queues, with retry/fairness tests;
- conditional version updates for CAS;
- current claim, Lease, fencing token and tick version at every decision write;
- scope advisory locks only to serialize first creation when no row can be
  locked, keyed by bounded context plus aggregate identity;
- database-wide advisory lock only for the migration registry.

Replay creates an isolated PostgreSQL schema, applies migrations, imports
immutable Artifact evidence through verified Readers, replays deterministic
services, compares identity/lineage/output and drops only the exact test schema.

## Decision bounded context

The decision system is a new bounded application package. It reuses existing
State, Pool, Candidate, Signal, Forecast, Fill-derived Position, Portfolio and
Risk concepts without creating another position ledger or trading path.

```text
Continuous Runtime Tick
  -> DECISION_SYSTEM child
    -> ACCOUNT_OBSERVATION_LOOKUP
    -> RECONCILIATION
    -> SUMMARY_PREVIEW
    -> PORTFOLIO_PROPOSAL
    -> RISK_DECISION
    -> SUMMARY_FINALIZE
```

Every child receipt binds Continuous Operation ID, Runtime Tick ID, claim,
Lease, fencing token, tick version, State receipt and configuration/model
versions. A stale worker is rejected before every write and finalize.

## Daily decision window

The existing `Asia/Shanghai` 14:30:00-14:55:00 inclusive runtime window is
used. It is a window, not a required exact tick. Before 14:30 a Final cannot be
created. A Preview may be created in-window. A Final or Blocked terminal is
append-only and unique for trading date, account and strategy configuration.
Correction creates a new revision linked to the prior Final. Evidence arriving
after 14:55 cannot mutate or be selected into the earlier Final.

Allowed lifecycle states are `WINDOW_NOT_OPEN`, `PREVIEW_AVAILABLE`,
`WAITING_FOR_REQUIRED_EVIDENCE`, `FINALIZING`, `FINALIZED`, `BLOCKED` and
`CORRECTED`. Allowed outcome semantics are `NO_ACTION`, `WATCH`,
`RESEARCH_BUY_CANDIDATE`, `DATA_INSUFFICIENT`, `ACCOUNT_NOT_CALIBRATED`,
`RECONCILIATION_REQUIRED`, `RISK_BLOCKED` and `MODEL_NOT_QUALIFIED`.

Summary construction receives an explicit identity graph; it never queries
"latest" records. Candidate lines preserve score/rank, State/Pool membership,
Signal factor coverage, empirical MFE/MAE/sample coverage, evidence and counter
evidence, invalidation, current position, research exposure ceiling, risk
result and model qualification. No uncalibrated probability field exists.

## Manual Account Observation

`ManualAccountObservation` is an append-only observation of an external real
account, not position authority. Money and price fields use Decimal-based
domain values and PostgreSQL `NUMERIC`. Each revision binds account, trading
date, aware as-of, equity/cash totals, source, actor, reason, notes,
idempotency key, previous observation and immutable position observations.

JSON and CSV application commands validate duplicate symbols, non-negative
quantities, quantity partitioning and Decimal precision. Recording or revising
an observation cannot call or modify ManualTrade, Fill, PositionSnapshot or
average-cost projection.

## Reconciliation

`AccountReconciliationReport` compares one explicit observation with one
explicit Fill-derived Position snapshot and Fill ledger head under one
tolerance configuration. Difference lines cover equity, cash, total/available/
frozen quantity, average cost, missing positions, suspected unrecorded trade,
corporate action, T+1 and insufficient data.

Statuses are `RECONCILED`, `RECONCILIATION_REQUIRED`, `DATA_INSUFFICIENT` and
`MANUAL_REVIEW_REQUIRED`. Reports and revisions are append-only and CAS-
protected. A difference is resolved only by separately authoritative real
trade/Fill/correction/corporate-action or manual-resolution evidence; the
service never fabricates one.

Missing/stale observation, incomplete Fill head, quantity/availability
difference, unknown position, unresolved report or lineage mismatch blocks
OPEN/ADD research actions.

## Research Portfolio Proposal

`ResearchPortfolioProposal` consumes an explicit Summary revision, State/Pool/
Candidate/Signal/Forecast lineage, observed account, reconciled Fill-derived
position, liquidity/orderability and versioned risk configuration. Lines hold
current/proposed research weights, delta, Decimal amount, theme/symbol
exposure, liquidity/position constraints, reasons, invalidation and model
qualification.

It is immutable research advice. Its repository and service have no dependency
on execution, Fill creation, Position mutation or Broker ports.

## Independent Risk Decision

The Risk service accepts only a Proposal identity, then reloads the Proposal
and every authoritative input from PostgreSQL. It recomputes freshness,
reconciliation, Fill-derived Position/T+1, State, concentration, correlation,
liquidity, orderability, model qualification, portfolio exposure, configured
loss limit and complete lineage. Proposal-derived assertions are never trusted.

Allowed results are `RESEARCH_APPROVED`, `RESEARCH_REDUCED`, `RISK_BLOCKED`,
`DATA_INSUFFICIENT`, `ACCOUNT_NOT_CALIBRATED`, `RECONCILIATION_REQUIRED`,
`MODEL_NOT_QUALIFIED` and `ORDERABILITY_UNKNOWN`. Approval remains research
approval only.

## Migration design

Forward migration 024 adds decision window/summary, account observation,
reconciliation, proposal, risk and decision child receipt tables. Tables use
`TIMESTAMPTZ`, `DATE`, `NUMERIC`, native `BOOLEAN`, explicit checks and foreign
keys, partial unique indexes for one Final, revision/CAS columns, idempotency
keys and active-fence bindings. Trigger functions enforce append-only rows,
terminal immutability and monotonic pointer versions only; audited Python owns
decision logic.

Migration 025, if required by the repository audit, removes obsolete runtime
binding values or adds non-destructive PostgreSQL-native constraints that
cannot safely share 024. Published migrations 001-023 remain byte-unchanged.

## Failure, recovery and correction

Database unavailability, Reader verification failure, stale evidence, lineage
mismatch, invalid configuration, missing model qualification and unknown
orderability are typed blockers. They never select another database or weaken
risk outcomes.

Idempotent commands with the same semantic input return the existing immutable
result. Reused keys with different hashes conflict. Crashes resume at the first
missing durable receipt. A later active worker may reclaim an expired decision
child at a strictly larger fence; the old worker cannot persist a report,
Summary, Proposal, Risk decision or Final.

## Verification and non-claims

The acceptance suite uses pure domain tests only where persistence is absent;
all repository, migration, runtime, concurrency, replay and CLI tests use the
temporary PostgreSQL 16 instance and isolated schemas. Package inspection must
find no runnable SQLite backend or bridge.

The work does not modify Market/ETF/Theme/Capital thresholds, Dynamic Pool
policy, Candidate weights, Signal rules, Forecast algorithm/horizon, Model
Registry status, historical 14:55 identities, Entry blocker or trading
authority.
