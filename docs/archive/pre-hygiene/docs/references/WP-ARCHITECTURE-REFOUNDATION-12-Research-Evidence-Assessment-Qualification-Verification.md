# WP-12 Research Evidence, Assessment and Qualification Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP12_EXIT_GATE_PASS`
> **Authority:** Immutable exact-SHA local engineering Verification; not Model/Forecast, Runtime/CLI Cutover, Formal OOS/Prospective promotion, Alpha value, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** `2026-09-02 (Asia/Shanghai)`
> **Execution-Time Origin Main:** `origin/main@883f35835671ebbd7d977b35b36c59528d536990`
> **WP-11 Verified Implementation:** `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`
> **WP-11 Merged Main:** `883f35835671ebbd7d977b35b36c59528d536990`
> **Implementation Checkpoint:** `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`

```text
WP11Q = MERGED / EXIT_GATE_PASS
WP12 = IMPLEMENTED_AND_QUALIFIED
WP12_EXIT_GATE = PASS
Runtime/CLI Cutover = NO-GO
Formal OOS/Prospective = NO-GO
Production = NO-GO
```

This Verification covers only:

```text
terminal EvaluationRun
→ immutable EvidenceItem / EvidenceDependency DAG
→ complete Experiment-bound ResearchAssessment
→ purpose-specific ResearchQualificationPolicy / Floor roster
→ ResearchQualificationDecision / every FloorResult / exact FloorEvidence
→ narrow generation-safe admitted-qualification read port
```

It neither starts the optional Model branch nor creates a DecisionRun consumer.

## 1. Dependency preflight, branch, and identities

WP-11Q was qualified, merged through PR #94, fetched again, and rechecked before
the independent WP-12 branch was created. Merged main contains the immutable
WP-11 Verification, `WP11_EXIT_GATE = PASS`, and the exact verified WP-11
implementation as an ancestor. No WP-12 table, package, or placeholder existed
before that merge gate.

Execution used an isolated linked worktree. The pre-existing
`.idea/modules.xml` change in the primary checkout was not modified, staged,
stashed, or committed.

```text
remote                 git@github.com:yuan2go/market-regime-alpha.git
origin/main baseline   883f35835671ebbd7d977b35b36c59528d536990
branch                 agent/wp-12-research-evidence-assessment-qualification
worktree               isolated linked worktree wp-12-research-evidence-assessment-qualification
implementation         48949c87ad0241a8d60031137bc3aa8eb9887525
root tree              b81e4c2ae29ff0f6b26c15333004b849ebc56431
source tree            baa201bfdd4540ad0a63dc4f0f3274eed2199db1
tests tree             906f0e59aea13218bfb461ffb967685fe57bb64e
Research tree          94b0c082a8db37ba3e1734834aa4154e3df3fff0
baseline blob          b7fe5192a1df0c5733842c632a70e2d88db80d91
baseline SHA-256       a7ef01de52dcb0dae900cc4bba6e7861e70dff0deb438e2fab2e4cbbcfa8986c
source diff SHA-256    4864ff5b990942bfe216d8d68203b2bebda4832e5f5c291061007f04d92a9679
test diff SHA-256      5cd6d084764d4e0c08c21a72aba590d9bf3a89272294dfed80e4f451f59fbcd0
```

Dependency-coherent checkpoints are:

```text
cbbe110  open WP-12 after the merged WP-11Q preflight
e57b238  freeze canonical WP-12 design
d761cfe  freeze detailed implementation and qualification plan
b2d180a  define WP-12 domain
6dbcf55  establish relational Authority schema
42497ce  close Evaluation-bound Evidence
b8d4343  derive complete Experiment Assessments
d417691  close purpose-specific Qualification
9866e77  compose and verify WP-12 Authority
45deb61  qualify concurrency, failure, recovery, and replay
d46013e  prove representative query plans
5e8dab2  retain narrow stable Research exports
48949c8  advance exact schema-generation assertions through WP-12
```

Historical immutable Verification files were read only.

## 2. Evidence Authority closure

`EvidenceItem` requires a concrete terminal `EvaluationRun`, immutable evidence,
code, and config Artifact FKs, typed class/origin/scope/role/direction, proof
ceiling, exact provenance, dependency roster hash, and content hash. A
metric-scoped item additionally binds a concrete same-Run `EvaluationMetric`;
a Run-scoped item rejects a metric identity.

`EvidenceDependency` is only an ordered Evidence-to-Evidence edge. Domain,
recursive PostgreSQL guards, chronological ordering, deferred child closure,
count/hash reconciliation, and immutable root/edge triggers reject self-edges,
cycles, late edges, missing parents, and cross-identity drift. Dependency
parents must already exist; no generic graph, `(kind,id)`, JSON subject, weak
path, or string business reference exists.

`RecordEvidence` verifies Artifact bytes outside the short business transaction,
then locks the terminal Evaluation and exact Artifacts, appends all dependency
edges and the root atomically, writes receipt/audit/provenance, and closes the
roster. Identical commands produce one truth and exact replay; changed commands
fail closed.

## 3. Complete ResearchAssessment closure

One append-only `ResearchAssessment` revision binds exactly one Experiment.
`AssessResearch` accepts neither caller-selected Evaluation/Evidence IDs nor a
requested positive conclusion. At a PostgreSQL-authoritative cutoff it derives:

- every terminal EvaluationRun opened for the Experiment by that cutoff;
- every EvidenceItem for those exact Evaluation Runs by that cutoff;
- complete ordered Evaluation and Evidence child rosters and hashes;
- source-generation minimum/maximum, terminal/known times, provenance, and
  deterministic Assessment status.

The root and child tables are bidirectionally reconciled. An incomplete
Evaluation roster, cherry-picked Evidence, foreign Experiment/Run/Evidence,
nonterminal Evaluation, missing Evidence, partial child transaction, changed
replay, or supersession fork fails closed. Support, counter-evidence, neutral,
failed Evaluation, inconclusive, and wholly not-estimable input remain explicit;
Artifact content is never interpreted as the conclusion. Supersession appends a
new positive revision with a direct predecessor; historical revisions remain
immutable.

## 4. Purpose-specific Qualification closure

`ResearchQualificationPolicy` freezes one Research purpose and a complete
non-empty ordered relational floor roster. Each floor binds an exact Evaluation
Protocol metric/slice, required Evaluation purpose/state, direction/operator,
threshold, minimum sample/estimable counts, missing/not-estimable policy,
Evidence role/direction requirements, and content hash. Protocol Target and
applicable purpose are concrete compatibility facts. No threshold or decision
rule is hidden in JSON or free text.

`DecideResearchQualification` binds one exact Assessment and one exact Policy,
derives the complete eligible Evaluation/metric/Evidence inputs, and emits one
`ResearchQualificationFloorResult` for every Policy floor plus the exact
`ResearchQualificationFloorEvidence` set used by that floor. Missing metric,
insufficient sample, counter-evidence, failed input, and not-estimable input are
recorded as explicit floor states; no failed floor or negative Evidence can be
skipped. Root, result, and Evidence rosters are independently counted and
hashed before `ADMITTED`, `REJECTED`, or `INCONCLUSIVE` can commit.

Policy and Decision histories are append-only and direct-supersession aware.
`ADMITTED` grants only the declared Research purpose; it does not prove Alpha,
select a Model, authorize a Forecast, or permit trading.

## 5. Temporal and generation safety

Every Evidence and Assessment inherits exact source Outcome generation facts
from completed older Evaluations. Qualification enforces:

```text
source Outcome generation
< qualification effective_at
<= qualification known_at
<= PostgreSQL recorded_at
```

The public read seam requires an exact Qualification Decision ID, requested
knowledge cutoff, requested later DecisionTime, and declared purpose. It returns
only a non-superseded `ADMITTED` identity whose source generation is strictly
older. It has no unrestricted current/latest selector and creates no
DecisionRun FK or same-generation feedback edge.

## 6. Transactions, concurrency, failure, and recovery

Evidence, Assessment, and Qualification own three narrow UoWs; there is no
Research God UoW or Domain/Application import of PostgreSQL. Commands perform
Artifact I/O before the business transaction, then use short transactions,
deterministic lock order, exact receipts, append-only roots/children, audit and
optional Runtime fence checks. No Provider, network, filesystem, Market bars,
or Outcome recalculation occurs inside the business transaction.

Real PostgreSQL campaigns prove:

- concurrent identical Evidence, Assessment, Policy, and Decision commands
  create one Authority and exact replay; changed requests reject;
- dependency/roster/floor/floor-Evidence children cannot commit partially;
- Assessment derives all terminal Evaluations and Evidence rather than accepting
  a cherry-picked caller roster;
- supersession has one direct successor and cannot fork;
- injected mid-Evidence-dependency, mid-Assessment-Evidence, and
  mid-Qualification-floor-Evidence serialization failures roll back every root,
  child, receipt, and audit row, then recover by exact replay;
- real committed-but-unacknowledged Evidence, Assessment, Policy, and Decision
  transactions are recovered by receipt probe and exact replay, never blind
  business mutation;
- stale Runtime fences across all three layers produce zero business, receipt,
  audit, or failure writes.

The shared transaction substrate's real serialization, deadlock, transient
connection, and failure-recorder campaigns remain covered by the inherited
WP-11/Persistence suites. WP-12 adds its own real concurrent writers, injected
PostgreSQL `40001`, unknown-commit, stale-fence, and partial-roster campaigns.

## 7. Read-only replay and reconciliation

The permanent narrow verifier recomputes:

- Evidence root identity, exact Evaluation/Metric/Artifact/provenance bindings,
  ordered dependency roster/hash, terminal Evaluation state, and DAG closure;
- Assessment Experiment identity, complete terminal Evaluation and Evidence
  rosters, all child/root hashes, deterministic status, supersession, generation,
  Artifact, receipt, audit, Runtime, and provenance facts;
- Policy purpose, exact Target/Protocol/metric/slice compatibility, every floor,
  child/root hashes, supersession, Artifact, receipt, audit, and provenance;
- Decision Assessment/Policy identity, every FloorResult, exact FloorEvidence,
  source metric values/counts, threshold result, all roster hashes, final state,
  supersession, effective/known/generation, Artifact, receipt, audit, Runtime,
  and provenance facts.

It performs no Provider call, unrestricted current/latest lookup, Market
reconstruction, bars-to-label computation, or mutation. Clean fixtures return:

```text
matched = true
mismatch_count = 0
```

Fault-injected immutable-row drift produces typed mismatches rather than a false
match.

## 8. PostgreSQL catalog and reproducibility

Only unreleased `MRA_REFOUNDATION_1/001_baseline.sql` was extended. WP-12 adds
exactly ten tables:

```text
evidence_item
evidence_dependency
research_assessment
research_assessment_evaluation
research_assessment_evidence
research_qualification_policy
research_qualification_policy_floor
research_qualification_decision
research_qualification_floor_result
research_qualification_floor_evidence
```

No `002+`, Model/Forecast/Context placeholder, compatibility schema, dual write,
generic registry, polymorphic subject, nullable future FK, or JSON business
Authority was created.

The final disposable PostgreSQL 16.14 catalog contains:

```text
tables                    78
views                      4
indexes                  611
constraints              913
functions                 65
non-internal triggers    163
catalog objects        1,835
```

Checksums are:

| Artifact | SHA-256 |
|---|---|
| baseline | `a7ef01de52dcb0dae900cc4bba6e7861e70dff0deb438e2fab2e4cbbcfa8986c` |
| seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| catalog | `5fa66be6a0b6019032217e201ed547cfd9217fa109ef3b9122d3f0d6dc48ee72` |
| reference vocabulary | `f5ab9cc4fe7617dd0bc5de171365e877eddadc9f6158f3fa0eb83f634c03e701` |

Final disposable database proof:

```text
database             mra_wp12_final_d46013e
database OID         16384 before and after guarded recreate
PostgreSQL           16.14 Homebrew arm64
socket/cluster       /tmp/mra-wp12-final-d46013e-pg.eCL1sF
port                 55451
Artifact root        /tmp/mra-wp12-final-d46013e-artifacts.rS6xYk
recreate plan        /tmp/mra-wp12-final-48949c8-recreate-plan.json
plan payload hash    837583bfa07f9ed2706c025813cd1c7e1e2b9952486b408ec5431f93ef606006
plan file SHA-256    703fe638abed7d8f6c2c21a54d70bc6d4e7fac0b0cae49c31b2040267873e13f
challenge            1188c3998e0cd9d37f7a19e0
operator             codex-wp12
backup attestation   DISPOSABLE_DATABASE_NO_USER_DATA
unexpected objects   []
```

The final run first proved the schema absent, then passed clean bootstrap and
verify, guarded exact-name/OID recreate, and post-recreate verify. OID, catalog
counts, and all four checksums remained stable.

## 9. Representative database plans

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` executed for:

```text
EvidenceItem → exact EvaluationRun
EvidenceDependency DAG traversal
Assessment → complete terminal Evaluation roster
Assessment → complete Evidence roster
PolicyFloor → exact EvaluationProtocolMetric
Decision → FloorResult / exact FloorEvidence reconciliation
generation-safe exact-ID admission read
```

The specification accepts equivalent declared PK/composite-unique/FK-leading
indexes without fixing optimizer node shape. Each fixture path returned no more
than two rows and executed below 100 ms. No join explosion, missing FK-leading
index, or lock-amplification blocker was found.

## 10. Engineering validation ledger

Environment:

```text
OS          macOS 26.5.2 arm64
uv          0.11.7
Python      3.12.2
PostgreSQL  16.14 Homebrew arm64
timezone    Asia/Shanghai
```

All final commands below ran against exact implementation
`48949c87ad0241a8d60031137bc3aa8eb9887525` in a clean worktree.

| Command / check | Result | Evidence |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | **PASS** | 61 locked packages checked |
| `pytest -q tests/refoundation/research_qualification` | **PASS** | 216/216 |
| `pytest -q tests/refoundation` | **PASS** | 545/545 |
| `pytest -q tests/platform` | **PASS** | 33/33 |
| `pytest -q tests/persistence/postgres` | **PASS** | 286/286 |
| `pytest -q` | **PASS** | 3,585/3,585 repository nodes |
| `ruff check .` | **PASS** | all checks passed |
| `python -m mypy` | **PASS** | no issues in 536 source files |
| `python -m build --outdir /tmp/mra-wp12-final-d46013e-build.ozuNhq` | **PASS** | wheel and sdist built |
| `python scripts/check_docs_links.py` | **PASS** | canonical inventory, metadata, and links OK |
| `pytest -q tests/scripts/test_check_docs_links.py` | **PASS** | 7/7 |
| architecture/import suite | **PASS** | 57/57 |
| clean `mra db bootstrap` + `mra db verify` | **PASS** | exact 78-table catalog/checksums |
| guarded `recreate-plan` + `recreate-apply` + verify | **PASS** | exact OID, no unexpected objects, stable checksums |
| WP-12 concurrency/recovery/replay/verifier suite | **PASS** | included in 216 focused tests |
| seven representative plan specifications | **PASS** | included in focused/full tests |
| `git diff --check` and clean status | **PASS** | no whitespace or uncommitted implementation change |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | read-only result `enabled=false`; remote CI is not reported PASS |

Build artifacts:

```text
wheel  0b2e3cb35906898dd31b02e903edc47648a3536e2bf46fc2b3cab4fe633c24f3
sdist  2bae8962d2bb759f25328646e4aef03ca4117620fea1758a3754822178b943eb
```

No final test was skipped, xfailed, deleted, reordered, or weakened to obtain
the gate.

## 11. Investigated non-final failures

No diagnostic failure is promoted to PASS:

| Attempt | Classification | Resolution |
|---|---|---|
| first clean-database CLI invocation | **FAIL / INVOCATION CORRECTED** | `MRA_ARTIFACT_ROOT` was absent; no schema mutation occurred, then the canonical explicit environment rerun passed |
| first focused Research suite | **FAIL / CORRECTED** | stable export line limits exposed broad Research package exports; exports were narrowed from 23/39 to 14/26 lines without changing the public command APIs; the limit was not raised |
| first full refoundation suite | **FAIL / CORRECTED** | five generation-boundary tests still prohibited WP-12 tables or omitted them from the exact table union; they now require exactly the ten WP-12 relations while continuing to forbid Model/Context/TradeOutcome and every later table |
| first representative plan assertion | **FAIL / CORRECTED** | PostgreSQL chose exact composite unique indexes instead of one hard-coded primary-key name; the final assertion accepts only equivalent declared leading indexes and does not freeze optimizer shape |
| first self-cycle scenario | **FAIL / TEST CORRECTED** | Domain rejected the invalid dependency before the command reached PostgreSQL; the test now proves Domain rejection plus zero database rows rather than incorrectly demanding a database exception |
| preliminary noncanonical mypy path invocation | **FAIL / CORRECTED** | repository-local path invocation exposed unrelated legacy packaging errors plus three new verifier errors; the verifier errors were fixed and the canonical `python -m mypy` gate passed all 536 source files |
| preliminary implementation SHAs | **SUPERSEDED** | every source/test correction created a new SHA; old results were discarded and all final gates reran at `48949c87…` |

## 12. Exit Gate and evidence ceiling

WP-12 passes because the exact implementation proves Evaluation-bound immutable
Evidence, a concrete dependency DAG, complete Experiment-bound Assessment,
negative/inconclusive/not-estimable preservation, purpose-specific relational
Policies, one explicit result per floor, exact Floor-to-Evidence bindings,
append-only supersession, strict generation safety, three narrow UoWs, exact
idempotency/concurrency/recovery/unknown-commit replay, permanent read-only
reconciliation, clean schema recreation, representative plans, full regression,
static checks, build, and documentation checks.

It does not prove or authorize:

```text
Model / ModelVersion / Calibration
Context / Signal / Forecast / Opportunity / Thesis
Portfolio / Risk / Execution / Fill / Position
TradeOutcome / Attribution
DecisionRun consumption of Research Qualification
Runtime or CLI Cutover
Legacy deletion
Formal PIT/OOS or Prospective campaign/promotion
Alpha value or optimization
Provider qualification
trading or Production readiness
```

The next dependency-ready branch is optional Model / ModelVersion / Calibration.
It remains optional, requires separate authorization and its own exit gate, and
was not started by this checkpoint. This record stops at WP-12.
