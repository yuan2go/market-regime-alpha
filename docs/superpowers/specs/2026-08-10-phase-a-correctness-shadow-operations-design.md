# Phase A Correctness Convergence and Research Shadow Operations Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved Phase A implementation design derived from the 2026-08-10 user directive
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../architecture/12-Canonical-Runtime-and-Legacy-Migration.md, ../../status/Current-State.md, ../../status/Capability-Matrix.md, ../../status/Gap-Register.md
> **Code Evidence:** Target-state design; implementation evidence is recorded separately after the quality gate.

## 1. Objective and evidence ceiling

Phase A closes correctness gaps that could contaminate future Research Shadow
samples. It does not qualify data, tune economic parameters, validate Alpha,
qualify Entry, mutate a Position, invoke a Broker, or authorize production.

The maximum claims are:

```text
CORRECTNESS_CONVERGENCE_ENGINEERING_PROVEN
CROSS_SESSION_STATE_ENGINEERING_PROVEN
RESEARCH_SHADOW_OPERATIONS_ENGINEERING_READY
MULTI_TARGET_EVALUATION_ENGINEERING_READY
```

Fixture, replay and simulated-clock evidence remain explicitly non-prospective.

## 2. Code facts

- `ContinuousResearchTickRunner` is the current scheduled daily Runtime owner.
  Controlled Operation, State System and Decision System are bounded children,
  not competing daily runtimes.
- `CanonicalDecisionLifecycleRunner` remains the downstream human-in-the-loop
  lifecycle continuation. It does not produce the daily Shadow sample.
- `daily_decision.entry.EntryAssessmentState` is the canonical Entry plumbing
  contract and can emit only `REJECT` or `WAIT_CONFIRMATION`.
- `daily_research.EntryState.ENTER` is a historical contract. No current
  canonical composition imports `daily_research`, but the boundary is not yet
  expressed as a machine-checked catalog.
- State V1 stores immutable Observation, State and Transition rows with
  `previous_state_id`. Its current pointer is scoped by
  `run_id:logical_scope`, so the chain stops at each trading date.
- State transition thresholds and Dynamic Pool gates are content-hashed, but
  FreeData composition constructs their values locally and represents the
  transition policy as model configuration.
- Shadow Session, frozen Shadow Decision, Outcome V1 and Evaluation Dataset V1
  are independent authorities with CAS/append-only behavior; no application
  service owns their end-to-end operating loop.
- Outcome V1 intentionally carries `NOT_PROSPECTIVE_EVIDENCE` and hard-wires a
  next-session checkpoint set. Evaluation V1 includes selected candidates.
- Runtime Query assigns every State pipeline stage to `STATE_SYSTEM`, including
  Signal and Forecast, and Observability reports some inferred or fixed-zero
  metrics.
- The current packaged PostgreSQL migration head is `037`.

## 3. Alternatives

### 3.1 Selected: append-only V2 authority overlay

Keep V1 Artifacts and Readers byte-compatible. Add content-addressed State
Policy and State Series authorities, V2 heads, Target Protocol and targeted
Outcome authorities, Prospective Attestation, Research Panel V2 and an
application-level Shadow operating loop. Existing Runtime and bounded owners
write the new records.

This approach preserves historical identity, avoids a second Runtime and makes
policy/target lineage explicit.

### 3.2 Rejected: mutate V1 payloads and pointers in place

Adding fields to all V1 semantic payloads or repurposing V1 pointer rows would
change historical content hashes and make old replay dependent on a migration.
That conflicts with immutable historical identity.

### 3.3 Rejected: create a new Shadow Runtime

A second scheduler or runtime journal would duplicate acquisition, recovery and
decision ownership. Shadow operations must orchestrate the existing Continuous
Runtime and its current bounded authorities.

## 4. Canonical and Legacy execution boundary

A typed, read-only authority catalog declares the executable boundary:

```text
Canonical daily runtime       = Continuous Research Runtime
Canonical lifecycle runtime   = Canonical Decision Lifecycle continuation
Canonical daily decision      = Decision System / ResearchDailySummary
Canonical Entry               = daily_decision Entry plumbing
Legacy daily decision model   = daily_research (read/replay/migration only)
Legacy strategy application   = dividend_t / legacy web compatibility only
```

Architecture tests scan imports, installed entry points and the canonical Entry
enum. Canonical application/composition modules may not import
`daily_research`, `dividend_t`, or executable Legacy producers. Historical
Readers and migration adapters remain callable only through the declared
compatibility boundary. No Legacy `ENTER` can enter Summary, Shadow Decision,
Outcome, Evaluation, Decision System or Production authority.

## 5. Cross-session State Authority V2

### 5.1 Stable State Series

`StateSeries` is content-addressed from:

- State domain and logical scope;
- research/strategy family and Runtime authority mode;
- stable Universe policy identity/hash;
- State model ID/version and model-configuration ID/hash;
- State transition policy ID/hash.

It excludes trading date, run ID, tick ID, observation ID and code revision.
Changing model configuration, State policy, Universe policy or research family
therefore creates a new series and an explicit reset. Daily membership data and
ordinary observations do not.

Every V2 State Artifact still binds the exact run, tick, trading date through
the run, observation/evidence, model/configuration, source Artifacts and
available/as-of times. Its lineage additionally binds State Series and State
Policy references.

### 5.2 V2 head and fencing

V1 `state_current_pointer` remains untouched. A V2 head is keyed by stable
`series_id`. The append transaction:

1. validates the active Continuous Tick claim;
2. locks the State Series head;
3. requires the caller's expected predecessor to match the head;
4. rejects an observation whose as-of time does not advance;
5. applies fencing-token monotonicity only within the same run;
6. accepts a lower token for a later run because tokens are run-scoped;
7. appends the immutable State/Transition and advances the head atomically.

This yields same-day Tick chaining and D1 → D2 → D3 / Friday → Monday
continuity. Non-trading and missing days append nothing; the next valid trading
observation consumes the latest effective series head. Replay reads immutable
series links and verifies the same predecessor chain without advancing a live
head.

Dynamic Pool becomes its own stable series. `previous_pool_id` means the latest
materially effective Pool in that same series, regardless of Tick or trading
date. A no-material-change Tick references the prior Pool and does not create a
new version.

## 6. State Policy Authority

`StateTransitionPolicy` and `DynamicPoolPolicy` are immutable,
versioned/content-addressed contracts. They own thresholds, confirmation,
dwell, hysteresis, coverage, missing-data behavior, rotation-state gates and
material-change policy. Model configuration no longer owns these values.

The engineering V1 values remain an explicit seeded policy; they are not
optimized or presented as economic truth. Policy ID/version/hash is persisted
and bound into every V2 State/Transition/Pool lineage, Shadow Decision and
Evaluation V2 slice. Runtime composition receives a policy bundle rather than
constructing numeric parameters inside stage functions.

## 7. Multi-horizon Target and Outcome Authority

`OutcomeTargetProtocol` is an immutable protocol containing ordered
`TargetDefinition` values. Each target declares:

- target ID/version and label start/end interval;
- return reference and checkpoint convention;
- optional barriers and MFE/MAE interval;
- required market-data timeframes;
- tradability, corporate-action and missing-quote policies.

The engineering default contains T+1 Open, 09:45, 10:00, 10:30, 11:30 and
Close. It is a protocol fixture, not a selected winner.

`TargetedShadowOutcome` derives factual labels from an already frozen Shadow
Decision and one verified future Dataset. It rejects future data whose
availability does not follow the freeze, computes only within each declared
label interval and records partial/unavailable labels explicitly. The same
Decision may have multiple settlements under different Target Protocol hashes.
Outcome V1 and its Reader remain unchanged.

The exact label interval is stored so later Purging and Embargo can be derived
from the target rather than from a hard-coded horizon.

## 8. Research Shadow Operating Loop

`ResearchShadowOperationsService` orchestrates existing owners:

```text
schedule → preflight/mark running → attach frozen Summary
→ outcome pending → V1 factual settlement + targeted settlement
→ Evaluation V2 → settled report/replay
```

The service and one `research-shadow` CLI expose schedule, run,
attach-summary/freeze, outcome-pending, settle, build-evaluation, report,
replay, resume and invalidate. Commands use existing PostgreSQL repositories,
CAS versions and immutable input files. Duplicate invocations return the same
Artifact when semantic content matches and reject conflicting content.

Crash recovery resumes only legal non-terminal states. Invalidated sessions
cannot settle. Missed or non-trading T+1 is recorded as unavailable rather
than fabricated. `NO_ACTION`, `WATCH`, `RESEARCH_CANDIDATE`,
`DATA_INSUFFICIENT`, `MODEL_NOT_QUALIFIED_FOR_MODE` and an empty Candidate set
remain valid frozen outcomes. The loop has no Order, Fill, Broker or Position
port.

## 9. Prospective Evidence Attestation

`ProspectiveEvidenceAttestation` binds the frozen Decision, Outcome,
acquisition/source receipts, run/tick, runtime mode, clock mode, code revision
and freeze/availability times. It verifies temporal ordering and rejects
Replay, Fixture or Simulated-clock impersonation.

Phase A cannot emit `PROSPECTIVE_PROVEN`. Even when engineering checks pass,
the status is `ENGINEERING_CHECKS_PASSED_NOT_PROSPECTIVE` or
`AWAITING_GOVERNANCE_ATTESTATION`; `prospective_proven` is invariantly false.
A future authenticated trusted-clock/source authority may add a separately
approved governance PASS without rewriting these records.

## 10. Research Evaluation Dataset V2

V2 freezes a complete Research Panel rather than only selected candidates. A
row records:

- Universe eligible/evaluated state;
- Dynamic Pool inclusion/exclusion, gate and rank;
- Candidate status/rank/score;
- raw/normalized factor exposure and contribution, including explicit
  `NOT_OBSERVED` values;
- Market/ETF/Theme/Capital State references;
- Signal and Forecast references/status;
- model/configuration, State Policy and Target Protocol references;
- targeted factual labels and their availability.

The builder joins only exact frozen owner Artifacts. It accepts explicit factor
exposure evidence so later Signal versions can populate richer values without a
schema rewrite. It never runs arbitrary SQL to reconstruct a panel and does not
calculate Alpha or choose a target. Dataset V1 remains readable and registered.

## 11. Runtime read model and Observability

The DAG gains Shadow Session, Shadow Decision, Outcome, Target Protocol,
Evaluation Dataset and Prospective Attestation node types. Owner mapping is
explicit:

```text
Dataset       MARKET_DATA_DATASET
Feature       FEATURE_MATERIALIZATION
State/Pool    STATE_SYSTEM
Candidate     CANDIDATE_DISCOVERY
Minute        CONTROLLED_OPERATION
Signal        SIGNAL_SYSTEM
Forecast      FORECAST_SYSTEM
Governance    MODEL_GOVERNANCE
Summary       DECISION_SYSTEM
Shadow        SHADOW_RESEARCH
Outcome       OUTCOME_AUTHORITY
Evaluation    RESEARCH_EVALUATION
Attestation   PROSPECTIVE_ATTESTATION
```

Metrics count actual Candidate records/members, coverage observations,
fence-rejection events and replay verification failures where owner evidence
exists. An unavailable metric is emitted as `UNKNOWN`/`NOT_OBSERVED`, never a
fabricated zero.

## 12. Schema, compatibility and repair

New migrations continue at 038 and are append-only. New tables use explicit
foreign keys to existing run/tick, Shadow Decision, Outcome and Dataset owners;
updates/deletes are rejected. V1 tables and migrations are not edited.

Rollback is application rollback: old Readers continue to function and ignore
new tables. If a V2 write fails before head advance, retry reuses immutable
rows. If it fails after an owner Artifact exists but before a workflow event,
resume reloads and validates that Artifact before repairing the missing event.
Conflicting identity or stale CAS requires forward repair through a new
command/policy/series; history is never rewritten.

## 13. Acceptance evidence

Focused PostgreSQL tests cover D1 → D2 → D3, Friday → Monday, missing/non-
trading days, same-day ticks, series reset, stale predecessor, run-scoped
fencing, restart/replay, policy lineage, multiple Target protocols, incomplete
quotes, corporate actions, Shadow CAS/recovery/invalidation, full Panel joins,
owner correctness and unknown metrics.

The final gate is the repository's frozen dependency sync, full pytest, Ruff,
mypy, package build, documentation/link checks and `git diff --check`. The
SHA-bound Engineering Verification record reports local commands and treats
unobserved GitHub Actions as `CI_NOT_RUN`.
