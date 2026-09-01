# WP-12 Research Evidence, Assessment and Qualification Implementation Plan

> **Status:** CURRENT_STATUS
> **Authority:** File-level execution sequence for the frozen WP-12 design;
> never business, Evidence, Assessment, Qualification, or exit-gate Authority
> **Owner:** Market Regime Alpha maintainers
> **Planned At:** 2026-09-02
> **Baseline:** `origin/main@883f35835671ebbd7d977b35b36c59528d536990`
> **Design:** [WP-12 canonical design](WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Design.md)
> **Branch:** `agent/wp-12-research-evidence-assessment-qualification`

## 1. Checkpoint discipline

Implementation is TDD-first and dependency ordered:

```text
Evidence vocabulary/domain
→ Evidence PostgreSQL closure and command
→ Assessment database-derived closure and command
→ Qualification Policy closure
→ Qualification Decision/floor closure
→ generation-safe read port
→ read-only verifier
→ real concurrency/failure/recovery/query-plan qualification
→ freeze exact implementation SHA
→ full engineering gate
→ immutable Verification and status reconciliation
```

No slice may introduce a Model, Forecast, DecisionRun consumer, Runtime
dispatch, CLI, Legacy dependency, compatibility facade, dual write, or future
placeholder. Each checkpoint commit is dependency-coherent and passes its
focused tests plus `git diff --check`.

## 2. Slice A — vocabulary and pure Domain

### Tests first

Create:

- `tests/refoundation/research_qualification/test_evidence_domain.py`;
- `tests/refoundation/research_qualification/test_assessment_domain.py`;
- `tests/refoundation/research_qualification/test_qualification_domain.py`.

Prove closed enum parsing, required text/hash/ordinal rules, Evidence
RUN/METRIC shape, dependency order/hash, Assessment revision/supersession
shape, deterministic Assessment status reduction, Policy floor metric/
threshold/evidence shape, Policy roster hash, floor-result reduction, and
overall Decision state. Preserve support/counter/neutral, failed,
not-estimable, negative, and inconclusive states.

### Implementation

Add:

- `research_qualification/domain/evidence.py`;
- `research_qualification/domain/assessment.py`;
- `research_qualification/domain/qualification.py`.

Extend only the public exports needed by owning Application code. Domain code
imports only `shared` and its own context.

## 3. Slice B — WP-12 schema and specification

### Tests first

Create
`tests/refoundation/research_qualification/test_wp12_schema_specification.py`
and advance only the target generation-boundary tests that must admit all ten
WP-12 relations while continuing to prohibit Model and later relations.

The specification must assert:

- exactly ten new tables and no placeholder relation;
- concrete composite FKs and FK-leading indexes;
- closed status/value/check shapes;
- root-last closure and late-child guards;
- append-only rows, contiguous revision/supersession chains, one direct
  successor;
- complete Evidence dependencies, Assessment rosters, Policy floors,
  Decision floor results, and floor Evidence rosters;
- PostgreSQL-time generation/effective/known order;
- no generic subject, JSON owner, nullable future FK, `002+`, or Legacy name.

### Implementation

Extend only:

- `infrastructure/postgres/migrations/001_baseline.sql`;
- catalog expectations and schema-generation tests directly affected by the
  68-to-78-table change.

Use named constraints, deferred closure triggers, insert guards, append-only
triggers, scoped advisory locks, and leading indexes. Do not freeze optimizer
node shape.

## 4. Slice C — Evidence UoW and command

### Tests first

Create
`tests/refoundation/research_qualification/test_evidence_postgres.py`.

Cover exact terminal Evaluation binding, same-Run Metric binding, Artifact
identity, code/config/provenance, complete dependency roster/hash, wrong
Experiment/Evaluation, self/cycle/future-parent/late-edge rejection, exact
idempotency, changed request, immutable history, rollback, optional fence, and
exact replay. Add a composition assertion that the sole TargetApplication
constructs the Evidence command.

### Implementation

Add:

- `research_qualification/ports/evidence_uow.py`;
- `research_qualification/application/evidence.py`;
- `infrastructure/postgres/repositories/research_evidence.py`;
- `infrastructure/postgres/evidence_uow.py`.

Use the existing Artifact byte verification seam before the business
transaction and exact Artifact locks inside it. Reuse shared Research command
retry/failure mechanics without widening an existing UoW.

## 5. Slice D — complete ResearchAssessment

### Tests first

Create
`tests/refoundation/research_qualification/test_assessment_postgres.py`.

Cover database-derived all-Evaluation roster, non-empty and all-terminal rule,
retention of `FAILED`, all-Evidence roster, at least one Evidence per Run,
support/counter/neutral preservation, wrong Experiment, no caller roster,
cutoff race with new Evaluation/Evidence, positive/negative/not-estimable/
inconclusive/blocked reduction, root/child reconciliation, contiguous
supersession, exact replay, changed request, mid-Evaluation-roster and
mid-Evidence-roster rollback.

### Implementation

Add:

- `research_qualification/ports/assessment_uow.py`;
- `research_qualification/application/assessments.py`;
- `infrastructure/postgres/repositories/research_assessments.py`;
- `infrastructure/postgres/assessment_uow.py`.

`AssessResearch` accepts no Evaluation/Evidence IDs or conclusion. The
repository derives both rosters under the Experiment-scoped lock and returns
the relationally calculated result.

## 6. Slice E — Policy and Qualification Decision

### Tests first

Create
`tests/refoundation/research_qualification/test_qualification_postgres.py`.

Policy tests cover exact Target/ProtocolMetric/slice copies, Decimal/Boolean
threshold compatibility, FIT input versus four admission purposes, protected
pre-access rule, ordered non-empty floors, changed replay, immutable versions,
and no late floor.

Decision tests cover exact Assessment/Policy Target binding, every floor once,
zero/ambiguous Evaluation match, missing metric, failed Run, insufficient
member/estimable counts, not-estimable policy, threshold rejection, missing
required Evidence, too much counter-evidence, complete all-direction Evidence
binding, deterministic overall state, supersession, concurrent identical and
changed requests, and mid-result/mid-evidence rollback.

### Implementation

Add:

- `research_qualification/ports/qualification_uow.py`;
- `research_qualification/application/qualifications.py`;
- `infrastructure/postgres/repositories/research_qualifications.py`;
- `infrastructure/postgres/qualification_uow.py`.

Policy registration accepts the ordered floor plan. Decision execution accepts
only exact Assessment/Policy identities plus command/provenance identities; it
derives all FloorResults and FloorEvidence bindings.

## 7. Slice F — generation-safe query and sole composition

### Tests first

Add focused query tests for exact admitted decision, purpose mismatch,
non-admitted state, not-yet-effective/known decision, same-generation source,
as-of supersession, and exact historical eligibility before a later
supersession. Add import tests proving no Market/Outcome persistence, Legacy,
Model, Decision Support repository, current/latest resolver, or second
composition root.

### Implementation

Add:

- `research_qualification/ports/qualification_read.py`;
- `infrastructure/postgres/queries/research_qualification.py`.

Extend `bootstrap.py` with separately typed Evidence, Assessment,
Qualification, read-port, and verifier fields. No Runtime step dispatch or CLI
surface is added.

## 8. Slice G — formal read-only verifier

### Tests first

Extend focused tests with clean zero-mismatch fixtures and one immutable fault
injection per owner. Assert that the verifier is read-only and has no Provider,
Market reconstruction, current/latest, Artifact payload inference, or mutation
path.

### Implementation

Extend or add:

- `research_qualification/domain/verification.py`;
- `research_qualification/application/verification.py`;
- `research_qualification/ports/verification.py`;
- `infrastructure/postgres/queries/research_verification.py`.

The result reports owner-scoped mismatch codes and only passes at
`matched=true`, `mismatch_count=0`.

## 9. Slice H — real PostgreSQL campaigns

Create focused tests for:

- identical/changed Evidence writes and dependency races;
- concurrent Evidence versus Assessment cutoff;
- concurrent Evaluation open versus Assessment cutoff;
- Assessment revisions and same-predecessor race;
- concurrent Policy registration;
- concurrent Decision and same-predecessor race;
- stale Runtime fence;
- serialization/deadlock/transient connection errors;
- actual commit followed by lost acknowledgement and exact receipt replay;
- injected mid-DAG, mid-Assessment-Evaluation, mid-Assessment-Evidence,
  mid-Policy-floor, mid-FloorResult, and mid-FloorEvidence failures;
- failure-recorder failure and exact recovery.

Prove no partial item/edge, Assessment roster, Policy floor roster, Decision
floor vector, or floor Evidence vector survives rollback.

Create representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` specifications
for Evaluation-to-Evidence, dependency reachability, complete Assessment
Evaluation/Evidence populations, Policy-floor lookup, Decision-floor closure,
and floor-Evidence reconciliation. Check bounded work and relevant declared
indexes, not a fixed plan node.

## 10. Exact-SHA qualification and exit documentation

After focused correctness passes, create one implementation checkpoint commit
and record its exact SHA/source/test/schema tree IDs and checksums. Every final
engineering command runs at that SHA. Any source/test/schema correction creates
a new checkpoint and invalidates affected earlier results.

Use a fresh disposable PostgreSQL 16 database for clean bootstrap, verify,
guarded exact-name/OID recreate, and verify. Then execute the complete gate from
the canonical WP-12 design. Disabled remote CI remains NOT_RUN.

Only after all P0/P1 gates pass, add an immutable WP-12 Verification and update
Current State, Capability Matrix, Roadmap, Authority Map, and documentation
navigation. The Verification records exact commands/results, catalog/checksums,
concurrency, recovery, replay, plans, investigated failures, evidence ceiling,
and NO-GO scopes. It may state `WP12_EXIT_GATE = PASS` only when the exact-SHA
evidence supports it.
