# Continuous Research Runtime Runbook

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Local engineering operation for WP-CRR-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../roadmap/work-packages/WP-CRR-01-Continuous-Research-Runtime.md, ../evidence/WP-CRR-01-Acceptance.md, ../audit/WP-CRR-01-CRR-00-Baseline.md

## 1. Safety boundary

Use only an explicitly identified PostgreSQL database and schema. Never point
the runtime at an unknown database. The CRR CLI deliberately disables database
URL environment fallback and requires `--database-url`. Use a dedicated test
database/schema for engineering verification.

The CLI and Runner grant no Entry or Broker authority. Do not connect QMT,
PTrade or another Broker. Do not convert a Child receipt into an Order or Fill.

## 2. Prepare an isolated test authority

Follow the disposable-cluster pattern recorded in
[CRR-00 baseline evidence](../audit/WP-CRR-01-CRR-00-Baseline.md). Bind
PostgreSQL to `127.0.0.1` on a dedicated port, create a new database, and set
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL` only for test commands. Stop the exact
cluster and remove only its resolved temporary directory after verification.

Do not reuse an existing local `5432` database merely because it accepts a
connection.

## 3. CLI operations

The CLI performs bounded Journal and durable-schedule administration. Run commands are canonical
JSON produced by `ContinuousResearchCommand.to_canonical_dict()`; tick commands
use `RuntimeTickCommand.to_canonical_dict()`.

```bash
uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  prepare --run-command /absolute/path/run-command.json

uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  admit-tick --tick-command /absolute/path/tick-command.json \
  --session-phase DECISION_WINDOW

uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  resume --run-id continuous-research-run-...

uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  schedule --run-command /absolute/path/run-command.json \
  --trading-day-assessment /absolute/path/trading-day.json \
  --at 2026-08-06T01:30:00+00:00

uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  reserve-due-tick --run-command /absolute/path/run-command.json \
  --at 2026-08-06T01:30:00+00:00
```

`schedule` stores the one versioned schedule for the Trading Date;
`reserve-due-tick` atomically appends at most one due Tick and advances the
next time. Concurrent callers cannot reserve the same schedule position.
`prepare`, `admit-tick`, `schedule`, `reserve-due-tick` and `resume` are
mutations. `report` and `replay` open
the existing schema without applying migrations:

```bash
uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  report --run-id continuous-research-run-...

uv run continuous-research \
  --database-url "$CRR_DATABASE_URL" \
  --application-schema "$CRR_SCHEMA" \
  replay --run-id continuous-research-run-...
```

All outputs are structured JSON. Errors report an error type and generic
credential-free message; they do not echo the supplied DSN.

## 4. Execute a bounded tick

Provider and child execution are programmatic because their existing service
commands and verified receipts are typed artifacts, not arbitrary CLI JSON.
Construct `ContinuousResearchTickRunner` with:

- `PostgresContinuousResearchJournal`;
- a `ProviderAcquisitionPort` implemented by the existing FreeData preparation adapter; and
- `ExistingResearchServiceComposition` delegates for Daily Dataset, Feature Materialization, Controlled Operation and Canonical Lifecycle.
- the exact content-addressed `ContinuousDecisionWindowPolicy` selected by the run.

Invoke one `execute(...)` call for one admitted tick. Do not wrap external
calls in a database transaction. Existing child delegates must provide durable
idempotent lookup before execution.
The Runner derives session phase from policy and Tick time. A child final-write
path must validate the Claim ID, fencing token, Tick version and unexpired
Lease supplied in `ChildExecutionRequest`; those recovery values do not change
the child's semantic idempotency key.

## 5. Incident and recovery procedure

1. Stop the failed worker; do not manually update CRR tables.
2. Wait for or verify Lease expiry.
3. Run `resume` for the exact run ID.
4. Start a bounded Runner invocation for the same tick command.
5. Verify the fencing token increased and the old Claim cannot commit.
6. Run read-only `report` and `replay`.
7. Confirm failed Attempts did not move `continuous_current_evidence`.
8. Confirm Child receipts were looked up and only missing CRR references were appended.

If an existing child service cannot prove durable idempotent receipt lookup,
stop. Do not claim crash-safe child execution.

## 6. Interpretation

`DECISION_WINDOW_OPEN` means the observed time is inside the additive
14:30–14:55 window. It does not mean a decision was executed at `14:55:00`, and
it does not create `DailyDecisionWindowSummary`.

`COMPLETED` means the engineering tick and its receipts settled. It does not
mean data is formally PIT-qualified, Alpha is validated, Entry is allowed, an
Order exists or a Broker was called.
