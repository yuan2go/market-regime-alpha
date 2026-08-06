# Daily Decision System Runbook

> **Status:** CURRENT_SPECIFICATION
> **Mode:** RESEARCH / MANUAL_DECISION_SUPPORT
> **Database:** PostgreSQL 16 authority only
> **Execution authority:** none

## Decision chain

```text
State System
→ ACCOUNT_OBSERVATION_LOOKUP
→ RECONCILIATION
→ SUMMARY_PREVIEW
→ PORTFOLIO_PROPOSAL
→ RISK_DECISION
→ SUMMARY_FINALIZE
```

`DECISION_SYSTEM` is the single Decision child of the existing Continuous
Research Runtime. It does not introduce another scheduler or daily runtime.
Every persisted child result is bound to the Continuous Operation, Runtime Tick,
Claim, lease, fencing token, tick version and State receipt.

## Decision window

The window is 14:30:00–14:55:00 `Asia/Shanghai`, inclusive. It is not an exact
14:55 single-point task.

- before 14:30: `WINDOW_NOT_OPEN`, no Preview or Final;
- during the window: Preview is allowed;
- Finalize requires all bound evidence to have `AvailableAt <= AsOfTime` and
  both times no later than 14:55;
- a complete post-close bar is prohibited;
- one original `FINALIZED` or `BLOCKED` terminal exists per trading date,
  account and strategy configuration;
- a correction appends a `CORRECTED` version and never overwrites the original.

The historical fixed 14:55 Entry Path Target identity and its Readers are not
changed by this Decision Summary window.

## Manual account input

JSON:

```bash
uv run decision-system --database-url "$DATABASE_URL" \
  --database-schema "$DATABASE_SCHEMA" \
  record-manual-account --input manual-account.json
```

CSV (one position per row, repeated account header):

```bash
uv run decision-system --database-url "$DATABASE_URL" \
  --database-schema "$DATABASE_SCHEMA" \
  import-manual-account --input manual-account.csv
```

Required account fields are `account_id`, `trading_date`, `as_of_time`,
`total_equity`, `available_cash`, `frozen_cash`, `source`, `actor`, `reason`,
`idempotency_key`, `revision` and `created_at`. Position quantities must form an
exact total/available/frozen partition. Decimal values must be JSON strings or
integers, never binary floats.

An observation is append-only and revisioned. It records a human observation;
it cannot create or modify ManualTrade, Fill, Position, average-cost authority
or T+1 state.

## Reconciliation

```bash
uv run decision-system --database-url "$DATABASE_URL" \
  --database-schema "$DATABASE_SCHEMA" \
  reconcile-account --input reconciliation-command.json
```

The command explicitly binds the observation, Fill-derived Position snapshots,
Fill Ledger head/completeness, tolerances and active Runtime Claim. It detects
equity, cash, quantity, available/frozen quantity, average cost, missing
positions, suspected unrecorded trade, suspected corporate action, T+1 and
insufficient-data differences.

Any unresolved difference blocks OPEN/ADD research deltas. Resolution requires
real ManualTrade/Fill correction, Corporate Action adjustment or an explicit
human resolution artifact. Reconciliation never fabricates a transaction.

## Preview and Finalize

Both commands consume one JSON object with explicit `request` and `inputs`
objects. No command selects the latest Candidate, Signal, Forecast, State,
account observation, Position or configuration implicitly.

```bash
uv run decision-system --database-url "$DATABASE_URL" \
  --database-schema "$DATABASE_SCHEMA" \
  preview-daily-decision --input decision-command.json

uv run decision-system --database-url "$DATABASE_URL" \
  --database-schema "$DATABASE_SCHEMA" \
  finalize-daily-decision --input decision-command.json
```

The Portfolio output is `ResearchPortfolioProposal`. Independent Risk accepts
only its ID, reloads Proposal, Summary, Manual Account and Reconciliation from
PostgreSQL, and revalidates lineage, freshness, model qualification,
orderability, concentration, liquidity, exposure and available loss limit.
`RESEARCH_APPROVED` means only that a research proposal passed those checks.

## Inspection

```text
inspect-manual-account --observation-id ID
inspect-reconciliation --reconciliation-id ID
inspect-daily-decision --summary-id ID
inspect-portfolio-proposal --proposal-id ID
inspect-risk-decision --risk-decision-id ID
```

Output is deterministic, sorted JSON and always declares:

```text
entry_authority_granted = false
order_created = false
fill_created = false
position_mutated = false
broker_called = false
```

## Fail-closed outcomes

Missing/stale account observation, unresolved reconciliation, incomplete Fill
lineage, unqualified model, unknown orderability, stale State/data, incomplete
Dynamic Pool, invalid risk configuration, mismatched Candidate/Signal/Forecast
lineage or a rejected PostgreSQL Reader blocks the Decision path. It never
falls back to another database or calls a Broker.
