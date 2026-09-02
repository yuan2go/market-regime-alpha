# WP-14 Formal Research / OOS / Prospective Engineering Readiness Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Frozen implementation contract for WP-14
> **Baseline:** `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Scope:** engineering mechanics only; no empirical admission
> **Owner:** Market & PIT, Runtime, Research & Qualification
> **Frozen:** 2026-09-02

## Decision

WP-14 closes the engineering seams required to run a controlled formal research
campaign. It does not run such a campaign and cannot promote fixture evidence.
The existing owners remain authoritative:

```text
Runtime Run / Step / Attempt
        │
        ├── Decision proof DAG ── existing Market → Selection → Decision Support
        └── Due proof DAG ─────── existing Outcome → Evaluation → Evidence
                                                   → Assessment → Qualification

Market & PIT                         Research & Qualification
ProviderQualificationProtocol        FormalResearchCampaign
ProviderQualificationDecision   ───> predeclaration / generation / bindings
qualified historical visibility      due discovery / read-only inspection
```

There is no second Runtime, Research, Selection, Outcome, or Decision Support
owner. `market_regime_alpha.research_qualification` receives cohesive
`formal_campaign` modules. Provider qualification remains Market & PIT owned.
The sole target composition root exposes the new narrow applications and query
ports. Runtime dispatch and CLI cutover remain absent.

## Evidence ceiling

The only permitted WP-14 terminal claims are:

```text
WP14_EXIT_GATE = PASS
FORMAL_RESEARCH_ENGINEERING_READY = true
FORMAL_PIT = NOT_PROVEN
FORMAL_OOS = NOT_PROVEN
PROSPECTIVE_PROVEN = NO
PROVIDER_QUALIFIED = NO
ALPHA_PROVEN = NO
```

`ENGINEERING_REHEARSAL` is a first-class evidence class. A qualification made
from that class is capped at `INCONCLUSIVE` or `REJECTED`; it cannot create an
`ADMITTED` Provider decision or a qualified historical visibility row. Tests,
fixtures, local PostgreSQL campaigns, and WP-14 Verification use only that
class. `RECORDED_PROVIDER` is reserved for WP-15 real Provider bytes, real
Runtime capture lineage, and PostgreSQL times.

## Provider qualification Authority

### Protocol

`ProviderQualificationProtocol` is immutable and supersession-aware. It freezes:

- exact Provider and ProviderProduct revision;
- purpose: `HISTORICAL_PIT`, `PROSPECTIVE_DECISION`, or
  `OUTCOME_SETTLEMENT`;
- market/instrument scope, exchange calendar, timeframe, price basis, and
  DecisionTime rule;
- capture window and evidence cutoff;
- historical availability, known-time, revision/finality, coverage, and
  Outcome-path requirements;
- a contiguous non-empty `ProviderQualificationRequirement` roster;
- exact code/config Artifacts and provenance.

The closed requirement vocabulary is:

```text
COVERAGE
RAW_SOURCE_LINEAGE
HISTORICAL_AVAILABILITY
KNOWN_TIME
REVISION_FINALITY
PRICE_BASIS
TRADING_CALENDAR
MEMBERSHIP_STATUS
DECISION_REFERENCE
OUTCOME_PATH
```

Thresholds and minimum observation counts are relational fields, never JSON.
Protocol changes append a new revision and cannot supersede an already consumed
decision in place.

### Recorded observations and decision

Provider finality/publication observations bind a concrete `data_capture` and
its immutable Artifact identity. They record typed status, observation time,
code/config/provenance, and content hash. They do not assert qualification.

`CompleteProviderQualification` derives the complete Capture roster in the
protocol window from PostgreSQL. The caller cannot choose evidence members.
Every Capture, including Provider failures and explicit SourceGaps, remains in
the roster. Every protocol requirement produces exactly one result:

```text
SATISFIED | REJECTED | INCONCLUSIVE
```

The terminal decision is derived from the complete result roster:

```text
ADMITTED | REJECTED | INCONCLUSIVE
```

`ADMITTED` requires `RECORDED_PROVIDER`, a non-empty complete capture roster,
canonical Runtime `CAPTURE` receipts for every member, verified Artifacts,
declared availability, all mandatory typed observations, and every requirement
`SATISFIED`. Missing finality/publication evidence is `INCONCLUSIVE`, never an
optimistic default. A rehearsal is never admitted even when fixture values meet
all numerical thresholds.

### Qualified historical visibility

The default Market invariant remains:

```text
decision_visible_at = known_at
```

Qualification never edits a Capture or normalized fact. An explicit
`AdmitQualifiedHistoricalVisibility` command can append a companion Authority
row only for an exact normalized source whose Capture belongs to an admitted
`HISTORICAL_PIT` decision. The row freezes:

```text
exact source table identity
+ exact ProviderQualificationDecision
+ source_available_at
+ qualified_decision_visible_at
+ source/content hash
```

The source vocabulary is concrete and closed; rows have table-specific concrete
FKs rather than `(kind,id)`, nullable multi-owner FKs, or JSON subjects.
Separate child tables cover bar revisions, instrument-fact revisions,
classification-membership revisions, trading sessions, and source gaps.

Only a campaign-bound Formal PIT query port may use those rows. Ordinary Market,
Selection, Outcome, and current/as-of queries continue to use the original
`decision_visible_at`. Formal source resolution requires the campaign ID,
qualification decision ID, exact source identity, and requested DecisionTime.
Missing, ambiguous, superseded, out-of-scope, or post-cutoff admission fails
closed. The port never provides unrestricted current/latest data.

## Formal campaign predeclaration

`FormalResearchCampaign` is an immutable predeclaration owned by Research &
Qualification. It is needed because existing WP-11 Experiment registration
correctly follows Partition freeze, while the formal baseline must be frozen
before a LOCKED_OOS or PROSPECTIVE Partition is exposed.

The campaign freezes:

- class: `ENGINEERING_REHEARSAL` or `FORMAL_RESEARCH`;
- one primary hypothesis and exact Target version/hash;
- exact ProviderQualificationProtocol and ProviderProduct;
- exact Feature/Candidate, Context, Strategy, Portfolio, and Risk policy roots;
- declared cost assumptions as a contiguous typed relational roster;
- FIT, VALIDATION, LOCKED_OOS and optional PROSPECTIVE Partition plans,
  including calendar, Decision window, population, purge and embargo;
- purpose-specific EvaluationProtocol bindings and one
  ResearchQualificationPolicy;
- exact code/config Artifacts and provenance;
- generation, predecessor, count/hash, and PostgreSQL authoritative
  predeclared time.

The campaign has no caller-mutable JSON configuration. A changed Target,
Feature/Candidate weight, TopK, Context rule, Signal/Forecast rule, Strategy,
Portfolio/Risk threshold, cost assumption, partition boundary, purge/embargo,
metric, or acceptance floor requires a new campaign generation.

### Materialization and lock order

Existing authorities are created by their existing applications and then bound
through exact relational identities:

```text
campaign predeclared
< Provider qualification decision bound
< planned ResearchPartition frozen and bound
< complete Experiment registered and bound
< ExperimentRun opened
< EvaluationRun OPEN
< first Outcome access
```

The campaign validates that actual Partition and Experiment roots exactly match
the frozen plan and complete purpose roster. The first LOCKED_OOS or
PROSPECTIVE ExperimentRun binding transitions the campaign to
`PROTECTED_OPEN`; PostgreSQL rejects late or changed policy/partition bindings.
Existing WP-11 access guards remain the first-access Authority.

A campaign cannot bind an `ADMITTED` Provider decision unless both use formal
evidence. An engineering campaign may bind an `INCONCLUSIVE` rehearsal decision
so orchestration, failure, and inspection mechanics can be qualified without
raising the evidence ceiling.

## Controlled Runtime plans

WP-14 adds four Runtime step kinds:

```text
ACQUIRE_OUTCOME_INPUTS
EVALUATE
RECORD_EVIDENCE
QUALIFY
```

The Runtime domain and PostgreSQL deferred guards recognize two exact mandatory
DAG profiles.

Decision proof:

```text
CAPTURE → NORMALIZE_PIT → FREEZE_UNIVERSE → ASSESS_ELIGIBILITY
→ REGISTER_DATASET → BUILD_CANDIDATE_SET → OPEN_DECISION_RUN
→ ASSESS_CONTEXT → SIGNAL_AND_FORECAST → DECIDE_AND_RISK
```

Due proof:

```text
SETTLE_OUTCOME → ACQUIRE_OUTCOME_INPUTS → EVALUATE
→ RECORD_EVIDENCE → ASSESS_RESEARCH → QUALIFY
```

Each profile has exactly one required step of every listed kind, contiguous
ordinals, and direct `REQUIRED_SUCCESS` edges. A campaign binds an exact Runtime
Run only after reloading and validating its persisted Schedule/Run/Step/edge
roster. It does not dispatch business commands. Existing applications still
receive and validate their own Runtime claim; fence-first mutation, retry, and
unknown-commit behavior remain with each owner.

## Locked OOS safety

LOCKED_OOS readiness is established by four independent mechanisms:

1. immutable campaign baseline and append-only generations;
2. exact planned-to-actual Partition and Experiment reconciliation;
3. `PROTECTED_OPEN` rejecting late bindings or policy replacement;
4. WP-11 PostgreSQL order and global first-access ledger.

No campaign table can alter an existing WP-11 Partition, Experiment,
EvaluationProtocol, or access row. A materialized LOCKED_OOS campaign whose
baseline differs from an existing child fails rather than shrinking or
rebuilding the child roster.

## Prospective workflow and due discovery

PROSPECTIVE uses the existing canonical live-clock rule. HISTORICAL and REPLAY
Decision/commitment lineage is rejected; SHADOW is accepted only when the
existing live-clock contract accepts it. Partition freeze still requires:

```text
commitment_recorded_at < earliest_outcome_event_at
```

`DiscoverDueOutcomes` is a narrow read port over the exact campaign-bound
PROSPECTIVE Partition member roster. It returns every member with
`outcome_due_at <= database_now`, its exact commitment, whether a terminal
Outcome exists, and typed `DUE`, `SETTLED`, `MISSING`, or `NOT_DUE` state. It
does not settle, call a Provider, read current Outcome, or omit gaps.

The due Runtime profile then invokes the existing fenced Outcome, Evaluation,
Evidence, Assessment, and Qualification commands. Retry/recovery remains at
the command/Runtime boundaries. `AcquireOutcomeInputs` retains transaction-
bound value visibility and complete-member semantics.

## Read-only inspection and verification

`InspectFormalResearchCampaign` is a projection, never Authority. It reports:

- campaign/generation/class/state and exact baseline hashes;
- Provider protocol/decision/result and evidence class;
- planned/bound Partition roster and first-access counts;
- bound Experiment and Runtime plan identities;
- due, missing, settled Outcome counts;
- Evaluation, Evidence, Assessment, and Qualification states;
- prospective elapsed sessions/days;
- explicit blockers.

The read-only verifier recomputes Provider protocol/requirement/capture/result
hashes, campaign plan/binding hashes, persisted Runtime DAGs, protected-open
ordering, exact first-access state, due counts, and downstream closure. It uses
no Provider, filesystem, current/latest Outcome, Market reconstruction,
mutation, or caller-supplied roster. Passing is only:

```text
matched = true
mismatch_count = 0
```

## Transactions, concurrency, and recovery

Provider qualification and campaign each receive a narrow UoW. Existing owner
UoWs are not combined. Business commands use short PostgreSQL transactions,
fence first when participating in Runtime, deterministic advisory-lock order,
exact idempotency, bounded transient retry, and exact unknown-commit probe.
Network, Provider, Artifact byte, and filesystem work remains outside business
transactions.

Root/child rosters use child-first insertion plus deferred closure triggers.
Concurrent identical requests converge on one root and replay. Changed requests
fail closed. A rollback cannot leave a partial protocol, evidence roster,
campaign plan, binding roster, or Runtime binding.

## PostgreSQL obligations

The unreleased `MRA_REFOUNDATION_1 / 001_baseline.sql` is extended. PostgreSQL
directly enforces concrete/composite FKs, typed vocabulary, contiguous and
complete rosters, exact hashes, immutable history, supersession, evidence-class
admission ceiling, formal visibility linkage, campaign generation, protected
state, actual-plan equality, Runtime DAG profile, and append-only behavior.
FK-leading indexes support all campaign and qualification joins.

## Qualification boundary

WP-14 qualification must cover Domain/Application/PostgreSQL behavior,
composition, clean bootstrap/recreate, real concurrency, injected failures,
unknown commit, stale fence, read-only replay, representative plans, full
repository tests, Ruff, mypy, build, docs/navigation, architecture/import, and
diff checks against one exact implementation SHA.

The immutable Verification must say that fixtures prove mechanics only. It
must not contain a Provider admission, Formal PIT/OOS claim, prospective value
claim, Alpha result, Production claim, Runtime/CLI cutover, or Legacy deletion.

## Explicit non-scope

```text
real Provider campaign or empirical claim
Alpha optimization
Model / ModelVersion / Calibration
automatic broker trading or unattended execution
Production Admission
Runtime/CLI cutover
Legacy deletion
```

WP-15 may start only after WP-14 `EXIT_GATE_PASS` is merged into a freshly
fetched `origin/main`. WP-15 must use real Provider data and recorded timestamps;
failure of that external-evidence gate is a valid terminal blocker.
