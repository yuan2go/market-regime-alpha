# WP-11 Research Validity and Evaluation Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP11_EXIT_GATE_PASS`
> **Authority:** Immutable exact-SHA local engineering Verification; not Research Evidence, Assessment, Qualification, Model, Forecast, Runtime/CLI Cutover, Formal OOS/Prospective promotion, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** `2026-09-02 (Asia/Shanghai)`
> **Execution-Time Origin Main:** `origin/main@d7f41a30f1917fc3b266bdeebbc157021c3cc352`
> **Implementation Checkpoint:** `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`

```text
WP11Q = ENGINEERING_QUALIFIED
WP11_EXIT_GATE = PASS
Runtime/CLI Cutover = NO-GO
Formal OOS/Prospective = NO-GO
Production = NO-GO
```

This Verification covers the integrated WP-11 chain only:

```text
REGISTERED Target
→ Outcome-compatible contract
→ frozen ResearchPartition
→ predeclared multi-Partition Experiment
→ predeclared EvaluationProtocol
→ EvaluationRun
→ controlled exact first Outcome access
→ complete EvaluationObservation roster
→ complete EvaluationMetric × member roster
```

WP-12 Evidence, Assessment, and Research Qualification remain absent and may
begin only after this branch is merged and the merged remote main is fetched
and rechecked.

## 1. Baseline, branch, worktree, and identities

Execution fetched the remote before starting and used an isolated linked
worktree. The pre-existing `.idea/modules.xml` change in the primary checkout
was not read as implementation evidence and was not modified, staged, stashed,
or committed.

```text
remote              git@github.com:yuan2go/market-regime-alpha.git
origin/main         d7f41a30f1917fc3b266bdeebbc157021c3cc352
branch              agent/wp-11q-research-validity-evaluation-qualification
worktree            /Users/yuan/projects/market-regime-alpha-worktrees/wp-11q-research-validity-evaluation-qualification
implementation      07151542f12a66d6e7da3e228e2dbf1d7d7771bb
root tree           688181c0edb24f8d8a98d6cb1540152bcfce4be9
source tree         09e629410fedf065a99a9b1b27cf9fee28fadbd9
tests tree          0b840065a4316742847849ccaf40d88fb0c0bf5b
baseline blob       07228e64040c97207f0146ea61c7b21689f45432
baseline SHA-256    6e63db66e69a50969d8fe5d6ca116454ead284427e54b04270673756e51936b1
source diff SHA-256 a31c1d0ac61b30dec01d04d12780fbee522b5a2a338961ba264e4507da0a9613
test diff SHA-256   3fed3e505a42632e90606e03a5fdf685e499322448d920df0a20e93f3e3d6a23
```

Dependency-coherent checkpoints are:

```text
e06acc3  docs cleanup and execution-time blocker record
289e15a  canonical WP-11Q qualification design freeze
81f075b  detailed implementation/qualification plan
41fcc05  sole target composition
71ca4ac  single-exchange Partition and complete Experiment roster closure
694b0c6  read-only WP-11 reconciliation
8b64300  concurrency and recovery campaign
0a91042  representative query-plan specification
2aab753  schema-generation boundary correction
e838734  Shanghai midnight-safe historical fixture
0715154  exact unknown-commit receipt replay proof
```

Historical immutable Verification files were read only.

## 2. Correctness closures

### 2.1 Canonical composition

The sole target `bootstrap_application(...)` now constructs and exposes:

```text
FreezeResearchPartition
RegisterExperiment
OpenExperimentRun
RegisterEvaluationProtocol
OpenEvaluationRun
AcquireOutcomeInputs
CompleteEvaluationRun
ResearchEvaluationVerifier
```

Ownership stays in `market_regime_alpha.research_qualification`, split into
three narrow Partition, Experiment, and Evaluation UoWs. `EvaluationRun` is
created and mutated only by the Evaluation UoW. No Runtime dispatch or CLI
cutover was added.

### 2.2 Target and Outcome parity

Target Domain, PostgreSQL root-last closure, and Outcome reconstruction agree
on at least one `REQUIRED` metric and all five exact dependency shapes:

| Metric | Dependency contract |
|---|---|
| `SIMPLE_RETURN` | exactly one `REFERENCE` and one `OBSERVATION` |
| `OBSERVATION_VALUE` | exactly one `OBSERVATION` |
| `MAX_FAVORABLE_EXCURSION` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |
| `MAX_ADVERSE_EXCURSION` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |
| `BARRIER_HIT` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |

WP-10 numerical semantics and revision lifecycle did not change.

### 2.3 One explicit exchange calendar per Partition

Each Partition freezes one non-null exchange and timezone, exact Decision
boundary sessions, protected boundary sessions, complete protected calendar
count/hash, Target Outcome horizon, purge/embargo, and member calendar facts.
Roster derivation joins each commitment through its concrete
DecisionReference Session and requires the declared exchange. A deliberately
divergent XSHG/XSHE fixture proves equal `session_date` cannot mix exchanges.

Protected ranges use ordered trading sessions, not calendar-day arithmetic.
Purpose-specific compatibility preserves diagnostic and rolling/walk-forward
reuse while serializing symmetric isolated overlap. `LOCKED_OOS` and
`PROSPECTIVE` remain isolated. Prospective membership rejects
`HISTORICAL`/`REPLAY`, applies canonical Runtime live-clock facts to any other
mode, and always requires commitment before the earliest Outcome event.

### 2.4 Complete Experiment Partition roster

One Experiment atomically freezes an ordered, non-empty roster of exact
Partition bindings. The root stores definition hash, binding count, binding
roster hash, and aggregate content hash. Child ordinals are contiguous;
duplicate binding/Partition identity, wrong Target/version/hash/purpose,
partial root/child closure, late binding, and changed replay fail closed.
`ExperimentRun` binds one concrete child while the Experiment may bind FIT,
VALIDATION, LOCKED_OOS, or other declared-purpose Partitions.

### 2.5 Evaluation and controlled access preservation

Gate B requires frozen Partition, registered Experiment, opened ExperimentRun,
frozen Protocol, `OPEN` EvaluationRun, and zero access. All Authority times use
PostgreSQL authoritative time and ordering is reinforced by concrete FKs,
state guards, same-transaction visibility guards, and locks.

`AcquireOutcomeInputs` remains one private short transaction. It resolves only
one exact revision visible at the requested cutoff, locks Outcome roots and
revisions before Partition/Evaluation, appends the globally monotonic
per-member access ordinal, writes one observation per member, reconciles the
complete roster, and only then commits `INPUTS_ACQUIRED`. No Outcome value can
escape before that commit. Research never calls current/latest, a Provider,
Market repository, bars-to-label, or Legacy.

`UNAVAILABLE` and `FAILED` stay in the sample; `NOT_DUE`, missing due Outcome,
ambiguous visible revision, or incomplete roster fails closed. Completion
writes every protocol metric and the full metric × observation Cartesian
roster with explicit included, excluded, or not-estimable state. Only complete
reconciliation permits `COMPLETED`.

## 3. PostgreSQL catalog and reproducibility

Only unreleased `MRA_REFOUNDATION_1/001_baseline.sql` was extended. No `002+`,
compatibility schema, dual write, generic registry, nullable future FK, JSON
business Authority, or WP-12 placeholder was created.

The verified PostgreSQL 16.14 catalog contains:

```text
tables                    68
views                      4
indexes                  534
constraints              822
functions                 55
non-internal triggers    141
catalog objects        1,625
```

Checksums are:

| Artifact | SHA-256 |
|---|---|
| baseline | `6e63db66e69a50969d8fe5d6ca116454ead284427e54b04270673756e51936b1` |
| seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| catalog | `ae08facaf68885a39a9c5a6a54c3a660e299f516cc415f891f2682d19995c14c` |
| reference vocabulary | `06d6c1f1b8a15c9ae83bc2f0124c003b3fe193f5a4ad5bdf09d3e8a1e3db0dcb` |

Final disposable database proof:

```text
database             mra_wp11q_final_20260902_0715154
database OID         447961286 before and after recreate
PostgreSQL           16.14 Homebrew arm64
schema               mra
Artifact root        /tmp/mra-wp11q-0715154-artifacts.50PTXU
recreate plan        /tmp/mra-wp11q-0715154-recreate-plan.json
plan hash            1d72a128badc18a324a6e1f18480119aeb60e14ca8c861487487745bf5d65f25
challenge            ddb183092558eab132575b4d
operator             codex-wp11q
backup attestation   DISPOSABLE_DATABASE_NO_USER_DATA
unexpected objects   []
```

Clean bootstrap, verify, guarded exact-name/OID recreate, and post-recreate
verify all passed. The OID and four checksums remained identical.

## 4. Concurrency, failure, recovery, and exact replay

Real PostgreSQL campaigns prove:

- concurrent identical Partition freeze produces one truth and exact replay;
- changed request fails closed; symmetric protected overlap has one winner;
- concurrent complete Experiment roster registration cannot fork or leave a
  partial binding roster;
- concurrent EvaluationRun open and first access preserve one run identity,
  one ordinal-one fact, and a globally monotonic ordinal chain;
- Outcome correction versus acquisition keeps the exact cutoff-visible
  snapshot; identical acquisition replays and changed acquisition rejects;
- Acquire versus Fail and Complete versus Fail produce one terminal truth,
  never a partial roster or double terminal state;
- stale Runtime fence produces zero business, receipt, audit, or failure rows;
- real SERIALIZABLE write skew produces one serialization loser; a real
  opposing lock order produces one deadlock loser; terminated backend
  connection loss is typed transient before commit;
- injected mid-Partition, mid-Experiment-child, mid-access/observation, and
  mid-metric-Cartesian failures leave no partial Authority and recover by exact
  replay;
- failure-recorder failure cannot resurrect rolled-back business rows;
- unknown commit is distinguished from known rollback. The final integration
  seam commits a real Partition transaction, loses only the acknowledgement,
  re-enters the exact command, probes the successful receipt, returns
  `replayed=true`, and proves exactly one Partition/member roster, receipt, and
  audit event.

Passing invariants are one canonical truth, no fork, no duplicate ordinal one,
no partial roster, no hidden Outcome access, and no double terminal state.

## 5. Read-only replay and reconciliation

`ResearchEvaluationVerifier` is a permanent narrow read-only Application port
implemented by PostgreSQL Infrastructure. It recomputes:

- Target/Outcome dependency parity and required metric presence;
- Partition exact calendar, bounds, protected roster, member/population roster,
  counts, hashes, content, and provenance;
- Experiment complete ordered binding roster, child/root hashes, Target,
  purpose, time ordering, and provenance;
- EvaluationProtocol metric count/order/hash and reducer/source/slice shape;
- EvaluationRun lifecycle and frozen parents;
- global per-member access ordinal chain and exact cutoff-visible revision;
- complete access and EvaluationObservation rosters;
- EvaluationMetric roster and completed MetricObservation Cartesian roster;
- receipt, audit, Runtime claim/fence, Artifact, and provenance facts.

It performs no Provider call, current/latest query, Market reconstruction,
bars-to-label computation, or mutation. The clean fixture returns:

```text
matched = true
mismatch_count = 0
```

A fault-injected immutable-row drift produces typed mismatches rather than a
false match.

## 6. Representative database plans

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` executed for:

```text
commitment → Partition roster
protected overlap
cutoff-visible Outcome revision
PartitionMember → global access ordinal
EvaluationObservation → exact OutcomeMetric
metric × member Cartesian reconciliation
```

The specification verifies relevant Target/FK/unique leading indexes, bounded
fixture rows, and execution below 100 ms without fixing optimizer node shape.
It found no Seq Scan/join explosion or lock-amplification blocker.

## 7. Engineering validation ledger

Environment:

```text
OS          macOS 26.5.2 arm64
uv          0.11.7
Python      3.12.2
PostgreSQL  16.14 Homebrew arm64
timezone    Asia/Shanghai
```

All final commands below ran against implementation
`07151542f12a66d6e7da3e228e2dbf1d7d7771bb` with a clean worktree.

| Command / check | Result | Evidence |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | **PASS** | 61 locked packages checked |
| `pytest -q tests/refoundation/research_qualification` | **PASS** | 163/163 |
| `pytest -q tests/refoundation` | **PASS** | 492/492 |
| `pytest -q tests/platform` | **PASS** | 33/33 |
| `pytest -q tests/persistence/postgres` | **PASS** | 286/286 |
| `pytest -q` | **PASS** | 3,532/3,532 repository nodes |
| `ruff check .` | **PASS** | all checks passed |
| `python -m mypy` | **PASS** | no issues in 528 source files |
| `python -m build --outdir /tmp/mra-wp11q-0715154-build.02NuHe` | **PASS** | wheel and sdist built |
| `python scripts/check_docs_links.py` | **PASS** | canonical inventory, metadata, links OK |
| `pytest -q tests/scripts/test_check_docs_links.py` | **PASS** | 7/7 |
| architecture/import suite | **PASS** | 69/69 |
| clean `mra db bootstrap` + `mra db verify` | **PASS** | exact 68-table catalog/checksums |
| guarded `recreate-plan` + `recreate-apply` + verify | **PASS** | exact OID, no unexpected objects, stable checksums |
| verifier/unknown-commit/query-plan focused rerun | **PASS** | 4/4 |
| `git diff --check` and clean status | **PASS** | no whitespace or uncommitted change |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | read-only result `enabled=false`; remote CI is not reported PASS |

Build artifacts:

```text
wheel  3a33f73b4e3ba5051f1c37cb13c0ad24aa58d325455a2fe4c7e4b59af47b01a9
sdist  8984aadf9f10418a3b01ed5d6106487412e978c0cdc34b0d0f50e8f11e904fa5
```

No test was skipped, filtered, xfailed, deleted, reordered, or weakened to
obtain the final gate.

## 8. Investigated non-final failures

No diagnostic failure is promoted to PASS:

| Attempt | Classification | Resolution |
|---|---|---|
| first `tests/refoundation` candidate run | **FAIL / CORRECTED** | five older generation tests still prohibited WP-11 relations; they now preserve exact WP-09/WP-10 rosters, require all WP-11 relations, and prohibit WP-12/later relations; full rerun passed |
| focused run crossing Shanghai midnight | **FAIL / CORRECTED** | historical Decision fixture was one day old but next-session 00:05 was briefly future; fixture now places both Decision and its horizon strictly in the past; the real Market clock guard was not weakened |
| first representative plan assertion | **FAIL / CORRECTED** | assertion fixed one optimizer index name; final test accepts only equivalent declared FK/unique leading indexes and does not freeze optimizer shape |
| first platform invocation | **FAIL / INVOCATION CORRECTED** | Unix-socket DSN omitted the host required by the legacy-shaped test adapter; canonical localhost DSN rerun passed all platform and persistence tests |
| initial unknown-commit evidence | **INSUFFICIENT / STRENGTHENED** | typed exception/retry unit proof was upgraded to real committed PostgreSQL receipt replay before final SHA |
| preliminary implementation SHAs | **SUPERSEDED** | every later test/source correction created a new SHA; old results were discarded and all final gates reran at `07151542…` |

## 9. Historical Verification immutability

The immutable records present at the baseline retain these SHA-256 identities:

```text
WP-03  3b5be2afa013f2639b618cb36fc3c8896d3ad1b67c47a57242c40d8724986e59
WP-04  6a8aedda78a6246a64b26335a6506315f30322c948e181b90760d73b473103a4
WP-05  990dd4f9dfbed7d1bd941301290f6ee7eb8a0b9c737efc653fa55821aa719caf
WP-06  59d7bd856eb874dc9e7b1c1f696e86f446facf3a8bd845b09e7b1cfe2bc4746c
WP-07  84dba3b18079ad54bfec0ff0a1be78b03cad136e921c08fd2d56f48d52f37d95
WP-09  2ad5eae3f6e9161c4b031ecb026b79451cd0720b4feaf0bfac90387003af5dad
WP-10  f97b33809f6c54c4b0fcd4343a99fd1d844e400a1483b9ccf59cd475fa77c221
```

## 10. Exit Gate and evidence ceiling

WP-11 passes because the exact implementation proves Target/Outcome parity,
database-derived anti-cherry-picking membership, one explicit exchange
calendar, trading-session purge/embargo, purpose-compatible protected overlap,
complete immutable multi-Partition Experiment binding, pre-access Protocol and
Run ordering, cutoff-safe exact Outcome access, global first-access ordinals,
complete observations, explicit unavailable/failed/not-estimable retention,
complete metric inputs, idempotency, concurrency, failure/recovery, exact
unknown-commit replay, read-only reconciliation, clean schema recreation, query
plans, full regression, static checks, build, and documentation checks.

It does not prove or authorize:

```text
EvidenceItem / EvidenceDependency
ResearchAssessment / ResearchQualification
Model / ModelVersion / Calibration
Context / Signal / Forecast / Opportunity
Portfolio / Risk / Execution / Fill / Position
TradeOutcome / Attribution
Runtime or CLI Cutover
Formal OOS or Prospective campaign/promotion
Alpha value, Provider qualification, trading, or Production readiness
Legacy deletion
```

The next dependency-ready checkpoint is WP-12 Research Evidence, Assessment,
and Qualification Closure, but only after this Verification and implementation
are merged into remote main and a fresh preflight proves that exact merged
fact. This record stops before WP-12.
