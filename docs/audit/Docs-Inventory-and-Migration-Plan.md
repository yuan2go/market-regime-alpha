# Docs Inventory and Migration Plan

> **Status:** CURRENT_STATUS  
> **Authority:** Full baseline document inventory and migration decision  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../README.md, ../archive/Document-Migration-Manifest.md  
> **Code Evidence:** 87 baseline docs read at main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

## Problems found

- several documents simultaneously claimed CURRENT authority;
- current status, design, implementation and historical research were mixed in long files;
- newer code contradicted stale AGENTS/R5 status claims;
- dated implementation plans crowded the current documentation namespace;
- no unique docs navigation, current status, capability matrix or executable Phase D roadmap;
- Phase D contracts were described in conversation/long programs but not separated into specifications;
- Legacy operational instructions were visually indistinguishable from current product authority.

## Migration decisions

| Baseline path | Action | Rationale/current owner |
|---|---|---|
| `docs/Data-Spec.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Dividend-T-Platform.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Formal-Data-Source-Capability-Audit.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Formal-Data-Source-PoC-2026-07-14.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Formal-MACD-Dataset-Builder-Plan.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/MACD-Research-Audit.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Project-Structure.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Sell-Side-Model-Spec.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Tushare-App.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/Usage-Manual.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/architecture/Constitution-Consistency-Audit.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/Original-Intent-to-Current-Docs-and-Codex-Readiness-Audit.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/Original-Intent-to-R3-R4-Consistency-Audit.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/Original-Intent-to-R5-Consistency-Audit.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/Original-Intent-to-R5-Eligibility-Readiness-Audit.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/PRR-MVP-1-Reproducible-Candidate-Backtest.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/R1-Legacy-Characterization.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/R2-Minimal-V2-Kernel.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/architecture/R3-R4-Minimal-Research-Spine.md` | ARCHIVE | Historical architecture/audit; current architecture is docs/architecture/00–08. |
| `docs/constitution/00-Project-Vision.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/01-Core-Principles.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/02-Architecture-Blueprint.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/03-Research-Framework.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/04-Data-Constitution.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/05-Factor-Constitution.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/06-Strategy-Constitution.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/07-Validation-Constitution.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/08-Roadmap.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/09-Glossary.md` | KEEP | Constitution path retained; standardized metadata and clarification. |
| `docs/constitution/implementation-status.md` | SUPERSEDE | Unique current status moved to docs/status/Current-State.md. |
| `docs/development/WP-0-Close-B1-Verification.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/references/providers/xuntou/README.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/research/Daily-Quant-Selection-and-Manual-Trading-Research-Program.md` | SUPERSEDE | Current navigation consolidated into focused current research docs. |
| `docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md` | SUPERSEDE | Current navigation consolidated into focused current research docs. |
| `docs/research/MR-1-Overnight-Morning-Pop-Signal-Validation.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2-Morning-Pop-Failure-Decomposition.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2A-Leak-Free-Regime-Diagnostic.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2B-F2A-Conditionality-Inputs.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2B-F2B-Statistical-Closure.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2B-F2B-v2-Post-Merge-Hardening.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/MR-2B-Final-Assessment.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/PIT-Candidate-Replication-Charter.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/PIT-Candidate-Replication-Success-Path-V2.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/PIT-Replication-Statistical-Protocol-V2.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/PIT-Validation-Partition-Governance.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Candidate-Dataset-Builder-Status.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Candidate-Model-Research-Program.md` | SUPERSEDE | Current navigation consolidated into focused current research docs. |
| `docs/research/R5-Current-Status.md` | SUPERSEDE | Unique current status moved to docs/status/Current-State.md. |
| `docs/research/R5-Data-Source-Role-Matrix.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Generic-Provider-Export-Adapter.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Provider-Rehearsal-Market-Artifact.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Versioned-Trading-Eligibility-Policy.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-WP3-Provider-Routing-Status.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Xuntou-P0-Adapter-Status.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/R5-Xuntou-Provider-and-Strategy-Priority.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/Research-Artifact-Identity-V3.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/research/Xuntou-PIT-Evidence-Qualification.md` | ARCHIVE | Retained as historical research evidence at stable path. |
| `docs/runbooks/Xuntou-PIT-Validation-Export.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/specs/Entry-Path-Target-V1.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/specs/Xuntou-P0-Native-Field-Mapping.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/specs/Xuntou-PIT-Field-Mapping-V4.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/specs/Xuntou-PIT-Validation-Bundle-V4.md` | KEEP | Current technical/provider specification with standardized metadata. |
| `docs/superpowers/checkpoints/2026-07-13-macd-task0-baseline.md` | MOVE | docs/archive/superpowers/checkpoints/2026-07-13-macd-task0-baseline.md |
| `docs/superpowers/plans/2026-07-13-macd-signal-intent-implementation.md` | MOVE | docs/archive/superpowers/plans/2026-07-13-macd-signal-intent-implementation.md |
| `docs/superpowers/plans/2026-07-16-tencent-composite-exploratory-r5.md` | MOVE | docs/archive/superpowers/plans/2026-07-16-tencent-composite-exploratory-r5.md |
| `docs/superpowers/plans/2026-07-16-wp3-candidate-directional-accuracy.md` | MOVE | docs/archive/superpowers/plans/2026-07-16-wp3-candidate-directional-accuracy.md |
| `docs/superpowers/plans/2026-07-16-wp3-provider-routing-and-candidate-runs.md` | MOVE | docs/archive/superpowers/plans/2026-07-16-wp3-provider-routing-and-candidate-runs.md |
| `docs/superpowers/plans/2026-07-16-wp4a-entry-path-targets.md` | MOVE | docs/archive/superpowers/plans/2026-07-16-wp4a-entry-path-targets.md |
| `docs/superpowers/plans/2026-07-16-xuntou-p0-native-adapter.md` | MOVE | docs/archive/superpowers/plans/2026-07-16-xuntou-p0-native-adapter.md |
| `docs/superpowers/plans/2026-07-18-wp4a1-entry-path-temporal-price-lineage-hardening.md` | MOVE | docs/archive/superpowers/plans/2026-07-18-wp4a1-entry-path-temporal-price-lineage-hardening.md |
| `docs/superpowers/plans/2026-07-18-wp4a2-entry-path-as-of-evidence-correction.md` | MOVE | docs/archive/superpowers/plans/2026-07-18-wp4a2-entry-path-as-of-evidence-correction.md |
| `docs/superpowers/specs/2026-07-13-macd-signal-intent-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-13-macd-signal-intent-design.md |
| `docs/superpowers/specs/2026-07-16-tencent-composite-exploratory-r5-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-16-tencent-composite-exploratory-r5-design.md |
| `docs/superpowers/specs/2026-07-16-wp3-candidate-directional-accuracy-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-16-wp3-candidate-directional-accuracy-design.md |
| `docs/superpowers/specs/2026-07-16-wp3-provider-routing-and-candidate-runs-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-16-wp3-provider-routing-and-candidate-runs-design.md |
| `docs/superpowers/specs/2026-07-16-wp4a-entry-path-targets-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-16-wp4a-entry-path-targets-design.md |
| `docs/superpowers/specs/2026-07-18-wp4a1-entry-path-temporal-price-lineage-hardening-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-18-wp4a1-entry-path-temporal-price-lineage-hardening-design.md |
| `docs/superpowers/specs/2026-07-18-wp4a2-entry-path-as-of-evidence-correction-design.md` | MOVE | docs/archive/superpowers/specs/2026-07-18-wp4a2-entry-path-as-of-evidence-correction-design.md |
| `docs/theory/退神股票涨跌理论.md` | ARCHIVE | Legacy/reference document retained with historical status. |
| `docs/退神股票涨跌理论-量化实现差距分析.md` | ARCHIVE | Legacy/reference document retained with historical status. |

No exact duplicate baseline documents were detected by content hash. Historical evidence is preserved rather than deleted.
