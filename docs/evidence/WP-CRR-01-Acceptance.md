# WP-CRR-01 Acceptance Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Observed CRR-00 through CRR-06 verification record
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../roadmap/work-packages/WP-CRR-01-Continuous-Research-Runtime.md, ../runbooks/Continuous-Research-Runtime.md, ../audit/WP-CRR-01-CRR-00-Baseline.md

## 1. Baseline binding

The isolated branch started from `origin/main` commit
`8de820cd149278bfebbaf18f150a90f36380176d` in
`/Users/yuan/projects/market-regime-alpha-worktrees/continuous-research-runtime`.
The original workspace and its `.idea/modules.xml` user modification were not
changed, staged, stashed or committed.

CRR-00 established PostgreSQL 16.14 with a disposable loopback cluster. The
full baseline with a credential-bearing test-only DSN passed 2,266 tests; all
41 database-dependent cases that otherwise skipped were executed.

## 2. Observed implementation checks before final exact-HEAD gate

| Check | Result | Observation |
| --- | --- | --- |
| CRR pure contracts and PostgreSQL package | PASS | Provider/Evidence isolation, change decisions, child lineage, scope, Runner and replay tests passed |
| PostgreSQL migration apply/verify | PASS | migrations 001–020, 67 authority tables |
| Claim/Lease/fencing/concurrency | PASS | stale fences rejected; two workers claimed disjoint ticks with `SKIP LOCKED` |
| Failure isolation | PASS | FAILED, TIMED_OUT, INVALID_RESPONSE, RATE_LIMITED and CIRCUIT_OPEN Attempts preserved the prior current Evidence |
| No material change | PASS | identical material identity produced `NO_MATERIAL_CHANGE`; child-service call counters did not increase |
| Crash recovery | PASS | recovery after Evidence CAS and child receipts skipped Provider/child republication; partial CRR lineage filled only missing rows |
| Request scope and Orderability | PASS | exact request partition retained; missing Eligibility/Orderability evidence failed closed |
| Structured CLI/replay | PASS | explicit PostgreSQL/schema, credential-free errors, read-only report/replay |
| Ruff | PASS | CRR-06 focused run passed |
| mypy | PASS | 355 configured source files passed |

The final exact-HEAD commands are run after the final checkpoint commit and are
reported with that commit SHA in the engineering handoff. This document does
not pre-claim a later commit as tested.

## 3. Acceptance matrix

| Requirement | Evidence | Status |
| --- | --- | --- |
| Sole all-day owner | Runner plus existing-service ports/composition; no second research engine | PASS |
| 14:30–14:55 window | boundary and no-exact-tick policy tests | PASS |
| Historical 14:55 compatibility | unchanged existing policy/Target/Reader/Replay plus regression tests in final gate | PENDING_FINAL_GATE |
| PostgreSQL-only writes | RepositoryFactory rejects SQLite CRR authority | PASS |
| Lease/fencing/CAS/idempotency | PostgreSQL Journal tests | PASS |
| Provider Attempt/Evidence separation | contract and restart tests | PASS |
| Last valid Evidence isolation | five terminal failure classes plus expired Claim | PASS |
| Material identity/reuse | semantic/non-semantic hash tests and call counters | PASS |
| Parent/Child lineage | append-only PostgreSQL reference/restart tests | PASS |
| Entry/Broker fail closed | code contracts, report/replay/CLI fields and forbidden-authority audit | PASS |
| Full repository gate on final HEAD | exact-HEAD handoff record | PENDING_FINAL_GATE |

## 4. Explicit evidence ceiling

This evidence is based on engineering fixtures and a local isolated PostgreSQL
instance. It does not establish production scheduling, sustained operation,
formal PIT, Provider qualification, calibrated probabilities, economic value,
Shadow readiness, authenticated operators, Entry authority, Opportunity/Order,
real Fill, Position mutation or Broker authority.

`DailyDecisionWindowSummary`, stateful Market/Theme/Capital, Dynamic Stock
Pool, Daily Summary, Manual Account/Reconciliation, Model Registry Selector,
economic validation and Shadow Runtime remain not delivered.
