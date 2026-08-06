# Stateful Research Runtime Runbook

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Local engineering operation and recovery procedure for WP-STATE-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../roadmap/work-packages/WP-STATE-01-Stateful-Research-System.md, ../evidence/WP-STATE-01-Acceptance.md, Continuous-Research-Runtime.md

## 1. Safety boundary

The state system is a `STATE_SYSTEM` child of Continuous Research. Never launch
it as a scheduler or feed it evidence that lacks a parent Operation, Runtime
Tick and active PostgreSQL fence. Do not connect a Broker, QMT, PTrade or
XtQuant. State and Pool output is research evidence, not an Entry or Order.

Use a disposable, explicitly named UTF-8 PostgreSQL database for tests. Set
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL` only to that database. Do not use an
unknown service on port 5432.

## 2. Runtime order

The parent calls the existing Dataset and Feature services before the State
child, then continues to existing Controlled and Canonical services:

```text
Continuous Tick Claim
→ Provider Attempt
→ valid Evidence Commit
→ material Change Decision
→ DAILY_DATASET
→ FEATURE_MATERIALIZATION
→ STATE_SYSTEM
   → OBSERVATION
   → MARKET_REGIME
   → ETF_ROTATION
   → THEME_ROTATION
   → CAPITAL_STATE
   → DYNAMIC_POOL
   → CANDIDATE
   → SIGNAL
   → FORECAST
→ CONTROLLED_OPERATION
→ CANONICAL_LIFECYCLE
→ Runtime Receipt
```

`NO_MATERIAL_CHANGE` stops before all children. A Provider failure records only
the Attempt and retains the last valid Evidence. The State child does not poll a
Provider or materialize a second Dataset/Feature.

## 3. Version selection

The parent command or Runtime policy must explicitly select Model ID/version
and Configuration ID/hash for every state domain and the Pool policy. Reject a
stage service without versioned configuration. Do not introduce a service-local
default threshold.

Before evaluation, verify:

- every input `AvailableAt` is no later than Tick `AsOfTime`;
- the Observation binds Provider Attempt, Evidence, Dataset and Feature IDs;
- Theme mapping is explicit and effective at the observation time;
- the previous State/Pool pointer is the expected CAS predecessor;
- the Tick Claim, Lease, fence and version remain active.

## 4. Inspection commands

The state CLI is read-only and never connects to a database:

```bash
uv run state-system describe

uv run state-system verify-pool \
  --artifact /absolute/path/dynamic-pool.json
```

`describe` prints the single parent owner, ordered stages and false Entry/Broker
authority. `verify-pool` validates content hash and content-derived Pool ID. It
does not advance a pointer or resume a run.

## 5. Recovery

1. Stop the failed worker and do not edit State or Pool rows.
2. Let the Continuous Tick Lease expire and resume through the parent Runtime.
3. Confirm the new Claim has a higher fencing token.
4. Let the State child look up its durable receipt by idempotency key.
5. If the receipt exists, reuse it without rerunning stages.
6. If only domain Artifacts exist, replay deterministic transitions and append
   only the missing receipt after validating their identities.
7. Verify the stale worker cannot update a current pointer or publish a receipt.
8. Use the content-validating Reader for every Pool recovered from storage.

Replay and recovery use an isolated PostgreSQL database or schema. They must
validate the same Claim, Lease, fencing and CAS behavior as the runtime; a
file-backed persistence substitute is prohibited.

## 6. Incident checks

Stop and report a blocked run when any of these occur:

- future Evidence or a complete closing bar enters a 14:30–14:55 Tick;
- Theme mapping coverage is missing and a caller attempts to guess membership;
- a Pool lacks a full included/excluded cross section;
- a new Signal payload writes `confidence` instead of `factor_coverage`;
- Forecast emits a probability while calibration is `NOT_CALIBRATED`;
- an adapter attempts Opportunity, Order, Fill, Position or Broker mutation.

`COMPLETED` proves only local engineering execution and durable identity. It
does not establish formal PIT, OOS Alpha, Shadow or Production readiness.
