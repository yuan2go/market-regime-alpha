# WP-12 Research Evidence, Assessment and Qualification Closure Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Approved implementation contract for WP-12 only; not
> implementation, Research admission, Model/Forecast, Runtime/CLI Cutover,
> Formal OOS/Prospective promotion, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Frozen At:** 2026-09-02
> **Execution-Time Origin Main:**
> `origin/main@883f35835671ebbd7d977b35b36c59528d536990`
> **WP-11 Verified Implementation:**
> `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`
> **Branch:** `agent/wp-12-research-evidence-assessment-qualification`
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP11_EXIT_GATE = PASS / MERGED
WP12_DESIGN = FROZEN
WP12_IMPLEMENTATION = NOT_STARTED
Runtime/CLI Cutover = NO-GO
Formal OOS/Prospective promotion = NO-GO
Production = NO-GO
```

## 1. Audit result and supersession boundary

WP-11 is present in the sole target composition root and its immutable
Verification is an ancestor of the execution-time main. It provides the exact
terminal Evaluation, metric, observation, first-access, receipt, audit, and
generation inputs required by this package.

WP-08's Evidence/Assessment/Qualification semantics remain applicable. This
record supplies the implementation-level closure that WP-08 intentionally left
for its later work package. It does not alter the immutable WP-11 Verification.

Legacy migrations 053, 057, and 068 and their Python writers preserve useful
behavioral evidence: append-only decisions, typed negative/not-estimable
results, Locked-OOS consumption, source references, and metric projections.
They also rely on purpose-local owners, JSON payload business truth, weak
Artifact references, caller-selected rosters, and parallel label/qualification
paths. Legacy is therefore characterization evidence only and cannot be
imported by target Domain/Application code, called by a target adapter, or
dual-written.

Active status documents now identify WP-12 as dependency-ready. There is no
separate Research Validity context: all new ownership stays in permanent
`market_regime_alpha.research_qualification`.

## 2. Scope and explicit non-scope

WP-12 adds exactly this chain:

```text
terminal EvaluationRun
→ immutable EvidenceItem / EvidenceDependency DAG
→ Experiment-bound ResearchAssessment revision
→ purpose-specific ResearchQualificationPolicy / Floor roster
→ ResearchQualificationDecision / every FloorResult / exact FloorEvidence
→ narrow generation-safe admitted-qualification read port
```

It adds no Model, ModelVersion, Calibration, Context, Signal, Forecast,
Opportunity, Portfolio, Risk, Execution, Fill, Position, TradeOutcome,
Attribution, DecisionRun consumer binding, Runtime dispatch, business CLI,
Legacy compatibility facade, formal campaign, promotion, or Production owner.
No placeholder table, nullable future-subject FK, generic registry, polymorphic
`(kind, id)`, JSON business owner, compatibility write, or dual write is
permitted.

## 3. Authority DAG and generation rule

The aggregate graph remains one-way:

```text
Experiment ───────────────────────────────┐
  └→ ExperimentRun → EvaluationRun ──────┤
                         │                │
                         └→ EvidenceItem ├→ ResearchAssessment
                               │          │
                               └──────────┘
ResearchQualificationPolicy ─────────────┤
                                         v
                         ResearchQualificationDecision
```

The cross-generation rule is:

```text
Outcome(n)
→ Evaluation(n)
→ Evidence(n)
→ Assessment(n)
→ Qualification(n)
→ exact read eligibility for DecisionTime(n+1)
```

WP-12 creates no FK or command back into DecisionRun. Its read port accepts an
exact Qualification Decision ID and a requested later DecisionTime; it never
selects unrestricted current/latest state. The later Decision Support package
must create its own concrete roster/member FK binding.

## 4. Closed vocabulary

WP-12 V1 freezes the following relational vocabulary.

Evidence classes are limited to evaluation-bound facts available in this
checkpoint:

```text
SOFTWARE_VERIFICATION
SOURCE_CAPTURE
TEMPORAL_LINEAGE
DATASET_LINEAGE
RESEARCH_RESULT
OUTCOME_OBSERVATION
REPLAY_COMPARISON
OPERATOR_ATTESTATION
```

Evidence origin classes are:

```text
FIXTURE
RECORDED_PROVIDER
QUALIFIED_ARCHIVE
PROSPECTIVE_CAPTURE
DERIVED_CANONICAL
OPERATOR_ATTESTED
```

Evidence scope, role, direction, and dependency role are independent:

```text
scope:      RUN | METRIC
role:       PRIMARY_RESULT | ROBUSTNESS | LINEAGE | MISSINGNESS |
            LIMITATION | REPLAY | PROCESS_CONTROL
direction:  SUPPORT | COUNTER | NEUTRAL
dependency: DERIVED_FROM | CORROBORATES | QUALIFIES | CONTRADICTS
```

Assessment status is terminal:

```text
SUPPORTED | REJECTED | NOT_ESTIMABLE | INCONCLUSIVE | BLOCKED | FAILED
```

Research qualification purpose is deliberately narrower than Partition
purpose:

```text
DISCOVERY | VALIDATION | LOCKED_OOS | PROSPECTIVE
```

`FIT` remains a valid Experiment/Evaluation input purpose but is not itself an
admission purpose. A Policy may still require a FIT floor as an input to one of
the four qualification purposes.

Policy metric operator and missingness behavior are:

```text
operator:            AT_LEAST | AT_MOST | EQUALS
floor_missingness:   REJECT | INCONCLUSIVE
floor_status:        SATISFIED | REJECTED | MISSING |
                     NOT_ESTIMABLE | INCONCLUSIVE | BLOCKED
decision_status:     ADMITTED | REJECTED | INCONCLUSIVE
```

No status is inferred from enum order. `ADMITTED` means admission only for the
declared Research purpose and never Alpha proven, Model selected, trading
authorized, or Production ready.

## 5. Evidence Authority

`EvidenceItem` is immutable and requires:

- one exact terminal `EvaluationRun`, including `COMPLETED` or `FAILED`;
- one exact immutable evidence Artifact plus exact code/config Artifacts;
- optional exact `EvaluationMetric` only when `scope = METRIC`;
- evidence class, origin, role, direction, proof ceiling, observed time,
  provenance, dependency count/hash, and content hash;
- the Evaluation's Experiment, terminal time, and maximum source Outcome
  DecisionTime copied under composite FK/trigger validation for efficient
  generation checks.

Run-scoped evidence forbids an EvaluationMetric FK. Metric-scoped evidence
requires a concrete same-Run EvaluationMetric FK. This nullable shape expresses
a current business distinction, not a future-subject placeholder.

`RecordEvidence` accepts one item plan and an ordered set of already-existing
parent Evidence IDs. It verifies all Artifact bytes before the business
transaction. Inside the Evidence UoW it locks the terminal Evaluation and exact
Artifacts, derives the Experiment/generation facts, validates each parent, then
inserts the dependency edges and root atomically.

The parent must already be recorded, its observed/recorded time cannot be later
than the child, and every edge uses a concrete Evidence-to-Evidence FK. Edges
are inserted before the child root through a deferred child FK; a committed
root rejects late edges. This chronological parent rule plus a recursive
reconciliation check proves a DAG and rules out self/cyclic dependency without
a generic graph registry. Root count/hash and contiguous edge order make the
dependency roster complete.

## 6. ResearchAssessment Authority

One append-only Assessment revision binds one exact Experiment and freezes:

- stable assessment code, positive revision, and optional direct predecessor;
- one PostgreSQL-authoritative Evaluation/Evidence cutoff;
- the complete Evaluation roster/count/hash;
- the complete Evidence roster/count/hash;
- source generation minimum/maximum DecisionTime and maximum terminal/known
  times;
- relationally derived status and reason;
- code/config Artifacts, provenance, content hash, and recorded time.

`AssessResearch` does not accept Evaluation IDs, Evidence IDs, or a requested
conclusion. Under one Assessment UoW and an Experiment-scoped advisory lock it:

1. locks the exact Experiment and captures a PostgreSQL-authoritative cutoff;
2. derives every `EvaluationRun` for that Experiment whose `opened_at` is no
   later than the cutoff;
3. requires a non-empty roster and requires every such Run to be terminal;
4. includes `FAILED` Runs rather than deleting them;
5. derives every EvidenceItem for those Runs whose `recorded_at` is no later
   than the cutoff;
6. requires at least one EvidenceItem for every EvaluationRun;
7. includes all support, counter, and neutral items, not a caller subset;
8. writes child rosters first and the Assessment root last, then reconciles the
   same database-derived populations before commit.

`OpenEvaluationRun`, `RecordEvidence`, and `AssessResearch` share the scoped
roster advisory lock. A Run or Evidence item that wins after the Assessment
cutoff receives a later PostgreSQL timestamp and belongs only to a later
Assessment revision. It cannot make the older frozen roster silently partial.

The V1 conclusion is calculated only from relational Evaluation/Evidence
facts:

- any rostered failed Evaluation produces `BLOCKED`;
- any estimated Evaluation metric with `acceptance_state = REJECTED` produces
  `REJECTED`;
- if every declared metric is `NOT_ESTIMABLE`, the result is
  `NOT_ESTIMABLE`;
- all declared metrics accepted with no counter-evidence produces `SUPPORTED`;
- mixed estimability, counter-evidence without an already-rejected metric, or
  otherwise conflicting complete facts produces `INCONCLUSIVE`.

`FAILED` is reserved for a typed, relationally recorded Assessment execution
result that could not apply its frozen rule; ordinary command/integrity failure
instead rolls back and records the standard failed command receipt. Artifact
JSON and report prose are never parsed to infer the status.

Supersession is append-only. Revision one has no predecessor; revision `n`
must directly supersede revision `n-1` in the same Experiment/assessment code,
and one revision may have at most one direct successor. The old root and child
rosters remain immutable.

## 7. ResearchQualificationPolicy Authority

One immutable Policy version freezes:

- policy code/version and optional direct predecessor;
- one exact Target/version/hash;
- one declared Research qualification purpose;
- required Assessment status;
- whether pre-access policy freeze is mandatory;
- ordered non-empty floor count/hash;
- code/config Artifacts, provenance, content hash, and PostgreSQL frozen time.

`LOCKED_OOS` and `PROSPECTIVE` Policies always require pre-access freeze.
`DISCOVERY` and `VALIDATION` may declare it explicitly but cannot weaken a
protected purpose.

Every `ResearchQualificationPolicyFloor` relationally freezes:

- exact Evaluation Protocol and Protocol Metric ID/content hash;
- required Evaluation Partition purpose and terminal state;
- exact metric code, source value type, reducer, slice kind, and concrete
  Candidate disposition where applicable;
- direction, operator, Decimal/Boolean threshold shape;
- minimum member and estimable counts;
- missing/not-estimable behavior;
- required Evidence class/origin/role, minimum matching support count, and
  maximum counter count;
- ordinal, floor code, content hash, and whether the floor is required.

The Policy Target must equal the exact Protocol/metric Target. A floor's copied
metric/slice fields are checked against its concrete Protocol Metric FK; they
are not free strings or JSON. Child floors insert before the root and a deferred
root closure proves non-empty contiguous order, count/hash, exact Target, and
no late floor binding.

## 8. Qualification Decision Authority

One Decision requires one exact terminal Assessment and one exact frozen Policy
with matching Target/Experiment lineage. `DecideResearchQualification` accepts
no floor results and no Evidence subset. In one Qualification UoW it:

1. locks Policy, all floors, Assessment, and both complete Assessment rosters;
2. proves Policy freeze/order and, for protected purposes, that the Policy
   predates every relevant first Outcome access;
3. evaluates every floor exactly once;
4. finds the exact Assessment Evaluation matching the floor's purpose and
   Protocol; zero matches is `MISSING`, more than one is `BLOCKED`;
5. binds the exact EvaluationMetric when one exists and records observed
   member/estimable counts, state, Decimal/Boolean value, threshold comparison,
   and typed reason;
6. binds every Assessment Evidence item for that matched Evaluation to the
   FloorResult, including support, counter, and neutral directions;
7. checks the floor's required class/origin/role/support/counter counts;
8. writes all FloorResults, complete FloorEvidence rosters, Decision root,
   receipt, audit, and optional Runtime finalization atomically;
9. reconciles every Policy floor and every exact evidence roster before commit.

Missing or not-estimable input is a result, never a skipped floor. A failed
Evaluation remains in the Assessment and yields an explicit `BLOCKED` floor.
No floor reads Artifact JSON, recomputes Outcome, or accesses Market.

Overall decision is deterministic:

- any rejected required floor or a rejected Assessment gives `REJECTED`;
- `ADMITTED` requires the Policy's required Assessment status and every
  required floor `SATISFIED`;
- all remaining complete vectors give `INCONCLUSIVE`.

Decision supersession is append-only and contiguous within one
Experiment/policy purpose decision series. It never rewrites the Assessment,
Policy, FloorResults, or earlier Decision. Exact retry replays the original
vector; a changed request fails closed.

## 9. Generation, effective-time, and known-time safety

The database derives and freezes these monotonic facts:

```text
max source Outcome DecisionTime
< Evaluation terminal time
< Evidence recorded time
<= Assessment cutoff/recorded time
< Qualification decided/effective/known time
```

All Authority times are PostgreSQL authoritative. Application timestamps are
diagnostic only. The Assessment and Decision roots copy their source generation
minimum/maximum and known-time ceiling under relational reconciliation.

The owning narrow read port is conceptually:

```text
read_admitted_qualification(
    exact_qualification_decision_id,
    required_purpose,
    requested_decision_time,
) -> ExactAdmittedResearchQualification
```

It returns only when the exact decision is `ADMITTED`, purpose-matched,
effective and known by the requested DecisionTime, not superseded by another
decision effective/known by that time, and its maximum source Outcome
DecisionTime is strictly earlier than the requested DecisionTime. Otherwise it
fails closed. It never resolves a mutable latest/current decision and exposes
no mutation, SQL, repository, Artifact payload, Market, Outcome, or bars.

This port is not connected to DecisionRun in WP-12. A future owning consumer
must freeze its own concrete complete roster/member binding.

## 10. Persistence and concrete FK closure

Only unreleased `MRA_REFOUNDATION_1/001_baseline.sql` is extended. WP-12 adds
exactly ten Research-owned tables:

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

Required concrete chains include:

| Child | Required parent |
|---|---|
| `evidence_item` | terminal EvaluationRun + optional same-Run EvaluationMetric + exact evidence/code/config Artifacts |
| `evidence_dependency` | child EvidenceItem + prior parent EvidenceItem |
| `research_assessment` | exact Experiment + optional same-series predecessor + exact code/config Artifacts |
| `research_assessment_evaluation` | Assessment + exact Experiment terminal EvaluationRun |
| `research_assessment_evidence` | Assessment + EvidenceItem whose EvaluationRun is in the Assessment roster |
| `research_qualification_policy` | exact Target + optional same-code predecessor + code/config Artifacts |
| `research_qualification_policy_floor` | Policy + exact same-Target EvaluationProtocolMetric |
| `research_qualification_decision` | exact Assessment + Policy + optional same-series predecessor + code/config Artifacts |
| `research_qualification_floor_result` | Decision + exact Policy floor + optional exact AssessmentEvaluation/EvaluationMetric current-fact binding for typed missingness |
| `research_qualification_floor_evidence` | FloorResult + exact AssessmentEvidence from the Decision's Assessment |

The schema directly enforces append-only roots/children, contiguous revisions,
one direct successor, ordered complete rosters, exact same-Experiment and
same-Assessment identities, exact Target/protocol binding, every floor result,
every floor evidence roster, content/hash shapes, temporal order, and FK-leading
indexes. Deferred constraint triggers close root-last rosters. Insert guards
reject late children after a root is committed.

The current 68-table/four-view draft becomes 78 tables/four views. Relation
count is descriptive, not a quota. No `002+` migration is created while the
epoch remains unreleased.

## 11. Commands, UoWs, composition, and transactions

The three narrow owners are:

```text
Evidence UoW:
  EvidenceItem / EvidenceDependency

Assessment UoW:
  ResearchAssessment / ResearchAssessmentEvaluation /
  ResearchAssessmentEvidence

Qualification UoW:
  ResearchQualificationPolicy / ResearchQualificationPolicyFloor /
  ResearchQualificationDecision / ResearchQualificationFloorResult /
  ResearchQualificationFloorEvidence
```

The sole target composition root constructs `RecordEvidence`,
`AssessResearch`, `RegisterResearchQualificationPolicy`,
`DecideResearchQualification`, the generation-safe read port, and the read-only
verifier. It adds no Runtime dispatch or CLI command.

Every command uses a short PostgreSQL transaction, optional Runtime fence first,
the existing global lock order, exact idempotency, receipt/audit, bounded typed
transient retry, and exact receipt probe/replay after unknown commit. No network,
Provider, broker, filesystem, or Artifact-byte I/O occurs inside a business
transaction. Repository methods never open nested transactions.

Concurrent identical requests produce one canonical root and exact replay.
Changed requests fail closed. A deterministic business failure rolls back fully
then uses the owning narrow failure recorder; a stale fence causes zero
business, receipt, audit, or failure writes.

## 12. Read-only verification and reconciliation

The permanent `ResearchQualificationVerifier` recomputes without mutation:

- Evidence identity, exact Evaluation/Metric/Artifact bindings, dependency
  order/count/hash, chronology, and DAG;
- Assessment exact Experiment, complete cutoff-derived Evaluation roster,
  terminal states, complete Evidence roster, per-Evaluation evidence presence,
  status derivation, generation bounds, hashes, and supersession chain;
- Policy exact Target, floor order/count/hash, metric/slice copy, Artifact and
  supersession facts;
- Decision exact Assessment/Policy, every floor, every typed result, every
  complete support/counter/neutral Evidence binding, overall state,
  generation/effective/known times, and supersession;
- receipt, audit, optional Runtime fence, code/config Artifact, and provenance
  identities.

Passing is only:

```text
matched = true
mismatch_count = 0
```

The verifier cannot call Provider, query unrestricted current/latest, access
Market/Outcome persistence, reconstruct labels, read Artifact business JSON,
or mutate Authority.

## 13. TDD and engineering qualification

Implementation proceeds evidence first, then Assessment, then Policy/Decision,
then generation-safe reads/reconciliation. Required focused tests include:

- valid/invalid Evidence scope/metric/Artifact shape and exact content identity;
- DAG edge order, wrong Evaluation, cycle/self/late-edge rejection;
- support/counter/neutral and positive/negative/inconclusive/not-estimable
  preservation;
- database-derived complete Evaluation roster and non-terminal rejection;
- database-derived complete Evidence roster, per-Run evidence requirement, and
  cherry-pick impossibility;
- wrong Experiment/Evaluation and wrong Assessment/Evidence binding;
- Assessment and Decision contiguous append-only supersession;
- Policy exact Target/protocol/metric/slice, non-empty contiguous floors, and
  threshold/value-type compatibility;
- missing/duplicate/failed/insufficient/not-estimable floor outcomes;
- every floor result and complete support/counter/neutral floor Evidence roster;
- protected-purpose pre-access Policy rule;
- generation/effective/known-time read rejection and no same-generation read;
- exact idempotency, changed replay, real concurrency, injected mid-roster
  rollback, failure recorder, serialization/deadlock/transient connection, and
  real unknown-commit receipt replay;
- read-only verifier zero mismatch and typed fault injection;
- schema/catalog/index/trigger specification and representative plans.

The final exact implementation SHA must pass:

```text
uv sync --frozen --extra dev --extra postgres
WP-12 focused suites
tests/refoundation
tests/platform
tests/persistence/postgres
full repository pytest
full Ruff
full mypy
package build
documentation/navigation
architecture/import
clean PostgreSQL 16 bootstrap/verify/exact-OID recreate/verify
schema/catalog verification
real concurrency/failure/recovery/replay campaign
representative EXPLAIN (ANALYZE, BUFFERS)
git diff --check
```

Remote CI is reported exactly as configured; disabled Actions is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, never PASS.

## 14. Exit gate

Only exact-SHA evidence for all of the following permits an immutable WP-12
Verification and `WP12_EXIT_GATE = PASS`:

```text
Evaluation-bound immutable Evidence Authority
+ complete validated Evidence DAG
+ Experiment-bound cutoff-complete terminal Evaluation roster
+ complete non-cherry-picked Evidence roster
+ negative/inconclusive/not-estimable preservation
+ purpose-specific immutable Policy and relational floor semantics
+ every floor explicitly evaluated
+ complete exact floor Evidence binding
+ append-only Assessment/Policy/Decision supersession
+ generation/effective/known-time safety
+ exact idempotency/concurrency/recovery/replay
+ full engineering qualification
```

If any required gate fails, status is `WP12_EXIT_GATE = NO-GO` and execution
stops. Passing WP-12 makes optional Model/ModelVersion/Calibration merely
dependency-ready; it does not start that branch automatically.
