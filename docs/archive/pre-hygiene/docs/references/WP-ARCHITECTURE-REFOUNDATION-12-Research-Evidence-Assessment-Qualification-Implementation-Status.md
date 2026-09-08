# WP-12 Research Evidence, Assessment and Qualification Implementation Status

> **Status:** CURRENT_STATUS
> **Authority:** Mutable implementation/status record; exact-SHA engineering proof remains in the immutable WP-12 Verification
> **Owner:** Market Regime Alpha maintainers
> **Recorded At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@883f35835671ebbd7d977b35b36c59528d536990`
> **Implementation Checkpoint:** `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **Branch:** `agent/wp-12-research-evidence-assessment-qualification`
> **Worktree:** isolated linked worktree `wp-12-research-evidence-assessment-qualification`; primary checkout untouched
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP11Q = MERGED / EXIT_GATE_PASS
WP12 = IMPLEMENTED_AND_QUALIFIED
WP12_EXIT_GATE = PASS
Runtime/CLI Cutover = NO-GO
Formal OOS/Prospective = NO-GO
Production = NO-GO
```

WP-12 is implemented in the existing Research & Qualification Authority with
three narrow Evidence, Assessment, and Qualification UoWs. The exact proof is
the immutable
[WP-12 Verification](WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md).
This status page neither grants business cutover nor turns an admitted Research
purpose into Alpha, Model, Forecast, trading, or Production authority.

## Implemented closure

```text
terminal EvaluationRun
→ immutable EvidenceItem / EvidenceDependency DAG
→ complete Experiment-bound ResearchAssessment revision
→ purpose-specific ResearchQualificationPolicy / complete Floor roster
→ ResearchQualificationDecision / every FloorResult / exact FloorEvidence
→ exact-ID, cutoff-aware, later-generation admitted-qualification read port
```

Evidence items bind exact terminal Evaluation Runs, immutable Artifacts, and,
when metric-scoped, exact Evaluation Metrics. Assessment derives rather than
accepts the complete terminal Evaluation and Evidence rosters for one exact
Experiment and preserves support, counter-evidence, failed, inconclusive, and
not-estimable facts. Qualification evaluates every relational Policy floor,
records missing and failed floors, binds the exact Assessment Evidence used by
each result, and grants only the declared Research purpose.

The sole target composition root constructs `RecordEvidence`,
`AssessResearch`, `RegisterResearchQualificationPolicy`,
`DecideResearchQualification`, the exact admitted-decision read port, and the
read-only verifier. No Runtime dispatch or business CLI command calls them.

## Persistence and proof state

The unreleased `001_baseline.sql` adds ten WP-12 tables and no `002+`
migration, placeholder, generic subject, JSON business owner, compatibility
facade, or dual write. The qualified clean PostgreSQL 16 catalog has 78 tables,
four views, 611 indexes, 913 constraints, 65 functions, and 163 non-internal
triggers.

At implementation `48949c87ad0241a8d60031137bc3aa8eb9887525`, clean
bootstrap/verify/recreate, real concurrency, atomic failure recovery,
unknown-commit exact receipt replay, stale-fence zero-write, read-only
reconciliation, seven representative query plans, all 3,585 repository tests,
Ruff, mypy, build, documentation, architecture/import, and diff gates pass.
GitHub Actions is disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS.

## Handoff boundary

The dependency-ready next branch is optional Model / ModelVersion /
Calibration. It is not started or implied. Remaining Decision Support,
including a concrete later-generation DecisionRun qualification roster, also
requires its own authorization and exit gate.

The following remain expressly unsupported:

```text
Model / ModelVersion / Calibration
Context / Signal / Forecast / Opportunity
Portfolio / Risk / Execution / TradeOutcome / Attribution
Runtime/CLI Cutover or Legacy deletion
Formal OOS or Prospective campaign/promotion
Alpha value, Provider qualification, trading, or Production readiness
```
