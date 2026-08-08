# WP-CRR-01 — Continuous Research Runtime

> **Status:** ROADMAP
> **Authority:** Bounded work package for CRR-00 through CRR-06
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../../superpowers/specs/2026-08-06-continuous-research-runtime-design.md, ../../superpowers/plans/2026-08-06-wp-crr-01-continuous-research-runtime.md, ../../audit/WP-CRR-01-CRR-00-Baseline.md, ../../evidence/WP-CRR-01-Acceptance.md, ../../runbooks/Continuous-Research-Runtime.md
> **Code Evidence:** `src/market_regime_alpha/application/continuous_research`, migration `020_continuous_research_runtime.sql`, `tests/application/continuous_research`, `tests/persistence/postgres`

## 1. Outcome

WP-CRR-01 adds one PostgreSQL-authoritative all-day orchestration owner. It
polls through an injected existing Provider/FreeData boundary, separates every
Provider Attempt from validated research Evidence, decides material change,
and delegates Dataset, Feature, Controlled and Canonical work to their existing
owners. It does not implement a parallel Provider, Dataset, Feature,
Candidate, Signal, Forecast or Canonical chain.

The additive Decision Window is 14:30 through 14:55 inclusive. It exposes
`DECISION_WINDOW_OPEN`; it does not require execution at exactly `14:55:00` and
does not change the historical fixed-14:55 policy, Target, TargetId, Reader or
Replay contracts.

## 2. Delivered phases

| Phase | Delivered mechanics | Acceptance boundary |
| --- | --- | --- |
| CRR-00 | isolated worktree, origin/main baseline, isolated PostgreSQL, write-authority graph | 41 previously skipped PostgreSQL cases activated and passed |
| CRR-01 | run/tick contracts, session/window policy, RequestScopedUniverse, research-only Orderability | no complete-PIT or execution-authority claim |
| CRR-02 | migration 020, PostgreSQL Journal, Claim, Lease, fencing, CAS, idempotency, recovery, `SKIP LOCKED` | no SQLite CRR writer |
| CRR-03 | append-only Provider Attempts, immutable Evidence Commits, last-valid Evidence CAS | failed/timeout/invalid attempts never replace valid Evidence |
| CRR-04 | canonical material hash, Change Decision, Child lineage and identity reuse | no-change makes zero child-service calls |
| CRR-05 | thin exact-time Eligibility and research Orderability scope adapter | missing evidence becomes `UNKNOWN`; Entry remains blocked |
| CRR-06 | bounded one-tick Runner, durable schedule reservation, existing-service ports/composition, crash recovery, CLI schedule/report/replay | local engineering fixtures only; no sustained production operation |

## 3. Core invariants

1. A failed Provider Attempt is operational evidence, never consumable research Evidence.
2. Only a successful Attempt with a validated SourceManifest may produce an Evidence Commit.
3. A stale Claim, Lease, fencing token or tick version cannot publish a pointer or receipt.
4. Transport time, retry count, Attempt ID and Lease metadata do not change material identity.
5. `NO_MATERIAL_CHANGE` records a decision and reused lineage but publishes no Dataset/Feature and starts no Controlled/Canonical child.
6. Every child reference binds Trading Date, run, tick, Attempt, SourceManifest, Evidence, Change Decision, input Artifact set and configuration set.
7. RequestScopedUniverse remains request-scoped and preserves excluded/missing rows.
8. Eligibility and Orderability are separate; missing orderability evidence yields `ORDERABILITY_UNKNOWN`.
9. Runtime success cannot create Opportunity, Order, BrokerOrder, real Fill or Position mutation.
10. Entry and Broker authority remain false in Runner, report, replay and CLI output.

## 4. PostgreSQL authority

Migrations 020 and 021 add nine tables:

- `continuous_research_run`;
- `continuous_runtime_tick`;
- `continuous_provider_attempt`;
- `continuous_evidence_commit`;
- `continuous_current_evidence`;
- `continuous_change_decision`;
- `continuous_child_run`; and
- `continuous_runtime_event`; and
- `continuous_runtime_schedule`.

The migration extends `runtime_database_bindings` with the
`CONTINUOUS_RESEARCH` scope. Immutable tables reject update/delete. Mutable
projections require monotonic versions and fencing tokens. Every foreign-key
column used by lineage joins has a supporting index.

## 5. Recovery model

The Journal uses short PostgreSQL transactions. External Provider and child
service calls occur outside Journal transactions. Expired in-progress ticks are
returned to `PENDING`; any started Attempt is terminally marked
`LEASE_EXPIRED`. A recovered worker receives a higher fencing token.

If Evidence or a Change Decision is already durable, the Runner resumes after
that boundary. Existing child services must expose durable idempotent receipt
lookup; after a crash, CRR records the returned identity as `REUSED` and fills
only missing CRR lineage rows.

## 6. Explicit non-goals and future packages

WP-CRR-01 itself did not deliver the later WP-STATE-01 state machines; those are
an additive Continuous child and do not change this package's authority. The
following remain not delivered: `DailyDecisionWindowSummary`, Daily Summary,
Manual Account, Reconciliation, Model Registry Selector, economic validation, Shadow
Runtime process supervision, authenticated operators, formal PIT
qualification, qualified Alpha, Opportunity/Order creation, QMT/PTrade/Broker
integration, real Fill or Position mutation.

These gaps remain separate work packages. WP-CRR-01 must not be used as
evidence that any of them is ready.
