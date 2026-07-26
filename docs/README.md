# Documentation Authority and Navigation

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical documentation entry point and authority policy  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
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
3. docs/architecture/00–08 and architecture/domains/**
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
- [Phase D Work Package Index](roadmap/Phase-D-Work-Packages.md)
- [Detailed Work Packages](roadmap/work-packages/README.md)

### Current status

- [Current State](status/Current-State.md)
- [Capability Matrix](status/Capability-Matrix.md)
- [Gap Register](status/Gap-Register.md)
- [External Blockers](status/External-Blockers.md)

### Audit and archive

- [Repository Audit Baseline](audit/Repository-Audit-Baseline-2026-07-26.md)
- [Post-Merge Reconciliation Audit](audit/Post-Merge-Reconciliation-2026-07-26.md)
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

- [`CLAUDE.md`](../CLAUDE.md) — Claude Code project memory and current execution priority.
- [`AGENTS.md`](../AGENTS.md) — shared cross-agent execution contract.
- [Claude project asset guide](../.claude/README.md) — shared Skills and Subagents.

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
CURRENT_STATUS
ROADMAP
HISTORICAL
SUPERSEDED
DRAFT
```

Every Markdown document has exactly one machine-readable `> **Status:**` header. Historical embedded status text must use `Historical Status at Original Publication`, never a second active Status field.
