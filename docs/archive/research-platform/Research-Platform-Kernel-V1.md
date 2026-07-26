# Research Platform Kernel V1 — Historical Merge Contract

> **Status:** HISTORICAL  
> **Authority:** Historical record of the platform-kernel contract delivered by PR #12; not current implementation-state authority  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** ../../status/Current-State.md; ../../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md  
> **Related Documents:** ../../research/Research-Platform-Vertical-Slice-V1.md, ../../status/Capability-Matrix.md, ../../audit/Post-Merge-Reconciliation-2026-07-26.md  
> **Code Evidence:** PR #12 merge `84e289a9616b70c61cc139c59e9bda8cd66a0975`; `src/market_regime_alpha/platform/**`

## Historical purpose

PR #12 established the first Research Platform Kernel contract and implementation slice. It froze five concerns:

1. Theory, Observable and Model domain contracts;
2. Target and Evaluation Protocols;
3. Frozen Experiment Protocols and research-access budgets;
4. Model Registry lifecycle semantics;
5. a first comparable Multi-model Candidate Slice.

The original document was created under `docs/constitution/10-Research-Platform-Kernel-V1.md`. That location incorrectly implied a new constitutional authority outside the canonical Constitution set `00–09`. The current repository therefore archives the merge contract here and delegates current authority to code/tests, Current State, Capability Matrix and WP-D0.

## Preserved design decisions

- Existing FeatureDefinition, CandidateResearchDataset, CandidatePrediction and Experiment Identity authorities are reused rather than duplicated.
- Model roles remain separate: CONTEXT, CANDIDATE, ENTRY, HOLDING, EXIT and PORTFOLIO.
- Target Protocols freeze decision time, price marks, horizon, return basis, benchmark, adjustment and missing-data semantics.
- Evaluation Protocols freeze metrics, comparators, costs, split policy and minimum evidence thresholds.
- Experiment Protocols enforce one primary change, explicit budgets and recorded evaluation access.
- Model lifecycle promotion requires evidence; ACTIVE requires human approval.
- Multi-model comparison does not establish Alpha, a model winner, production readiness or trading authority.

## Current interpretation

The Platform Kernel is merged and test-backed, but current implementations of Model Registry and Experiment Governance are in-memory prototypes. The first Multi-model Candidate Slice is a mechanical comparable-run capability, not a persistent daily Prediction Ledger.

Current gaps and acceptance conditions are maintained in:

- [Current State](../../status/Current-State.md)
- [Capability Matrix](../../status/Capability-Matrix.md)
- [WP-D0 Platform Governance Kernel Hardening](../../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md)

The original full text remains available in Git history at the PR #12 merge lineage. This historical file must not be used to overrule current executable evidence.
