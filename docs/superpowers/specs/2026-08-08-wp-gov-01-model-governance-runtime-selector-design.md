# WP-GOV-01 Model Governance and Runtime Selector Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved implementation design for WP-GOV-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Baseline:** `feat/continuous-research-runtime@bd868b06df13c4a657a169e5039c91c1d69a5ef9`
> **Related Documents:** ../../architecture/09-Platform-Architecture-V2.md, ../../architecture/10-Production-Decision-Lifecycle.md, ../../roadmap/work-packages/WP-PGSQL-01-PostgreSQL-Authority-Only.md, ../../roadmap/work-packages/WP-DECISION-01-Daily-Decision-Closure.md

## 1. Objective

WP-GOV-01 extends the existing PostgreSQL Model Registry into the sole model
governance and Runtime-selection authority. It separates five facts:

```text
Model Exists
!= Lifecycle State
!= Qualified for a Runtime Purpose
!= Selected for this Runtime invocation
!= Authorized for Production Decision
```

The delivery must remove the in-process Registry constructed by
`DailyLoopRunner`, stop trusting caller-authored `model_qualification` in the
Decision Runtime, and persist every accepted or rejected selection. It does not
qualify any model for Production, unblock Entry, or create Order, Broker, Fill or
automatic execution authority.

## 2. Audited baseline facts

- `ModelRegistry`, `PersistentModelRegistry` and
  `PostgresModelRegistryRepository` already own immutable model definitions,
  lifecycle validation, CAS, command idempotency and append-only transition
  history.
- Migration 001 persists registration, transition, experiment and command state,
  but does not represent qualification evidence, selection policy, deployment
  lanes, governance revision or Runtime selection receipts.
- `DailyLoopRunner.finalize_run()` constructs `ModelRegistry()` and registers
  B0/B1 definitions inside the process before publishing PredictionRuns.
- B0/B1 model IDs are stable, while the current helper embeds the daily Dataset
  Universe identity into each `ModelDefinition`. A persistent registry therefore
  needs an explicit stable-version versus runtime-lineage separation.
- `SummaryCandidate.model_qualification` is deserialized from caller JSON. Both
  Portfolio and Independent Risk currently treat that field as authoritative.
- Decision lineage contains model IDs and configuration IDs, but not registry
  versions, qualification evidence, assignment authority or a selection receipt.
- The State child persists exact stage identities; model-bearing Signal and
  Forecast evidence reaches the Decision child through those authorities. The
  Decision Runtime is therefore the current enforceable admission seam for those
  outputs.

## 3. Ownership and module boundaries

The existing `platform` bounded context remains the sole owner.

```text
platform/model_registry.py
  existing model definition and lifecycle rules

platform/runtime_governance.py
  immutable lineage, qualification evidence, policy, assignment and selection contracts

platform/postgres_governance.py
  existing Registry adapter, now bound to the shared governance revision ledger

platform/postgres_runtime_governance.py
  unified Registry extension that evaluates and persists qualification,
  assignment, accepted/rejected selection and historical replay

application/daily_loop/runner.py
  requests governed B0/B1 Research selection before model execution

application/decision_system/runtime.py
  derives candidate qualification from persisted selection evidence before Summary/Portfolio/Risk
```

No new registry, scheduler, Journal or mutable Artifact store is introduced.

## 4. Stable model version and runtime lineage

`ModelDefinition` remains the immutable registered version definition. A new
`ModelVersionLineage` binds its definition hash to:

- stable implementation reference and code revision/hash;
- stable Target and declared Universe contract;
- exact FeatureDefinition IDs;
- result-affecting configuration identity/hash;
- declared supported DataEligibility values;
- validation protocol references.

Daily Dataset, Universe snapshot and FeatureMaterialization identities are not
part of the stable model version. They enter a `RuntimeModelLineage` for each
selection request. The Selector validates:

- model ID and registered definition hash;
- stable Target, FeatureDefinition, configuration and implementation identity;
- runtime Dataset/Universe/FeatureMaterialization identities and hashes;
- DataEligibility compatibility;
- exact request/State/Decision configuration references.

The selection receipt connects the stable definition to the exact runtime
lineage. This removes the cross-day identity conflict without weakening lineage.
Historical PredictionRun schemas remain readable.

## 5. Lifecycle, evidence and qualification

Existing `ModelLifecycleStatus` remains unchanged and is not treated as a
qualification result.

Qualification evidence is append-only and content-addressed. Evidence kinds are
extensible and initially include:

```text
DATASET_INTEGRITY
FEATURE_LINEAGE
IMPLEMENTATION_REPRODUCIBILITY
BACKTEST_VALIDATION
FORMAL_PIT
FORMAL_OOS
ECONOMIC_VALIDATION
COST_CAPACITY
SHADOW_OPERATION
OPERATOR_APPROVAL
```

Each evidence record binds the model definition, Dataset/Feature/Config/Code
lineage, validation protocol, evidence Artifact identity/hash, availability,
actor and reason. Outcomes are `SATISFIED`, `FAILED` or `REVOKED`; later records
do not rewrite earlier evidence.

A versioned `ModelGovernancePolicy` defines one Runtime purpose:

```text
RESEARCH
BACKTEST
SHADOW
PRODUCTION_DECISION
```

It declares allowed lifecycle states, required evidence kinds and allowed data
eligibilities. A `ModelQualificationDecision` is an explicit, append-only
governance action under one policy and exact evidence set. Evidence may make a
model eligible for review, but never automatically transitions lifecycle,
assigns Champion or authorizes Production.

WP-GOV-01 may exercise Research qualification in fixtures. No implementation,
migration or bootstrap action creates a Production qualification.

## 6. Champion and Challenger assignment

An assignment is scoped by `runtime_scope + model_slot + runtime_purpose` and
has lane `CHAMPION` or `CHALLENGER`.

- exactly one active Champion may exist for a scope/slot/purpose;
- zero or more active Challengers may exist;
- assignment requires an explicit actor, reason and approval reference;
- suspend and replace append events and advance CAS version;
- replacement activates the new assignment and closes the old assignment in
  one transaction;
- Challengers are recorded in the selection receipt but cannot determine the
  authoritative output model.

Current slots are stable strings so later stages do not require a Registry
schema rewrite. WP-GOV-01 uses `DAILY_B0`, `DAILY_B1`, `STATE_SIGNAL` and
`STATE_FORECAST`.

## 7. Governance revision and PostgreSQL authority

Migration 027 adds:

```text
model_governance_action
model_version_lineage
model_qualification_evidence
model_governance_policy
model_qualification_decision
model_runtime_lineage
model_runtime_assignment
model_selection_receipt
```

Every governance mutation appends an action with a monotonically increasing
global revision. One global transaction advisory lock serializes action commit
order, global CAS and selection snapshots; scope locks and optimistic versions
add aggregate-level concurrency control. Champion state is reconstructed from
append-only assignment/supersession events under those locks rather than a
mutable active-row flag. Foreign keys and lookup indexes cover authoritative
model/policy/assignment references. History, evidence, decisions, events and
receipts are protected from UPDATE/DELETE by PostgreSQL triggers.

The mutable registration and assignment projections are rebuildable from their
append-only histories. Transactions contain no network or file IO.

## 8. Runtime Selector

For every required slot, `ModelRuntimeSelector.select()`:

1. opens a PostgreSQL transaction and reads the latest governance revision;
2. resolves exactly one active Champion and all active Challengers;
3. loads and reconstructs Registry lifecycle history;
4. loads stable version lineage, policy and latest explicit qualification;
5. validates every evidence identity and runtime-lineage field;
6. verifies purpose, lifecycle, temporal effectiveness and data eligibility;
7. writes an accepted or rejected `ModelSelectionReceipt`;
8. returns only the Champion as authoritative output.

Missing state and integrity errors become typed rejection receipts where the
database remains writable. Database unavailability raises
`DATABASE_UNAVAILABLE`; no in-memory or stale fallback exists.

The receipt includes the request hash, governance revision, policy, assignment
and version, selected model and definition hash, qualification/evidence
identities, Challenger identities, exact runtime lineage, reason codes and the
separate `production_authorized` boolean.

## 9. Canonical Runtime integration

```text
PostgreSQL Registry + lineage + evidence + policy + assignment
→ Runtime Selector
→ persisted selection receipt
→ selected Champion implementation / exact upstream model output
→ State receipt and model-bearing evidence
→ Decision Runtime revalidates selection receipt and model IDs
→ derived model qualification
→ Daily Summary
→ Research Portfolio Proposal
→ Independent PostgreSQL Risk reload
→ Decision Runtime receipt with selection ID/hash/revision
```

`DailyLoopRunner` requires a PostgreSQL-backed Selector when it reaches B0/B1.
It resolves each Champion, matches it against the bounded executable B0/B1
catalog, selects that exact runtime lineage, and publishes only selected Models.
An assigned implementation outside that catalog produces durable rejection
evidence and fails closed. Governed Prediction Artifacts embed and verify the
selection receipt and the exact Dataset, feature/materialization pairs, config,
code, validation-protocol and DataEligibility lineage. Source-freeze-only paths
remain model-independent.

The Decision Runtime requests/validates Signal and Forecast selection before
Summary Preview. Caller qualification is ignored and replaced with the derived
result. State Receipt schema V2 and DecisionLineage schema V3 bind the
PostgreSQL-derived DataEligibility used by that request; legacy receipts that do
not carry it remain readable but map to `UNQUALIFIED`. A forged `QUALIFIED`
value cannot make a rejected model eligible.

## 10. Replay and determinism

Selection receipts are immutable facts. Replay does not query the current
assignment as a substitute for historical state. It reconstructs Registry,
policy, qualification, assignment and evidence as of the receipt's governance
revision, re-evaluates the exact request and requires byte-equivalent semantic
output.

A later promotion, demotion, suspension or replacement changes new selection
results only. It cannot mutate a historical receipt. `replay-selection`
reconstructs the historical PostgreSQL state in place and fails on any semantic
identity mismatch. Daily replay replays each embedded selection receipt before
accepting governed Prediction Artifacts. Isolated Decision replay exports the
minimal point-in-time governance bundle for its receipt IDs, imports it into the
isolated PostgreSQL schema, and independently re-executes each selection.

## 11. Fail-closed conditions

Selection is rejected for at least:

- missing Registry, lineage, policy, qualification or Champion;
- duplicate active Champion or corrupt assignment history;
- lifecycle not allowed, `SUSPENDED` or `RETIRED` model;
- missing, failed, revoked or mismatched evidence;
- stale qualification relative to policy/model/evidence revision;
- model/definition/version, Dataset, Universe, Feature, Config, Code or
  validation lineage mismatch;
- runtime DataEligibility outside policy/model declaration;
- CAS/version/idempotency conflict;
- historical reconstruction mismatch;
- database unavailable or PostgreSQL integrity error.

No rejection path chooses a Challenger, creates a default model, trusts caller
qualification, or reuses an unverified stale selection.

## 12. CLI and inspection

The `model-governance` CLI provides JSON commands for:

- list/show registered versions and lifecycle;
- register stable lineage;
- record qualification evidence;
- register/inspect policy;
- issue qualification decision;
- assign Champion/Challenger;
- suspend or replace assignment;
- inspect selection receipt and governance revision;
- replay one selection receipt.

All write commands require actor, reason and idempotency key. Promotion and
Production approval additionally require explicit approval references.

## 13. Verification

Tests exercise public seams with real PostgreSQL 16:

- migration 001→027 and 026→027 replay;
- Registry restart, CAS, concurrent assignment and command idempotency;
- qualification evidence and policy gates;
- Champion/Challenger, suspension and replacement;
- accepted and rejected selection receipts;
- as-of governance revision and historical replay after replacement;
- exact Dataset/Feature/Config/Code/Validation mismatch rejection;
- DailyLoop removal of the in-memory Registry path;
- forged Decision candidate qualification rejection;
- Decision receipt binding to selection evidence;
- no Production qualification and no Challenger output contamination;
- package contents, full pytest, Ruff, mypy, build and diff checks.

## 14. Rollback and forward repair

Migration 027 is forward-only for material environments. To roll back Runtime
behavior, stop new model-bearing runs and retain all governance/selection tables
read-only. Correct defects with a forward migration and replay projections from
append-only actions. Do not delete or rewrite selection evidence.

## 15. Evidence ceiling and next phase

WP-GOV-01 completion means governance mechanics and Runtime enforcement are
implemented and locally verified. It does not mean any model has formal PIT,
formal OOS, economic validity, Shadow evidence, profitability or Production
trading authority.

The next dependency-ready work package is WP-PIT-01 only if Runtime enforcement,
PostgreSQL integration, replay, concurrency and full repository quality gates
pass at the final commit.
