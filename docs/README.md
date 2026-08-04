# Documentation Authority and Navigation

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical documentation entry point and authority policy  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-04
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** constitution/**, architecture/**, research/**, specs/**, status/**, roadmap/**, audit/**, archive/**  
> **Code Evidence:** Repository-wide

## Two independent authority orders

Normative authority and implementation-fact authority answer different questions. They must never be merged into one precedence list.

### Normative authority order

Use this order to determine what the project **should** do:

```text
1. Latest explicit user decision that has not been superseded
2. docs/constitution/00–09
3. docs/architecture/00–11 and architecture/domains/**
4. docs/research/Current-Research-Program.md and focused current research programs
5. docs/specs/** and docs/roadmap/work-packages/**
6. HISTORICAL/SUPERSEDED material for context only
```

### Implementation fact authority order

Use this order to determine what the repository **actually does now**:

```text
1. Current executable code at the audited commit
2. Current tests and static checks
3. Reproducible runtime/research Artifacts and manifests
4. docs/status/Current-State.md and Capability-Matrix.md
5. Audit evidence tied to an exact commit
6. Historical status reports and plans
```

A lower normative document cannot override Constitution. A document cannot establish implementation by assertion when code/tests/artifacts disagree.

## Current documents

### Constitution

- [00 Project Vision](constitution/00-Project-Vision.md)
- [01 Core Principles](constitution/01-Core-Principles.md)
- [02 Architecture Blueprint](constitution/02-Architecture-Blueprint.md)
- [03 Research Framework](constitution/03-Research-Framework.md)
- [04 Data Constitution](constitution/04-Data-Constitution.md)
- [05 Factor Constitution](constitution/05-Factor-Constitution.md)
- [06 Strategy Constitution](constitution/06-Strategy-Constitution.md)
- [07 Validation Constitution](constitution/07-Validation-Constitution.md)
- [08 Constitutional Roadmap](constitution/08-Roadmap.md)
- [09 Glossary](constitution/09-Glossary.md)

The canonical Constitution ends at `09`. Historical platform-kernel merge material is archived and cannot create a new constitutional authority.

### Current architecture

- [System Context](architecture/00-System-Context.md)
- [Domain Boundaries](architecture/01-Domain-Boundaries.md)
- [Domain Design Index](architecture/domains/README.md)
- [End-to-End Flow](architecture/02-End-to-End-Research-and-Decision-Flow.md)
- [Research Artifact Architecture](architecture/03-Research-Artifact-Architecture.md)
- [Data and Time Semantics](architecture/04-Data-and-Time-Semantics.md)
- [Phase D Daily Decision Engine](architecture/05-Phase-D-Daily-Decision-Engine-V1.md)
- [Legacy Migration](architecture/06-Legacy-Migration.md)
- [QuantDesk Boundary](architecture/07-QuantDesk-Integration-Boundary.md)
- [Deployment and Operations Boundary](architecture/08-Deployment-Operations-Boundary.md)
- [Platform Architecture V2](architecture/09-Platform-Architecture-V2.md)
- [Production Decision Lifecycle](architecture/10-Production-Decision-Lifecycle.md)
- [Production Lifecycle Hardening and Shadow Operations](architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md)
- [Architecture Decision Records](architecture/decisions/README.md)

### Current research

- [Current Research Program](research/Current-Research-Program.md)
- [Candidate Research](research/Candidate-Research.md)
- [Research Platform Multi-model Candidate Slice V1](research/Research-Platform-Vertical-Slice-V1.md)
- [Entry Research](research/Entry-Research.md)
- [Position Lifecycle Research](research/Position-Lifecycle-Research.md)
- [Exit Research](research/Exit-Research.md)
- [ETF, Theme and Capital Context](research/ETF-Theme-Capital-Context-Research.md)
- [Validation and Ablation](research/Validation-and-Ablation.md)
- [Failure Attribution](research/Failure-Attribution.md)
- [Negative and Inconclusive Results](research/Negative-and-Inconclusive-Results.md)

### Specifications and roadmap

- [Specification Index](specs/README.md)
- [Contract Conventions](specs/Contract-Conventions.md)
- [Error Catalog](specs/Error-Catalog.md)
- [Production Decision Lifecycle Requirements](specs/Production-Decision-Lifecycle-Requirements.md)
- [Phase D Work Package Index](roadmap/Phase-D-Work-Packages.md)
- [Detailed Work Packages](roadmap/work-packages/README.md)
- [Run-First Exploratory Daily Platform Implementation Plan](superpowers/plans/2026-07-28-run-first-exploratory-daily-platform.md)
- [Public LIVE Semantic Closure Implementation Plan](superpowers/plans/2026-07-29-public-live-semantic-closure.md)
- [WP-D3.1 Real Decision Evidence Implementation Plan](superpowers/plans/2026-07-30-wp-d3-1-real-decision-evidence.md)
- [WP-D3.1 Real Decision Evidence Design](superpowers/specs/2026-07-30-wp-d3-1-real-decision-evidence-design.md)
- [Production Decision Lifecycle Approved Design](superpowers/specs/2026-08-01-production-decision-lifecycle-design.md)
- [Production Decision Lifecycle Implementation Plan](superpowers/plans/2026-08-01-production-decision-lifecycle.md)
- [Production Lifecycle Hardening and Shadow Readiness Plan](superpowers/plans/2026-08-01-production-lifecycle-hardening-shadow-readiness.md)
- [H4 Reducing-Risk Decision Route Design](superpowers/specs/2026-08-03-h4-reducing-risk-decision-route-design.md)
- [H4 Reducing-Risk Decision Route Implementation Plan](superpowers/plans/2026-08-03-h4-reducing-risk-decision-route.md)
- [H5 Artifact-Derived Thesis Health Design](superpowers/specs/2026-08-04-h5-artifact-derived-thesis-health-design.md)
- [H5 Artifact-Derived Thesis Health Implementation Plan](superpowers/plans/2026-08-04-h5-artifact-derived-thesis-health.md)
- [H6 Composite Operational Evidence Design](superpowers/specs/2026-08-04-h6-composite-operational-evidence-design.md)
- [H6 Composite Operational Evidence Implementation Plan](superpowers/plans/2026-08-04-h6-composite-operational-evidence.md)
- [H4.5 Risk-Reduction Manual Intent Design](superpowers/specs/2026-08-04-h4-5-risk-reduction-manual-intent-design.md)
- [H4.5 Risk-Reduction Manual Intent Implementation Plan](superpowers/plans/2026-08-04-h4-5-risk-reduction-manual-intent.md)
- [Canonical Runtime and Legacy Model Migration Infrastructure Design](superpowers/specs/2026-08-04-canonical-runtime-and-legacy-migration-design.md)
- [WP-PAV2 Platform Architecture V2 and Research Layer MVP](roadmap/work-packages/WP-PAV2-Platform-Architecture-V2-and-Research-Layer-MVP.md)
- [WP-PDL Production Decision Lifecycle](roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md)
- [WP-PDL-HARDENING Production Lifecycle Hardening and Shadow Readiness](roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md)

### Operations and implementation prompts

- [Production Decision Lifecycle Runbook](operations/Production-Decision-Lifecycle-Runbook.md)
- [Claude Code Production Decision Lifecycle Master Prompt](prompts/Claude-Code-Production-Decision-Lifecycle.md)

### Current status

- [Current State](status/Current-State.md)
- [Capability Matrix](status/Capability-Matrix.md)
- [Gap Register](status/Gap-Register.md)
- [External Blockers](status/External-Blockers.md)

### Audit and archive

- [Claude Code Engineering Program Update — 2026-08-01](audit/Claude-Code-Engineering-Program-Update-2026-08-01.md)
- [Current Main Code Audit — 2026-08-01](audit/Current-Main-Code-Audit-2026-08-01.md)
- [H4.5 Risk-Reduction Manual Intent Delivery](audit/H4-5-Risk-Reduction-Manual-Intent-Delivery.md)
- [H4 Risk Route Delivery](audit/H4-Risk-Route-Delivery.md)
- [H5 Thesis Health Delivery](audit/H5-Thesis-Health-Delivery.md)
- [H6 Composite Operational Evidence Delivery](audit/H6-Composite-Operational-Evidence-Delivery.md)
- [Production Decision Lifecycle Gap Analysis](audit/Production-Decision-Lifecycle-Gap-Analysis.md)
- [Production Decision Lifecycle Documentation Delivery](audit/Production-Decision-Lifecycle-Documentation-Delivery.md)
- [Production Decision Lifecycle Delivery](audit/Production-Decision-Lifecycle-Delivery.md)
- [Production Lifecycle Hardening Baseline](audit/Production-Lifecycle-Hardening-Baseline.md)
- [Production Lifecycle Hardening Delivery](audit/Production-Lifecycle-Hardening-Delivery.md)
- [Run-First Daily Platform Baseline Audit](audit/Run-First-Daily-Platform-Baseline-Audit.md)
- [Run-First Exploratory Daily Platform Delivery](audit/Run-First-Daily-Platform-Delivery.md)
- [WP-D3 Public LIVE Semantic Closure Audit](audit/WP-D3-Public-Live-Semantic-Closure.md)
- [WP-D3.1 Real Decision Evidence Baseline Audit](audit/WP-D3-1-Real-Decision-Evidence-Baseline.md)
- [WP-D3.1 Real Decision Evidence Delivery](audit/WP-D3-1-Real-Decision-Evidence-Delivery.md)
- [WP-PAV2 Platform Architecture V2 Delivery](audit/WP-PAV2-Platform-Architecture-V2-Delivery.md)
- [Repository Audit Baseline](audit/Repository-Audit-Baseline-2026-07-26.md)
- [Post-Merge Reconciliation Audit](audit/Post-Merge-Reconciliation-2026-07-26.md)
- [Post-Consolidation Code Audit](audit/Post-Consolidation-Code-Audit-2026-07-26.md)
- [Branch Reconciliation Audit](audit/Branch-Reconciliation-2026-07-26.md)
- [Repository Map](audit/Repository-Map.md)
- [Documentation Problem Report](audit/Docs-Problem-Report.md)
- [Document Inventory and Migration Plan](audit/Docs-Inventory-and-Migration-Plan.md)
- [Conversation Decision Ledger](audit/Conversation-Decision-Ledger.md)
- [Conversation Evidence Index](audit/Conversation-Evidence-Index.md)
- [Conversation-to-Repository Traceability](audit/Conversation-to-Repository-Traceability.md)
- [Conflict Register](audit/Conflict-Register.md)
- [Supersession Registry](audit/Supersession-Registry.tsv)
- [Code Evidence Registry](audit/Code-Evidence-Registry.tsv)
- [Archive Index](archive/README.md)
- [Historical Research Platform Kernel V1](archive/research-platform/Research-Platform-Kernel-V1.md)

### Agent project assets

- [`CLAUDE.md`](../CLAUDE.md) — Claude Code project memory and current WP-PDL execution priority.
- [`AGENTS.md`](../AGENTS.md) — shared cross-agent execution contract.
- [Claude project asset guide](../.claude/README.md) — shared Skills and Subagents.
- [Continuous WP-PDL Skill](../.claude/skills/advance-production-lifecycle/SKILL.md) — dependency-ordered whole-program execution.
- [Single Work Package Skill](../.claude/skills/implement-work-package/SKILL.md) — one bounded work package or phase.

### Provider operational authorities

- [Xuntou PIT Field Mapping V4](specs/Xuntou-PIT-Field-Mapping-V4.md)
- [Xuntou PIT Validation Bundle V4](specs/Xuntou-PIT-Validation-Bundle-V4.md)
- [Xuntou PIT Validation Export Runbook](runbooks/Xuntou-PIT-Validation-Export.md)

## Status vocabulary

```text
CONSTITUTION
CURRENT_ARCHITECTURE
CURRENT_RESEARCH_PROGRAM
CURRENT_SPECIFICATION
CURRENT_EXECUTION_PROMPT
CURRENT_STATUS
PROPOSED_ARCHITECTURE
PROPOSED_REQUIREMENTS
PROPOSED_OPERATIONS
ROADMAP
PLANNED
HISTORICAL
SUPERSEDED
DRAFT
```

Every Markdown document has exactly one machine-readable `> **Status:**` header. Historical embedded status text must use `Historical Status at Original Publication`, never a second active Status field.
