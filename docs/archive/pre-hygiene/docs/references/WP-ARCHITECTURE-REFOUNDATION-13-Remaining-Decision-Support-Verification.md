# WP-13 Remaining Decision Support Closure Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP13_EXIT_GATE_PASS`
> **Authority:** Immutable exact-SHA local engineering Verification; not Runtime/CLI Cutover, Formal PIT/OOS/Prospective evidence, Provider qualification, Alpha value, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **WP-12 Verified Implementation:** `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **WP-12 Merged Main:** `6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **Implementation Checkpoint:** `fc5993e5d9e05dbe2845659140108e1051cf3704`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`

```text
WP12 = MERGED / EXIT_GATE_PASS
WP13 = IMPLEMENTED_AND_QUALIFIED
WP13_EXIT_GATE = PASS
Runtime dispatch / CLI Cutover = NO-GO
Formal PIT / Locked OOS / Prospective = NOT_PROVEN
Provider qualification / Alpha / Production = NOT_PROVEN
```

This Verification covers only:

```text
ResearchQualification(n)
→ DecisionRun qualification roster(n+1)
→ PIT Context + immutable Strategy
→ Signal → rule-based Forecast → Opportunity → Thesis
→ complete Portfolio Proposal → Decision-Support-only Risk
```

It does not implement or qualify a Model, empirical research campaign,
Execution, Account, broker, order, Fill, Position mutation, or target Runtime
dispatch.

## 1. Dependency preflight, branch, and identities

WP-12 was qualified, merged through PR #95, fetched again, and rechecked before
the independent WP-13 branch and linked worktree were created. Execution-time
main contains the immutable WP-12 Verification and its verified implementation
as an ancestor. The pre-existing `.idea/modules.xml` modification in the
primary checkout was not modified, staged, stashed, or committed.

```text
remote                 git@github.com:yuan2go/market-regime-alpha.git
origin/main baseline   6e0ad150057e43a89843eb4fb307e0373d5572ac
branch                 agent/wp-13-remaining-decision-support-closure
worktree               isolated linked worktree wp-13-remaining-decision-support-closure
implementation         fc5993e5d9e05dbe2845659140108e1051cf3704
root tree              a6e6286ff15cc46e75ece116763e6c35d014f4fd
source tree            03b785fa3ff39040e15e068228ad37ce50a33dbc
tests tree             4a09d6ef845f4c38d8e34f36564b3d3b408595d4
Decision Support tree  c1ba668614144b6bc0ed8f29adfd1996d506d0a1
Research tree          94b0c082a8db37ba3e1734834aa4154e3df3fff0
PostgreSQL tree        0056682f948349c70ef1660d03c99679b9b6ccfc
WP-13 test tree        23910f12ae38b6d69f393611e3d86c8eb05f490e
baseline blob          047e5d1271958a5dcd2b3a4ec776d0fbe4929d5d
baseline SHA-256       94fe2bdca092c979c50bc9228a7a316f2229d17b6527e54c5adeb21873bd34f8
source diff SHA-256    ec4cef20bb83b529d0744556e3a1f2c8f0ee71dfeb5e95eed37c337191ed48c2
test diff SHA-256      0a7b22e8bd00af0f79b5a45eb0ca857a0d23cd1c69ee77374fda91f33242b67c
schema diff SHA-256    be6e9ce4a9ea8344a8b6c8af69d744bf5fd59e6fa08e836bf91bf34f05e67f08
```

Dependency-coherent checkpoints are:

```text
c4d0420  open WP-13 after the merged WP-12 preflight
2aac234  freeze canonical WP-13 design
d5320e1  freeze detailed implementation and qualification plan
e1216b2  freeze DecisionRun qualification roster
362636c  close PIT Context authority
b3c3224  freeze Strategy and inference authorities
08eff56  represent empty inference rosters explicitly
3689274  compose exact Strategy Signal and Forecast commands
2a3fc63  define Opportunity, Portfolio, and Risk closure
29efebb  close Decision Support Portfolio and Risk
2d9cf07  close Decision Authority races and failures
0733dda  advance prior Authority boundaries through WP-13
fc5993e  qualify Decision closure recovery and plans
```

Historical immutable Verification files were read only.

## 2. Later-generation Qualification and DecisionRun closure

Every DecisionRun atomically freezes exactly one explicit zero-or-more
qualification roster plus contiguous member rows, count, and deterministic
hash. Members concrete-FK exact `ADMITTED` Research Qualification Decisions
whose purpose matches, effective and known times do not exceed DecisionTime,
source Outcome generation is strictly older, and no successor is effective and
known at that DecisionTime. Empty means an explicit zero roster, not an absent
or unknown input. No current/latest or caller-asserted qualification path
exists. Root/child reconciliation, exact replay, changed roster rejection, and
the existing Candidate × Target commitment closure remain intact.

## 3. PIT Context, Strategy, Signal, and Forecast

Context policies relationally freeze typed Market Regime, ETF rotation, Theme
rotation, and Capital/Breadth metrics. Assessments bind exact DecisionRun and
Candidate scope plus complete Decision-visible Market bar, fact,
classification, session, or SourceGap lineage with known-time and explicit
availability/missingness. They accept no Outcome port and read no future label.

Immutable Strategy Versions freeze the primary change, action mapping,
Context requirements, one Signal rule, complete Target/checkpoint/metric
Forecast rules, Decimal coefficients, code/config Artifacts, and provenance.
One inference transaction writes explicit Signal and Forecast run roots even
for empty Candidate rosters, then complete candidate/context and
forecast/estimate rosters. `NO_SIGNAL`, `WAIT`, `UNKNOWN`, and
`NOT_ESTIMABLE` remain facts. Forecast is rule-based, Target/commitment-bound,
and explicitly `UNCALIBRATED`; no Model or nullable model binding exists.

## 4. Opportunity, Thesis, Portfolio, and Risk closure

Opportunity derives the complete Forecast roster and binds every exact Signal,
Context, Strategy, Candidate, commitment, Target, and forecast fact. Typed
Thesis conditions are immutable, independently observable/falsifiable, and
append-only by revision. A Portfolio Proposal covers the complete Opportunity
set with one relational line per member, explicit included/excluded/not-
estimable status, Decimal weights, and deterministic count/hash reconciliation.

Risk is evaluated only after the complete Proposal. One result exists for
every required global rule or rule × PortfolioLine Cartesian input. Missing,
failed, rejected, unknown, and no-action results cannot be omitted. Scope is
constant `DECISION_SUPPORT_ONLY`; no result writes Account, Intent, Order,
Fill, Position, broker, or trading Authority.

## 5. Composition and architecture boundaries

The sole target `bootstrap_application` constructs Decision, Context,
Strategy, Inference, Opportunity, Portfolio, Risk, and read-only verification
seams. Domain/Application declare typed narrow ports and do not import concrete
PostgreSQL adapters. Independent Decision, Context, Strategy, Inference,
Opportunity, Portfolio, and Risk UoWs remain narrow; no God UoW, generic
repository/registry, service locator, JSON business owner, Legacy dependency,
compatibility facade, or dual write was introduced.

Runtime dispatch and business CLI cutover deliberately remain absent. Provider,
network, and filesystem I/O occur outside business transactions. PostgreSQL
authoritative time, fence-first transaction locking, deterministic root/child
lock order, exact receipts, audit, bounded retry, and exact unknown-commit
probe/replay preserve the existing global transaction contract.

## 6. Concurrency, failure, recovery, and replay

Real PostgreSQL campaigns prove:

- identical Opportunity, Portfolio, and Risk commands produce one canonical
  writer and one exact replay;
- changed Opportunity requests racing for one identity produce one Authority
  and one fail-closed conflict, never a fork;
- a stale Runtime fence writes no Opportunity, receipt, audit, or failure fact;
- injected failures on the second Opportunity Context, first Portfolio Line,
  and second Risk Reason roll back every new root and child before one exact
  failed receipt/audit/Runtime terminal fact is recorded;
- no partial Opportunity, Portfolio, or Risk Cartesian roster survives;
- an unknown commit result returns only after the exact owner query finds the
  committed Authority; absence does not become a blind success;
- the inherited Runtime/PostgreSQL suites continue to cover real
  serialization failure, deadlock, transient connection loss,
  failure-recorder rollback/recovery, stale fencing, and receipt races.

The read-only verifier recomputes Decision Target/commitment/reference and
Qualification rosters, Context roots/metrics/sources, Strategy rules, Signal
and Forecast roots/children, Opportunity Contexts, Portfolio Lines, Risk
rule-line Cartesian reasons, receipt/audit/fence provenance, counts, ordinals,
and hashes. A clean completed chain returns:

```text
matched = true
mismatch_count = 0
```

It performs no Provider call, unrestricted current/latest lookup, Outcome
read, bars-to-label calculation, or mutation.

## 7. PostgreSQL catalog and reproducible recreate

The final disposable PostgreSQL 16.14 database was created only for this
qualification. The test suites removed their isolated schema; the final run
then proved a fresh bootstrap again before the final guarded recreate.

```text
database             mra_wp13_final_fc5993e
database OID         12209451 before and after guarded recreate
PostgreSQL           16.14 Homebrew arm64
port                 55433
artifact root        /tmp/mra-wp13-final-fc5993e-artifacts
recreate plan        /tmp/mra-wp13-final-fc5993e-recreate-plan-post-suite.json
plan hash            f9fe788d7a358d65979f9b8a56d0a9012a44cc41662b3b1fbd324996dae01e46
plan file SHA-256    bb9b4f8a18425eb10c22c0ac071710bcebc7a3d48e2584475eb4244b0e694e22
challenge            d7c2c58dd8c329055d85f075
operator             codex-wp13
backup attestation   DISPOSABLE_DATABASE_NO_USER_DATA
unexpected objects   []
```

The final target catalog contains:

```text
tables                    108
views                       4
indexes                   845
constraints             1,196
functions                  89
non-internal triggers     224
catalog objects         2,467
```

Checksums are:

| Artifact | SHA-256 |
|---|---|
| baseline | `94fe2bdca092c979c50bc9228a7a316f2229d17b6527e54c5adeb21873bd34f8` |
| seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| catalog | `d47fb0bc99fcec99a92e1f8353e528e4e1cd4b9eb350b609260d35f11209e60d` |
| reference vocabulary | `f5ab9cc4fe7617dd0bc5de171365e877eddadc9f6158f3fa0eb83f634c03e701` |

Clean bootstrap, verify, guarded exact-name/OID/owner/zero-client recreate, and
post-recreate verify all passed. OID, counts, checksums, and empty unexpected-
object set remained stable. Only unreleased `001_baseline.sql` changed; no
`002+` migration was created.

## 8. Representative database plans

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` executed against the real vertical
chain for:

```text
DecisionRun → PIT Context assessments
Signal → exact Context bindings
Forecast → exact Estimate roster
Opportunity → complete Context roster
Portfolio Proposal → complete Line roster
Risk Decision → complete Reason Cartesian roster
```

The specification accepts equivalent PK/composite-unique/FK-leading indexes
without fixing optimizer node shape. Every path used a bounded leading index;
no missing FK-leading index, unbounded join explosion, or lock-amplification
blocker was found.

## 9. Engineering validation ledger

Environment:

```text
OS          macOS 26.5.2 arm64
Python      3.12.2
PostgreSQL  16.14 Homebrew arm64
timezone    Asia/Shanghai
```

All commands below ran against exact implementation
`fc5993e5d9e05dbe2845659140108e1051cf3704` in a clean worktree.

| Command / check | Result | Evidence |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | **PASS** | 61 locked packages checked |
| WP-13 focused suite | **PASS** | 51/51 |
| `pytest -q tests/refoundation` | **PASS** | 585/585 |
| `pytest -q tests/platform` | **PASS** | 33/33 |
| `pytest -q tests/persistence/postgres` | **PASS** | 286/286 |
| `pytest -q` | **PASS** | 3,625/3,625 repository nodes |
| `ruff check .` | **PASS** | all checks passed |
| `python -m mypy` | **PASS** | no issues in 554 source files |
| `python -m build --outdir /tmp/mra-wp13-final-fc5993e-build.CIrioU` | **PASS** | wheel and sdist built |
| `python scripts/check_docs_links.py` | **PASS** | canonical inventory, metadata, and links OK |
| `pytest -q tests/scripts/test_check_docs_links.py` | **PASS** | 7/7 |
| architecture/import suite | **PASS** | 68/68 |
| clean `mra db bootstrap` + `mra db verify` | **PASS** | exact 108-table catalog/checksums |
| guarded `recreate-plan` + `recreate-apply` + verify | **PASS** | exact OID, no unexpected objects, stable checksums |
| concurrency/failure/recovery/replay/verifier campaign | **PASS** | included in focused/refoundation/PostgreSQL suites |
| six representative plan specifications | **PASS** | included in focused/full tests |
| `git diff --check` and clean implementation status | **PASS** | no whitespace or uncommitted implementation change |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | read-only result `enabled=false`; remote CI is not reported PASS |

Build artifacts:

```text
wheel  365c6068a07d99940133f3f949a41ad51d5947481bd53d2e3b32537436633961
sdist  bbf8ecfcc74779f80efa8b37ed27dc5c28c533df4d436c995c46d5f387b955ca
```

No final test was skipped, xfailed, deleted, reordered, or weakened to obtain
this result. The plan assertions deliberately allow equivalent bounded index
choices, as required; they do not force optimizer node shapes.

## 10. Exit decision and evidence ceiling

All WP-13 P0/P1 implementation, composition, PostgreSQL, concurrency,
failure/recovery, replay/reconciliation, plan, regression, static, build,
documentation, architecture, and clean-tree gates passed at the exact
implementation SHA. Therefore:

```text
WP13 = IMPLEMENTED_AND_QUALIFIED
WP13_EXIT_GATE = PASS
```

The evidence ceiling remains:

```text
target_release_state = DRAFT
runtime_dispatch_cut_over = false
business_cli_cut_over = false
provider_qualification_established = false
formal_pit_established = false
locked_oos_evidence_established = false
prospective_value_proven = false
alpha_proven = false
model_or_calibration_implemented = false
execution_or_broker_authority = false
production_ready = false
```

This Verification proves deterministic Decision Support engineering closure,
not empirical value. Test/fixture data cannot qualify a Provider or research
hypothesis. WP-14 may begin only after this branch is pushed, reviewed, merged,
latest `origin/main` is fetched again, and merged main is proved to contain
this immutable Verification and exact implementation checkpoint. It must use a
new branch and worktree.
