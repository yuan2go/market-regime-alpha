# Research Shadow Operations Runbook

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Operator procedure for the Research Shadow operating loop
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/16-Phase-A-Correctness-and-Research-Shadow-Operations.md, ../runbooks/Continuous-Research-Runtime.md, PostgreSQL-Authority-Runbook.md
> **Code Evidence:** `cli/research_shadow.py`, `application/shadow_research/operations.py`, `application/runtime_operations/query.py`

## 1. Safety boundary

`research-shadow` operates only PostgreSQL Research Shadow authorities. It does
not start a second Runtime and cannot create an Order, Fill, Broker call or
Position mutation. Fixture and simulated-clock runs must remain
`prospective_proven=false`.

Set an explicit PostgreSQL 16 target and schema:

```bash
export MARKET_REGIME_ALPHA_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DB'
export MARKET_REGIME_ALPHA_DATABASE_SCHEMA='market_regime_alpha'
```

Apply migrations and run the preflight before scheduling:

```bash
uv run python scripts/apply_postgres_migrations.py
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  preflight --help
```

Use the complete arguments from the Continuous Runtime runbook for the actual
date, Provider profile, calendar, configuration and Artifact root.

## 2. Schedule and attach

Create one Session for an already-created SHADOW Continuous Run:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  schedule \
  --run-id CONTINUOUS_RUN_ID \
  --trading-date YYYY-MM-DD \
  --scheduled-at RFC3339_TIME \
  --idempotency-key UNIQUE_SEMANTIC_KEY
```

Attach the Session to that Runtime; this does not execute or replace
`continuous-research run-due`:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  run --session-id SESSION_ID --expected-version VERSION
```

Identical schedule and already-running attach requests are observations of the
existing state. A changed command under the same idempotency key fails closed.

## 3. Freeze and await T+1

After the canonical Runtime has durably produced its SHADOW Summary:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  freeze \
  --session-id SESSION_ID \
  --summary-id SUMMARY_ID \
  --frozen-at RFC3339_FREEZE_TIME \
  --expected-version VERSION

uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  outcome-pending --session-id SESSION_ID --expected-version VERSION
```

Freeze validates the Summary, State, Pool, Candidate, Signal, Forecast,
governance, Provider and State Policy lineage. Do not edit the Decision or
backdate `--frozen-at`.

## 4. Settle factual and multi-target outcomes

Only after the next-session source is actually available, provide verified raw
source archive, settlement Dataset and factual evidence files:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  settle \
  --decision-id DECISION_ID \
  --source-archive SOURCE_ARCHIVE.json \
  --settlement-dataset DATASET.json \
  --factual-evidence FACTUAL_EVIDENCE.json \
  --next-session-date YYYY-MM-DD \
  --session-status TRADING_DAY \
  --expected-version VERSION \
  --created-at RFC3339_SETTLEMENT_TIME \
  --code-revision FULL_OR_UNAMBIGUOUS_REVISION \
  --clock-mode LIVE_TRUSTED \
  --runtime-origin LIVE_ACQUISITION
```

Use `NON_TRADING_DAY` or `UNKNOWN` when that is the observed calendar fact.
Partial and unavailable quotes remain typed outcomes. Never substitute a
future checkpoint or a fixture to make a missing label complete. Repeating an
identical settlement verifies and reuses the durable facts; conflicting
evidence fails.

## 5. Build the frozen research panel

Export or locate the exact frozen Dynamic Pool, CandidateSet and ordered State
Policy reference JSON used by the Decision, then run:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  build-evaluation \
  --decision-id DECISION_ID \
  --targeted-outcome-id TARGETED_OUTCOME_ID \
  --target-protocol-id TARGET_PROTOCOL_ID \
  --dynamic-pool POOL.json \
  --candidate-set CANDIDATES.json \
  --state-policy-references STATE_POLICIES.json \
  --artifact-root ARTIFACT_ROOT \
  --created-at RFC3339_PANEL_TIME
```

The panel retains excluded and rejected symbols; do not reduce it to selected
Candidates before publication.

## 6. Inspect, replay and recover

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  report --session-id SESSION_ID

uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  replay --decision-id DECISION_ID

uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  inspect-trading-date --trading-date YYYY-MM-DD
```

After a recorded failure, use `resume --session-id ... --expected-version ...`.
A crash while the Session is already running can be inspected and continued;
do not schedule a replacement Run. A crash after factual V1 settlement is
recovered by repeating `settle`, which verifies V1 before adding any missing
V2 Target/Attestation records.

Invalidate a non-terminal Session only with an explicit reason:

```bash
uv run research-shadow \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  invalidate \
  --session-id SESSION_ID \
  --expected-version VERSION \
  --reason-code OPERATOR_INVALIDATED
```

Never repair immutable history with SQL updates. Use a new policy/protocol,
new Session, explicit invalidation or a forward migration.
