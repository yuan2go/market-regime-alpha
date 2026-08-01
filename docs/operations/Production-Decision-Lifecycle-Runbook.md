# Production Decision Lifecycle Runbook

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Operational procedure for the human-in-the-loop production decision lifecycle  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/10-Production-Decision-Lifecycle.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../specs/Production-Decision-Lifecycle-Requirements.md  
> **Code Evidence:** Target-state runbook. Commands and components that do not yet exist are labelled as planned.

## 1. Operating boundary

This runbook governs research, deterministic replay, simulation, manual confirmation, manual order/fill recording, position projection and review.

It does not authorize unattended broker operations. Until a separate execution decision is accepted, every actual trade remains a human action recorded by the system.

## 2. Operating modes

| Mode | Purpose | External data | Position mutation |
|---|---|---|---|
| Fixture | deterministic development and tests | none | simulated only |
| Replay | recompute immutable historical evidence | none during replay | simulated or historical manual ledger |
| Shadow | current evidence and decisions without automated execution | current providers | manual record only |
| Manual production support | operator uses approved plan and records actual action | current providers | manual fill ledger |
| Automated broker mode | not authorized | future | not available |

## 3. Daily operating sequence

### 3.1 Pre-run checks

Before a scheduled decision run:

1. Confirm the configured Decision Time and trading date.
2. Confirm provider credentials and connectivity without printing secrets.
3. Confirm artifact and runtime storage have sufficient capacity.
4. Confirm the Runtime Journal is writable.
5. Confirm no unresolved position reconciliation blocks new exposure.
6. Confirm the active model/configuration identities.
7. Confirm hard-risk limits and strategy pause state.
8. Confirm system time and timezone.

A failed pre-run check shall stop the run or mark it blocked. Operators must not bypass a failed evidence or risk check by copying a previous result.

### 3.2 Data acquisition and freeze

Current implemented path:

```text
History Source Frozen
→ Security Status Source Frozen
→ Decision Quote Source Frozen
→ Source Archive and SourceManifest
```

Operational rules:

- repeat the same RunRequest rather than creating a new semantic request after a transient failure;
- allow the Runtime Journal to resume from the recorded stage;
- do not delete an orphan artifact before recovery code has attempted to verify and claim it;
- do not edit source archives or manifests;
- if provider status is unknown or late, accept `DATA_BLOCKED` or symbol-level rejection.

### 3.3 Research run

Planned operational sequence:

```text
Verified Daily Artifact
→ Operational Research Adapter
→ PlatformResearchRunner
→ ResearchLayerArtifact
```

Operator checks:

- SourceManifest ID and Decision Time match the daily run;
- ResearchInputBundle contains only evidence available by Decision Time;
- data eligibility remains EXPLORATORY unless a separately approved authority exists;
- Candidate population is complete and every symbol has an explicit status;
- Theme or Capital insufficiency is not bypassed.

### 3.4 Signal and forecast

Planned checks:

- SignalSnapshot references the selected CandidateSet and exact feature evidence;
- Signal state is not treated as an order;
- PathForecast target and horizon are the intended protocol;
- probability fields are absent unless calibration status permits them;
- ambiguous and missing target states remain visible.

### 3.5 Opportunity and thesis review

The operator shall review:

- market permission and exposure ceiling;
- theme state and concentration;
- capital state and confidence;
- candidate reasons and rejections;
- signal confirmations and contradictions;
- expected reward, adverse excursion and horizon;
- thesis invalidation conditions;
- opportunity expiry.

The operator may reject an opportunity without changing its evidence. Rejection shall record actor, time and reason.

### 3.6 Portfolio and risk

Before manual action:

1. Load current authoritative positions and available cash.
2. Generate target positions from approved theses.
3. Apply gross, per-symbol, per-theme, liquidity and loss-budget limits.
4. Apply T+1 and available-quantity rules.
5. Persist RiskDecision with the exact limit snapshot.
6. Stop if risk rejects, times out or is unavailable.

No operator or strategy may convert a rejected decision into an approved system action. A human may still act outside the system, but that deviation must be recorded explicitly and shall not be represented as system approval.

### 3.7 Manual action recording

For every actual action:

- create or reference an approved ManualTradeRecord;
- record intended symbol, side, quantity and expected range;
- record operator identity and confirmation;
- record actual fills individually;
- record fees where available;
- use the external fill/order identity as an idempotency input when possible;
- represent cancellation, rejection and partial fill explicitly;
- never edit a previous fill; use a correction record.

### 3.8 Position reconciliation

After fills:

1. Rebuild PositionSnapshot from the complete fill ledger.
2. Compare against the operator or broker statement when available.
3. If quantity, side, cost or fill history differs, enter `RECONCILIATION_REQUIRED`.
4. Block new exposure for the affected account/symbol until resolved.
5. Record the resolution as append-only evidence.

### 3.9 Holding and exit review

For each open position, review:

- current thesis state;
- market, theme and capital change;
- current signal and overheat state;
- MFE and MAE;
- time invalidation;
- T+1 and execution availability;
- portfolio concentration and alternative opportunity cost.

ADD requires a still-valid thesis and a fresh portfolio/risk decision.

If exit is recommended but execution is unavailable because of T+1, suspension or price limit, record the pending exit condition and continue risk monitoring.

### 3.10 End-of-day review

- verify all DailyRun and application stages reached a terminal or explicitly failed state;
- verify artifact checksums;
- verify no unresolved fill or position mismatch;
- settle outcomes whose evidence is available;
- publish review and attribution artifacts;
- record provider, model and operational incidents;
- preserve all source and decision artifacts.

## 4. Incident procedures

## 4.1 Provider unavailable

1. Keep the same semantic RunRequest.
2. Allow built-in retry/resume behavior.
3. Do not substitute stale data as current without an explicit stale-data contract.
4. If the Decision Time window is missed, publish the correct blocked state.
5. Record provider, stage, error and recovery evidence.

## 4.2 Artifact checksum mismatch

Severity: critical.

1. Stop all downstream processing of the artifact.
2. Mark the run or workflow failed.
3. Preserve the corrupted object for investigation; do not overwrite it.
4. Compare source archive, manifest, receipt and artifact index.
5. Recompute only from verified immutable inputs.
6. Escalate if a supposedly immutable file changed after publication.

## 4.3 Runtime Journal conflict

1. Stop the conflicting transition.
2. Reload the current record and version.
3. Determine whether the command is duplicate, stale or semantically different.
4. Return the original result for a true duplicate.
5. Reject a reused identity with different semantics.
6. Never force a backward state transition.

## 4.4 Risk service unavailable

1. Fail closed.
2. Do not generate an approved manual intent.
3. Preserve the portfolio proposal and failure reason.
4. Retry only with the same idempotency identity.
5. Escalate if the failure persists into the decision window.

## 4.5 Duplicate or disputed fill

1. Reject duplicate fill ID or idempotency key.
2. If the external statement differs, enter reconciliation-required state.
3. Preserve the original fill.
4. Add a correction or reconciliation event.
5. Rebuild the position from the corrected ledger.
6. Record who approved the correction.

## 4.6 Position mismatch

Severity: critical for the affected account/symbol.

1. Stop new exposure.
2. Export the fill ledger and position projection.
3. Compare with external statement.
4. Identify missing, duplicate or corrected fills.
5. Append reconciliation records.
6. Rebuild and verify PositionSnapshot.
7. Resume only after risk approval.

## 4.7 Model output anomaly

Examples:

- sudden candidate-count collapse;
- state transitions for most themes in one run;
- score distribution outside historical range;
- material feature missingness;
- repeated high-confidence disagreement with evidence.

Procedure:

1. Do not mutate model parameters automatically.
2. Compare data quality and feature coverage first.
3. Replay the exact inputs.
4. Compare with the previous approved model version.
5. Suspend the affected model if the anomaly breaches governance limits.
6. Record evidence and open a controlled research task.

## 4.8 Database unavailable

1. Stop mutable workflow commands.
2. Continue immutable evidence acquisition only if the Runtime Journal and safety policy permit it.
3. Do not accept unrecorded manual actions as system-managed actions.
4. Restore the operational database.
5. replay outbox and audit events;
6. rebuild projections from append-only ledgers;
7. reconcile before resuming.

## 5. Recovery principles

- immutable evidence is never repaired in place;
- mutable projections are rebuilt from append-only authority;
- retries preserve semantic request identity;
- stage receipts prevent duplicate work;
- risk and execution paths fail closed;
- no recovery action raises evidence authority;
- manual corrections require actor and reason.

## 6. Rollback procedures

### Code rollback

- deploy or check out the previous verified commit;
- retain new artifacts and database records for audit;
- disable new model/config registrations rather than deleting evidence;
- run compatibility tests before resuming.

### Feature rollback

- disable new application command composition;
- keep existing DailyLoop and Platform V2 offline research paths active;
- make new operational records read-only;
- continue manual reconciliation if fills were already recorded.

### Database migration rollback

- follow the migration-specific down procedure;
- never delete append-only execution or audit history;
- if schema rollback is unsafe, stop writes and use the prior application in read-only mode until a forward repair is available.

## 7. Routine verification commands

Current repository quality gate:

```bash
python scripts/check_docs_links.py
python -m pytest -q
python -m ruff check .
python -m mypy
```

Planned operational commands shall expose machine-readable output and non-zero failure status. Exact command names must be added to this runbook only after implementation.

## 8. Audit checklist

For any selected trade or completed position, an auditor must be able to locate:

- RunRequest and DailyRun record;
- Source Archive and SourceManifest;
- Universe, Eligibility and Feature artifacts;
- ResearchLayerArtifact and CandidateSet;
- Signal and Forecast artifacts;
- Opportunity and Thesis state history;
- Portfolio and Risk decisions;
- Manual intent and fills;
- Position snapshots and reconciliation;
- Holding and Exit assessments;
- outcome and attribution;
- model, configuration and code revision;
- operator and approver actions.

## 9. Production-readiness blockers

This runbook does not declare production readiness. The following remain blockers until implemented and evidenced:

- formal provider/PIT authority;
- operational universe and theme mapping;
- durable governance repositories;
- executable Signal and PathForecast;
- independent Risk Authority;
- manual fill and position ledger;
- authentication and permissions;
- metrics, tracing and alerts;
- sustained shadow evidence;
- approved operational database and backup procedure.
