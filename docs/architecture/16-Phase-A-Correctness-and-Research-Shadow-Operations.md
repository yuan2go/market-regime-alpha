# Phase A Correctness and Research Shadow Operations

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical boundary, cross-session State and Research Shadow operating architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Supersedes:** Cross-session and independent-component assumptions in 11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Superseded By:** None
> **Related Documents:** 10-Production-Decision-Lifecycle.md, 11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, 12-Canonical-Runtime-and-Legacy-Migration.md, ../operations/Research-Shadow-Operations-Runbook.md, ../status/Current-State.md
> **Code Evidence:** `application/authority_boundary.py`, `application/state_system/**`, `research/state_system/authority.py`, `application/shadow_research/**`, `application/research_evaluation/**`, `application/runtime_operations/**`, PostgreSQL migrations 038–042

## 1. Authority ceiling

This phase makes future Research Shadow samples structurally retainable. It
does not establish Live operation, prospective evidence, Alpha, formal PIT,
formal OOS, qualified Entry or trading authority.

The maximum engineering states are:

```text
CORRECTNESS_CONVERGENCE_ENGINEERING_PROVEN
CROSS_SESSION_STATE_ENGINEERING_PROVEN
RESEARCH_SHADOW_OPERATIONS_ENGINEERING_READY
MULTI_TARGET_EVALUATION_ENGINEERING_READY
```

Every current fixture or simulated-clock attestation remains
`prospective_proven=false`.

## 2. Canonical and Legacy execution boundary

The executable write path is owned by the Continuous Research Runtime,
Canonical Decision Lifecycle, `daily_decision` Entry contract, Decision System,
independent Risk, manual Fill ledger and Fill-derived Position authority.
Canonical Entry can emit only `REJECT` or `WAIT_CONFIRMATION`.

`daily_research`, the Legacy dashboard/strategy/risk path and
`migration.legacy` adapters are historical read, replay, migration or bounded
differential-comparison surfaces. They are not writable current authorities.
The ENTER-capable `daily_research.EntryAssessment` remains readable so old
Artifacts are not destroyed, but architecture tests reject imports from those
namespaces into Canonical executable composition. There is no second Entry,
Decision, Runtime, Risk, Position or Broker fact source.

## 3. Cross-session State Authority V2

`run_id` and `tick_id` still identify the observation that produced an
Artifact. They no longer identify the mutable State stream. `StateSeries`
content-addresses the stable combination of:

```text
State domain + logical scope + research family + authority mode
+ Universe policy + upstream model/configuration + State policy
```

Trading date, Run and Tick are deliberately absent. Each immutable
`state_series_link` binds them back to the produced State/Pool Artifact. One
`state_series_head` supplies CAS over the last link and rejects a stale
predecessor, non-advancing AsOfTime, stale same-Run Tick or fencing regression.

Consequently, for one unchanged series:

```text
D1 State
→ D2.previous_state_id = D1.state_id
→ D3.previous_state_id = D2.state_id
```

The same rule covers Friday to Monday and missing calendar days. Same-day
ticks advance by Tick sequence and AsOfTime. A policy, upstream model/config,
Universe policy, logical scope or authority-mode change creates a new Series
whose first Artifact has no predecessor. Dynamic Pool `previous_pool` means
the latest effective Pool in the same stable Series, not merely the previous
Tick or previous calendar day.

V1 State tables and Readers remain immutable. V2 adds links and heads; it does
not rewrite V1 history. Canonical V2 evaluation requires the previous Artifact
to carry the same Series ID. Legacy V1 evaluation retains its historical
within-Run checks for replay only.

## 4. State Policy Authority

`StateTransitionPolicy` and `DynamicPoolPolicy` are immutable,
content-addressed and versioned. They carry transition thresholds,
confirmation, dwell, hysteresis, coverage, missing-data behavior and every
domain classification cutoff used by the Canonical State evaluators. Dynamic
Pool additionally binds allowed states, evidence coverage, dwell and
material-change rules.

The explicit `engineering-v1` factories are labelled
`ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH`. A Canonical V2 evaluator rejects a
missing policy, a lineage ID/version/hash mismatch or an unimplemented
missing-data behavior. State Artifacts, frozen Shadow Decisions and Evaluation
V2 slices preserve policy references. Upstream model configuration, State
transition policy and Dynamic Pool policy remain distinct identities.

## 5. Multi-horizon Outcome Target Authority

`OutcomeTargetProtocol` owns ordered content-addressed `TargetDefinition`
records. The engineering protocol defines T+1 Open, 09:45, 10:00, 10:30,
11:30 and Close without selecting a winner. Each definition states its label
interval, checkpoint, return reference, barriers, MFE/MAE interval, required
market data, tradability, corporate-action and missing-quote policies.

`TargetedShadowOutcome` derives factual labels from one frozen Decision and one
existing Outcome V1 settlement. Missing checkpoints remain missing; raw returns
fail closed when corporate-action handling requires adjusted evidence; no
future quote can enter an earlier label interval. Label intervals are stored so
future purging and embargo can be derived rather than hard-coded. One Decision
may have multiple protocol-bound settlements without changing the Decision.

## 6. Research Shadow Operating Loop

`ResearchShadowOperations` orchestrates existing owners:

```text
schedule Session
→ attach the existing Canonical Continuous Runtime
→ freeze its immutable Research/Shadow Summary
→ mark Outcome pending
→ settle factual Outcome V1 and Targeted Outcome V2
→ record Prospective Evidence Attestation
→ build frozen Evaluation Panel V2
→ report or replay
```

Schedule, attach, freeze, pending, settle and publication are idempotent where
the semantic command is identical. Session transitions use optimistic version
CAS. Failed sessions can resume; invalidated and settled sessions are terminal.
An existing V1 settlement can be replay-verified and completed with the V2
Target/Attestation layers after a crash. The service never reacquires Runtime
data and has no Order, Fill, Broker or Position mutation dependency.

## 7. Prospective Evidence Attestation

The attestation binds the frozen Decision/Summary, Run/Tick, source acquisition
receipts, Outcome settlement, code revision, runtime mode, clock mode and
runtime origin. It checks that freeze precedes Outcome availability, but a
timestamp comparison alone is insufficient. Replay, fixture, simulated clock,
missing source receipt or non-Live origin is ineligible.

The V1 engineering schema enforces `prospective_proven=false` in both domain
validation and PostgreSQL. `ENGINEERING_ATTESTABLE` means the supplied facts
meet the structural checks; it is not a prospective PASS. A later separately
approved authority must define how trusted production identity can promote
evidence.

## 8. Frozen Research Panel V2

Evaluation V1 remains readable. V2 freezes the complete Pool cross section and
Candidate evaluation status, including eligible/evaluated symbols, included or
excluded Pool state, selection/rejection, rank and score. It retains raw factor
exposure, any actually available normalized exposure/contribution, gates,
Market/ETF/Theme/Capital State, Signal/Forecast references, Model/configuration,
State Policy, Target Protocol and Outcome labels.

Unavailable normalized or contribution values are absent rather than
fabricated. The panel is an immutable research authority for later ablations;
its creation performs no Alpha analysis and grants no model qualification.

## 9. Query and observability projection

The read-only DAG assigns Dataset/Feature, State/Pool/Candidate, Signal,
Forecast, Summary/Governance and Shadow/Outcome/Evaluation nodes to their real
owners. A trading-date inspection joins Runtime to Summary, frozen Decision,
Outcome, Targeted Outcome, Attestation and Evaluation Panel.

Candidate count and available minute coverage come from their owning facts.
Fence/replay failure counts and any unavailable measurement are
`NOT_OBSERVED`, never a fabricated zero. These projections cannot enter a
decision.

## 10. PostgreSQL migrations and repair

Migrations are append-only:

| Migration | Authority |
|---|---|
| 038 | State Policy, State Series, immutable links and CAS head |
| 039 | Target Protocol, definitions and Targeted Outcome V2 |
| 040 | Prospective Evidence Attestation |
| 041 | Frozen Research Evaluation Panel V2 |
| 042 | Shadow Decision V2 State Policy references |

Rollback means stop new V2 writes and use historical Readers. Published V2
facts are not deleted or rewritten. A defect is repaired by a new migration,
new policy/protocol version, new Session or explicit invalidation.
