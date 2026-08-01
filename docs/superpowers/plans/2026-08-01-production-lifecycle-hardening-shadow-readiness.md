# Production Lifecycle Hardening and Shadow Readiness Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for WP-PDL-HARDENING
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../audit/Production-Lifecycle-Hardening-Baseline.md
> **Code Evidence:** Plan against baseline `a7ce0b444e77506a85e1c1c7b240c22c8421580d`; delivery is recorded only after tests and commits

## Goal

Make the Phase 0–7 engineering lifecycle account-complete, fully traceable,
A-share T+1 aware, operationally recoverable and ready for a synthetic/manual
Shadow period while retaining the exploratory evidence and no-broker ceiling.

## Architecture and technology

The implementation remains a Python modular monolith. Domain behavior stays in
the existing bounded contexts; application services orchestrate them. SQLite
is the first durable adapter behind storage-neutral Protocols. Immutable
content-addressed Artifacts remain evidence authority. Pytest, Ruff, mypy and
the repository documentation checker are mandatory gates.

## H0 tasks

1. Verify the twelve baseline questions in the exact code, SQL, CLI and tests.
2. Run the unchanged full quality gate.
3. Add Architecture 11, WP-PDL-HARDENING, baseline audit and this plan.
4. Correct stale implementation-state prose without changing runtime.
5. Run documentation/full gates, review the diff and create the H0 checkpoint.

## H1 tasks

1. Add failing tests under `tests/portfolio/` for full-account exposure,
   completeness, stale/reconciliation, empty/reducing/close, idempotency and
   restart.
2. Add V2 account-position, trade-delta and post-trade snapshot contracts in
   `portfolio/` with canonical identity and no defaults.
3. Change Portfolio construction and Risk recomputation to consume the complete
   post-trade snapshot.
4. Add repository Protocol operations, SQLite migration 005, strict restore and
   isolated down migration.
5. Adapt `PortfolioRiskApplicationService` and CLI request parsing.
6. Run focused migration/repository/service tests, full gates, update docs and
   commit H1.

## H2 tasks

1. Add failing Decision/Execution/Position/Evaluation tests for open-book
   uniqueness and complete authority mismatch/replay cases.
2. Add a versioned `PositionBook`/trace reference and active account-symbol
   repository invariant without altering V1 Thesis meanings.
3. Add V2 ManualTrade and Fill trace fields, exact upstream validation and
   migration 006.
4. Project Position per book and retain manual-trade/Fill provenance.
5. Require TradeOutcome inputs to reconstruct Opportunity→Risk→Fill scope.
6. Run focused/full gates, document compatibility/rollback and commit H2.

## H3 tasks

1. Add T+1 tests for same day, explicit Friday/Monday, holiday, suspension,
   lots, correction, missing calendar, replay and restart.
2. Add PositionLot/Snapshot V2 sellability fields and settlement states.
3. Reuse `TradingCalendarArtifact` to derive sellable sessions.
4. Reject sells above available quantity and remove independent caller
   available-quantity authority from the V2 risk path.
5. Persist/rebuild the current Position projection where needed via migration
   007, retaining Fill as history authority.
6. Run focused/full gates, update docs and commit H3.

## H4 tasks

1. Add tests for Risk timeout with valid exit, reducing-only invariants,
   reconciliation, suspension, missing state and bypass attempts.
2. Add typed increasing/reducing classification and structured reducing-gate
   results in `portfolio/`/`execution/`.
3. Add the application command and append-only audit persistence in migration
   008.
4. Route REDUCE/EXIT to the reducing gate; retain full Risk for OPEN/ADD.
5. Run focused/full gates, update runbook/status/audit and commit H4.

## H5 tasks

1. Add builder tests for hash, time, theme, Capital, Signal, risk-off,
   invalidation, missingness, replay and input-surface rejection.
2. Define explicit health-rule config and verified input references.
3. Implement `ThesisHealthObservationBuilder`; keep derived booleans internal
   to the resulting typed observation.
4. Change review CLI input from support values to Artifact references/config.
5. Preserve V1 reader compatibility but prevent V1 input through the new
   operational command.
6. Run focused/full gates, update docs and commit H5.

## H6 tasks

1. Add operational-research tests for dual manifest time/hash/identity,
   per-field coverage, eligibility ceiling, replay and kind semantics.
2. Add `OPERATIONAL_EXPLORATORY_ARCHIVE` as a new compatible evidence kind.
3. Implement and publish `CompositeOperationalInputManifest` as a lineage
   index referencing both original authorities.
4. Bind the ResearchInputBundle/artifact to the composite identity without
   changing the original SourceManifests.
5. Run focused/full gates, update docs and commit H6.

## H7 tasks

1. Add repository contract tests for duplicate/CAS/stale inputs/restart,
   blocked exit, acknowledgement, corruption, append-only and up/down migration.
2. Define assessment schedule/event/latest-state Protocols.
3. Implement SQLite migration 009, append-only history and rebuildable latest
   projection.
4. Add application services for assessment, blocked reduction,
   reconciliation/stale evidence and acknowledgement.
5. Run focused/full gates, update docs and commit H7.

## H8 tasks

1. Add synthetic E2E and failure-injection tests for schedule idempotency,
   stage restart, queues, metrics, alerts, acknowledgement and reports.
2. Define ShadowRun, stage receipt, queue item, metric, alert and Fill-source
   contracts.
3. Implement SQLite migration 010 and recoverable CLI-first Shadow service.
4. Implement manual-recorded versus synthetic Shadow Fill provenance and its
   no-broker limitations.
5. Produce deterministic daily operations reports, structured JSON logs and
   correlation/trace IDs.
6. Verify there is no LIVE broker mutation, run full gates, update the runbook
   and status to at most `SHADOW_READY_ENGINEERING`, then commit H8.

## H9 tasks

1. Add tests for complete sample retention, PIT/availability, overlapping-label
   purging, embargo, walk-forward split and deterministic metrics.
2. Add explicit comparison-group and validation-protocol contracts in
   `evaluation/` or a research validation submodule.
3. Label V1 path statistics `EmpiricalPathBaselineV1` in the new validation
   output; preserve existing PathForecast V1 readers.
4. Add bounded PathForecastV2 conditional-bucket/pooling/sample-gate contract.
5. Implement the required diagnostics over synthetic fixtures only.
6. Run focused/full gates, state the external evidence blockers and commit H9.

## Final review and publication tasks

1. Review every phase commit, migration pair, reader compatibility and dirty
   workspace preservation.
2. Run the independent standards/spec review workflow against the H0 base.
3. Fix High/Medium findings in bounded commits and rerun full gates.
4. Push only the feature branch and create a documented Draft PR after H1–H8.
5. Record PR URL, review state, test evidence, rollback and all non-claims.
