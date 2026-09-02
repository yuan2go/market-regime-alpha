# WP-14 Formal Research Engineering Readiness Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP14_EXIT_GATE_PASS`
> **Authority:** Immutable exact-SHA local engineering Verification; not Formal PIT, Formal OOS, Provider qualification, Prospective value, Alpha, Runtime/CLI Cutover, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **WP-13 Verified Implementation:** `fc5993e5d9e05dbe2845659140108e1051cf3704`
> **WP-13 Merged Main:** `eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Implementation Checkpoint:** `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`

```text
WP13 = MERGED / EXIT_GATE_PASS
WP14 = IMPLEMENTED_AND_QUALIFIED
WP14_EXIT_GATE = PASS
FORMAL_RESEARCH_ENGINEERING_READY = true
FORMAL_PIT = NOT_PROVEN
FORMAL_OOS = NOT_PROVEN
PROSPECTIVE_PROVEN = NO
PROVIDER_QUALIFIED = NO
ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover = NO-GO
```

This Verification proves only the engineering mechanics required to launch a
future recorded-provider campaign. Fixtures and local test campaigns cannot
promote any empirical claim.

## 1. Dependency preflight, branch, and identities

WP-13 was qualified, merged through PR #96, fetched again, and rechecked before
the independent WP-14 branch and linked worktree were created. The merged main
contains the immutable WP-13 Verification and its exact implementation as an
ancestor. The pre-existing `.idea/modules.xml` change in the primary checkout
was never modified, staged, stashed, or committed.

```text
remote                         git@github.com:yuan2go/market-regime-alpha.git
origin/main baseline           eb7970b4833228a2faba6715c65c26dae88f6ee5
branch                         agent/wp-14-formal-research-readiness
worktree                       isolated linked worktree wp-14-formal-research-readiness
implementation                 ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8
root tree                      c1198fa61e432d46a416e863d32a7b253abdf67e
source tree                    ccc42e2a732f0738c560d762ce3c61a1418c475e
tests tree                     4a2148ff361c057db68d4ee3e758266246b010dd
Research Qualification tree   453e0f4f81d62a27ebd1e8237fae1627901c95b8
Market tree                    d0efafaa99e7cc575b619f1a3791112e432bb5f0
Runtime tree                   b01c45b9ca7009fe8ddc9cba227f2f656473c6c1
PostgreSQL tree                9bd9e87be8b4eab3173b69b685147a757e03e909
WP-14 test tree                8eb4cf6a37d51c9d31635ac37f15b4faebb881dc
baseline blob                  2b4f587da1f616ef6b0eeaf15621cbe1c116be50
baseline SHA-256               df75c594bba25ab293723af615fcdad8f5b64781fddaf716f6fe586fffc8bc85
source diff SHA-256            564815f6756e21cd6a53dd6d0b06bf072425c1b0321d795e73db292a662f8030
test diff SHA-256              c474ae54c80e9a221b3b3ab780b68c92f433745ac8edef48de3237ed05067eec
schema diff SHA-256            cc495ee5c6804cac3cb11564312ba34ac91d494ab2bfa22393319fa3c35fc69b
```

Dependency-coherent checkpoints are:

```text
9fae2d2  clean stale WP-14 planning authority
f3e5ba3  freeze canonical WP-14 engineering design
f401bb2  freeze detailed WP-14 implementation plan
d038b6e  define controlled proof Runtime profiles
08093e6  establish Provider qualification mechanics
ca6f66b  close formal campaign, PIT, Dataset, composition, and verification
```

Historical immutable Verification files were read only.

## 2. Controlled proof Runtime and composition

The existing Runtime remains the only Runtime owner. WP-14 adds exact,
mandatory, ordered profiles for:

```text
CAPTURE → NORMALIZE_PIT → FREEZE_UNIVERSE → ASSESS_ELIGIBILITY
→ REGISTER_DATASET → BUILD_CANDIDATE_SET → OPEN_DECISION_RUN
→ ASSESS_CONTEXT → SIGNAL_AND_FORECAST → DECIDE_AND_RISK

SETTLE_OUTCOME → ACQUIRE_OUTCOME_INPUTS → EVALUATE
→ RECORD_EVIDENCE → ASSESS_RESEARCH → QUALIFY
```

The database rejects missing, reordered, optional, partial-edge, or bypassed
profiles. A materialized campaign binds exact Decision Proof and Due Proof
Runtime Run FKs. The sole target composition root exposes the narrow Provider
qualification commands/query, Formal Campaign commands/query, and Formal PIT
read port. No second Runtime, Runtime business dispatcher, or CLI cutover was
added.

## 3. Formal campaign predeclaration and protected opening

`FormalResearchCampaignDefinition` freezes exact Target, one transparent
hypothesis and primary change, Provider Product/protocol, Candidate, Context,
Strategy, Portfolio, Risk and Qualification policies, complete FIT,
VALIDATION, and LOCKED_OOS partition plans, complete purpose-bound Evaluation
Protocols, Decimal cost assumptions, code/config Artifacts, and provenance.
All ordered child rosters are inserted before the immutable root; deferred
database reconciliation proves contiguous counts and deterministic hashes.

Actual Research Partitions remain database-derived. Campaign binding reloads
the entire declared roster and exact purpose/Target/calendar identities.
Experiment registration remains atomic and binds the same complete ordered
roster. `open_protected` concrete-FKs one Experiment Run and Evaluation Run,
uses PostgreSQL authoritative time, and proves zero Outcome access before the
LOCKED_OOS or PROSPECTIVE opening. Late Provider rebinding and changed replay
fail closed. Any frozen baseline change requires a new campaign revision and
new Experiment generation.

## 4. Provider qualification and Formal PIT boundary

Market owns immutable Provider Qualification Protocol, ten typed requirements,
Finality Observations, Decision, Capture roster, and complete Requirement
Results. Protocol scope freezes Provider Product, purpose, market/instrument,
exchange, timeframe, price basis, DecisionTime rule, evidence window/cutoff,
Outcome path sessions, code/config, and provenance. Decision status is derived
from recorded owner facts; caller assertions such as `pit_correct=true` are not
accepted.

`ENGINEERING_REHEARSAL` is database-forbidden from producing `ADMITTED` or any
qualified visibility. Only a future `RECORDED_PROVIDER + ADMITTED +
HISTORICAL_PIT` decision may create source-specific visibility rows. The Formal
PIT resolver requires exact Campaign, bound Provider Decision, typed source
kind/identity, and requested DecisionTime. It performs no current/latest read,
Provider call, or reconstruction. Formal Dataset registration concrete-FKs the
campaign/decision and a complete qualified-source roster. Ordinary Dataset
registration remains unchanged.

## 5. Prospective and due mechanics

The Due Proof Runtime profile uses the database clock and existing Outcome,
Evaluation, Evidence, Assessment, and Qualification commands. Read-only due
discovery returns explicit `NOT_DUE`, `DUE`, `MISSING`, or `SETTLED` for every
PROSPECTIVE member; missing facts are not dropped. Existing Outcome and WP-11
qualification campaigns prove due settlement atomicity, concurrent one-writer
replay, correction-vs-acquisition snapshot safety, global access ordinals,
Acquire/Fail races, stale fences, unknown commits, and rollback of partial
rosters.

The WP-14 historical fixture remains rejected even when its Runtime mode is
`SHADOW`, because `commitment_recorded_at < earliest_outcome_event` is false.
No synthetic future time or fixture is presented as prospective evidence.

## 6. Inspection, reconciliation, and architecture

Read-only campaign inspection reports campaign/provider state, planned and
bound partitions, first access, open/terminal Evaluation counts, due/missing/
settled Outcome counts, Evidence, Assessment, Qualification, and explicit
blockers. It is not Authority.

Independent read-only verifiers recompute Provider Protocol and Decision
rosters, finality chains, qualified visibility hashes, campaign plan/evaluation/
cost rosters, actual Partition and Experiment bindings, protected opening and
zero-access ordering, Runtime DAGs, global Outcome access ordinals, exact
Outcome revisions, Evaluation/Evidence/Assessment/Qualification closure, and
receipt/audit/Runtime provenance. A clean materialized chain returns:

```text
matched = true
mismatch_count = 0
```

Domain/Application own typed ports; Infrastructure implements PostgreSQL
adapters. Provider, network, and filesystem I/O remain outside short business
transactions. Narrow Provider Qualification and Formal Campaign UoWs preserve
fence-first locking, exact idempotency, bounded retry, deterministic failure,
and unknown-commit exact probe/replay. No God UoW, generic registry/repository,
JSON business owner, Legacy dependency, compatibility writer, dual write,
nullable future FK, Model, Calibration, or Execution placeholder was added.

## 7. Concurrency, failure, and recovery

Real PostgreSQL tests prove:

- identical Provider Protocol/Decision and Campaign predeclarations converge
  to one Authority; changed idempotency reuse fails closed;
- Campaign partition binding and protected opening races produce one writer
  plus exact replay, never a partial roster or duplicate opening;
- Provider and Campaign unknown-commit results succeed only after an exact
  owner receipt/aggregate probe finds committed Authority;
- stale fences write no Campaign business row, receipt, audit, or failure fact;
- injected root/child failures roll back Provider results and Campaign roots/
  rosters before exact recovery;
- existing Outcome tests prove concurrent due settlement, correction chain
  non-forking, mid-write rollback, failure-recorder recovery, and stale-fence
  zero writes;
- existing WP-11/WP-12 tests prove first-access, Acquire/Fail, terminal races,
  metric Cartesian completeness, Evidence/Assessment/Qualification races, and
  exact recovery/reconciliation.

No partial Campaign, Provider roster, access ledger, Evaluation observation,
metric input, Evidence, Assessment, or Qualification Authority survives a
failed transaction.

## 8. PostgreSQL catalog and reproducible recreate

The final explicitly disposable PostgreSQL 16.14 database was bootstrapped,
verified, recreated through an exact database-name/OID/owner/zero-client
authorization, and verified again.

```text
database             mra_wp14_qual
database OID         454219883 before and after guarded recreate
PostgreSQL           16.14 Homebrew arm64
recreate plan hash   b27d1673d16c13bb29ba1c4c8f4a46553a846d3a2fff0c0e3562fd737c30db32
challenge            5db2ed8f8c2d3d8fd64451e7
operator             wp14-final-verification
backup attestation   DISPOSABLE_DATABASE_NO_USER_DATA
unexpected objects   []
active clients       []
```

The final catalog contains:

```text
tables                    129
views                       4
indexes                   963
constraints             1,349
functions                 105
non-internal triggers     268
catalog objects         2,819
```

| Artifact | SHA-256 |
|---|---|
| baseline | `df75c594bba25ab293723af615fcdad8f5b64781fddaf716f6fe586fffc8bc85` |
| seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| catalog | `1d58cbace3120fb0c7048900bb5e162df8dfc40c2b4a26337b2e562093f03714` |
| reference vocabulary | `52fd044a72334fe7334bacd7f5ef96cff72244f3f89fab1c48bcfa4ee095d0a6` |

The four checksums were identical before and after guarded recreate. WP-14
extends only unreleased `001_baseline.sql`; no `002+` migration exists.

## 9. Representative database plans

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` ran against a complete materialized
WP-14 vertical chain:

| Query | Execution | Leading indexes / bounded observation |
|---|---:|---|
| Provider requirement roster | 0.029 ms | protocol requirement index; 10 rows |
| Campaign Partition roster | 0.018 ms | campaign/purpose index; tiny 3-row Partition scan |
| qualified fact cutoff | 0.005 ms | decision/cutoff index; zero visibility rows |
| prospective due discovery | 0.067 ms | campaign purpose, member calendar, Outcome root/revision indexes |
| first-access guard | 0.027 ms | campaign purpose and member/ordinal indexes; tiny 3-row member scan |
| Campaign roster reconciliation | 0.019 ms | exact Campaign/plan indexes; 3 rows |

All shared reads were cache hits and `shared_read_blocks = 0`. The two Seq
Scans were optimizer choices over three-row fixture tables. No unbounded join,
missing FK-leading index, disk amplification, or lock-amplification blocker was
found. Optimizer node shape is intentionally not fixed.

## 10. Engineering validation ledger

Environment:

```text
OS          macOS 26.5.2 arm64
Python      3.12.2
PostgreSQL  16.14 Homebrew arm64
timezone    Asia/Shanghai
```

All passing gates ran against exact implementation
`ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8` in a clean worktree.

| Command / check | Result | Evidence |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | **PASS** | 61 locked packages checked |
| `pytest -q tests/refoundation/formal_research` | **PASS** | 19/19 |
| `pytest -q tests/refoundation` | **PASS** | 604/604 |
| `pytest -q tests/platform` | **PASS** | 33/33 |
| `pytest -q tests/persistence/postgres` | **PASS** | 286/286 |
| `pytest -q` | **PASS** | 3,644/3,644 repository nodes |
| `ruff check .` | **PASS** | all checks passed |
| `python -m mypy` | **PASS** | no issues in 566 source files |
| `python -m build` | **PASS** | wheel and sdist built |
| `python scripts/check_docs_links.py` | **PASS** | canonical inventory, metadata, and links OK |
| `pytest -q tests/scripts/test_check_docs_links.py` | **PASS** | 7/7 |
| architecture/import/schema specification suite | **PASS** | 64/64 |
| clean bootstrap + verify + guarded recreate + verify | **PASS** | exact OID, 129 tables, stable checksums |
| concurrency/failure/recovery/replay/verifier campaign | **PASS** | focused/refoundation/PostgreSQL suites |
| six representative plans | **PASS** | all bounded; no blocker |
| `git diff --check` and clean implementation status | **PASS** | no whitespace or implementation drift |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | read-only response `enabled=false`; remote CI is not reported PASS |

Build artifacts:

```text
wheel  caa8f4eca9978d1d74544fb555f400988803329c03d01da0bf0e2e934711061a
sdist  8f84b7e03885e01e46eec011eb287c01e589ff47c5f58fa54054a4fc33cc81e4
```

Qualification hygiene: an initial platform/PostgreSQL command used the invalid
hostless URL `postgresql:///mra_wp14_qual` and failed configuration validation;
that disposable database was destroyed and freshly bootstrapped before the
valid TCP commands above ran serially. Two initial plan-harness attempts used
incorrect reporting column names and failed before EXPLAIN; each `finally`
removed its schema, and the corrected harness produced the recorded plans.
Those failed operator commands are not reported as product PASS evidence.

No final test was skipped, xfailed, deleted, reordered, or weakened. Build
output was removed after hashing; the implementation worktree remained clean.

## 11. Exit decision and evidence ceiling

All WP-14 P0/P1 implementation, composition, PostgreSQL, concurrency,
failure/recovery, replay/reconciliation, plans, full regression, static, build,
documentation, architecture, and clean-tree gates passed at the exact
implementation SHA. Therefore:

```text
WP14 = IMPLEMENTED_AND_QUALIFIED
WP14_EXIT_GATE = PASS
FORMAL_RESEARCH_ENGINEERING_READY = true
```

The evidence ceiling remains:

```text
target_release_state = DRAFT
runtime_dispatch_cut_over = false
business_cli_cut_over = false
provider_qualification_established = false
formal_pit_established = false
formal_oos_established = false
prospective_campaign_started = false
prospective_value_proven = false
alpha_proven = false
model_or_calibration_implemented = false
execution_or_broker_authority = false
production_ready = false
```

WP-15 may start only after this branch is pushed, reviewed, merged, latest
`origin/main` is fetched again, and merged main is proved to contain this
immutable Verification and exact implementation checkpoint. WP-15 must use a
new branch/worktree and real recorded Provider evidence. If that external gate
cannot prove known-time/finality/coverage, the campaign must stop as
`BLOCKED_BY_EXTERNAL_EVIDENCE`; synthetic replacement is forbidden.
