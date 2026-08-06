# WP-STATE-01 Acceptance Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Local implementation and pre-final verification record
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../roadmap/work-packages/WP-STATE-01-Stateful-Research-System.md, ../runbooks/Stateful-Research-Runtime.md, ../audit/WP-CRR-01-Final-Review.md

## 1. Implementation checkpoints

| Checkpoint | Scope |
| --- | --- |
| `a9d2d08` | versioned State lineage, thresholds and configuration contracts |
| `b4a0423` | Stateful Market Regime and V0 comparison |
| `97db26e` | separate ETF and Theme Rotation lifecycle states |
| `ab22a40` | observable-proxy Capital State |
| `0370c8d` | immutable Dynamic Pool plus PostgreSQL/SQLite repositories and migration 022 |
| `f944bda` | Pool/State-bound Candidate, Signal V4 and Forecast V2 |
| `853640c` | ordered Continuous child, migration 023, recovery/fencing and authority guards |
| `59b9323` | fail-closed state corrections, lifecycle coverage and read-only inspection CLI |

## 2. Observed focused evidence before final repository gate

| Requirement | Evidence | Status |
| --- | --- | --- |
| Observation/State separation | distinct content-addressed contracts and persistence tables | PASS |
| deterministic replay | repeated inputs reproduce State, Transition, Pool and research identities | PASS |
| Market lifecycle | pulse, confirmation, dwell, hysteresis, counter evidence, all six states, late evidence | PASS |
| ETF lifecycle | pulse cannot lead; resonance/persistence, liquidity, divergence/weakening/failure/recovery | PASS |
| Theme lifecycle | many-to-many mapping, conflicts, incomplete mapping, independent lifecycle/replay | PASS |
| Capital semantics | four bias states, uncertainty/counter evidence; forbidden actor assertions absent | PASS |
| Dynamic Pool | full cross section, add/remove, materiality, no-change reuse, future-State rejection | PASS |
| PostgreSQL | migration 022, active fence, CAS pointer, concurrent identical create, append-only history | PASS |
| SQLite | explicit compatibility, restart recovery, immutable history and content-validating Reader | PASS |
| Runtime | nine ordered stages, durable receipt lookup/reuse, stale-fence rejection | PASS |
| Candidate | exact Pool and State binding; complete cross section required | PASS |
| Signal | new writer uses `factor_coverage`; legacy `confidence` Reader remains compatible | PASS |
| Forecast | empirical, `NOT_CALIBRATED`, probability-free, unavailable samples fail closed | PASS |
| Authority | AST guard finds no Summary/Opportunity/Order/Fill/Position/Broker call path | PASS |
| Inspection CLI | ordered ownership description and tamper-rejecting Pool Reader | PASS |

The focused post-correction State collection passed 52 tests. Configured mypy
covered 371 source files. Exact final repository-wide commands and final local
SHA are reported in the engineering handoff after the last documentation
checkpoint; this document does not pre-claim their result.

## 3. PostgreSQL schema

Migrations 001 through 023 apply from an empty database. Migration 022 adds 17
tables. It also upgrades a schema already at migration 020. All domain business
values are inserted by audited Python services. Triggers reject mutation and
pointer regression; they do not create a proposed/effective State.

The State and Pool repositories verify the parent Tick's Claim ID, unexpired
Lease, fencing token and Tick version in the final transaction. Tests observe a
fresh worker taking `stale fence + 1`, concurrent identical Pool appends
converging on one row, and stale receipt publication failing after computation.

## 4. Time and compatibility

- `AvailableAt > AsOfTime` fails closed at Evidence, State stage, Pool,
  Candidate, Signal and Forecast boundaries.
- Late evidence produces a new immutable version.
- Decision-window tests reject a complete daily close bar.
- historical fixed-14:55 Target, TargetId, Reader and Replay code is unchanged;
  the final regression gate covers those existing tests.
- V0 snapshot models and historical Readers are preserved.

## 5. Evidence levels

| Module | Code | Fixture | Replay | PostgreSQL integration | Free live data | PIT-aware | Formal PIT | OOS | Shadow | Production |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Continuous Runtime | yes | yes | yes | yes | blocked | yes | no | no | no | no |
| Market State | yes | yes | yes | yes | no | yes | no | no | no | no |
| ETF Rotation | yes | yes | yes | yes | no | yes | no | no | no | no |
| Theme Rotation | yes | yes | yes | yes | no | yes | no | no | no | no |
| Capital State | yes | yes | yes | yes | no | yes | no | no | no | no |
| Dynamic Pool | yes | yes | yes | yes | no | yes | no | no | no | no |
| Candidate binding | yes | yes | yes | receipt lineage | no | yes | no | no | no | no |
| Signal V4 | yes | yes | yes | receipt lineage | no | yes | no | no | no | no |
| Forecast V2 | yes | yes | yes | receipt lineage | no | yes | no | no | no | no |

“PIT-aware” means time/availability contracts reject future data. It is not
formal Provider PIT evidence. The live Tencent smoke attempt was
`EXTERNAL_PROVIDER_BLOCKED` by a TLS handshake timeout before valid Evidence;
no Fixture is counted as live data.

## 6. Explicitly undelivered

Daily Decision Summary, Manual Account, Reconciliation, complete Registry
Selector, economic validation, Shadow Runtime, formal PIT, formal OOS, Portfolio/
Risk integration, Holding/Exit scheduling, pages and Broker integration remain
undelivered. Entry remains fail closed.
