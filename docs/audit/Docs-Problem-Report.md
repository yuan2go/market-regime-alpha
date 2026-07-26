# Documentation Problem Report

> **Status:** CURRENT_STATUS  
> **Authority:** Detailed diagnosis of the baseline documentation system  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Docs-Inventory.tsv, Conflict-Register.md  
> **Code Evidence:** 87 baseline docs fully read

## Findings

1. **Authority collision:** multiple architecture audits and R5 documents labelled themselves current without one status owner.
2. **Status drift:** AGENTS and R5 current status lagged implemented Xuntou and Entry Path work.
3. **Mixed concerns:** long documents combined normative rules, design, status, work plans and historical results.
4. **Historical namespace pollution:** dated superpowers plans/specs appeared beside current architecture.
5. **Implementation overstatement risk:** test-only success paths and adapters could be read as real provider or Alpha evidence.
6. **Product identity ambiguity:** Legacy auto-provider/broker/Dashboard instructions appeared in the root entry point.
7. **Missing Phase D contracts:** daily snapshot, position, review and manual execution objects existed only in conversation/long programs.
8. **No unique navigation:** README linked individual legacy/current documents but no authority map.
9. **No complete traceability:** decisions were not mapped end to end from conversation through Constitution, code, tests and roadmap.
10. **No executable current roadmap:** constitutional R stages and dated task plans did not provide one Phase D dependency chain.

## Resolution

- `docs/README.md` is the authority/navigation entry.
- `docs/status/Current-State.md` is the sole current implementation-state owner.
- architecture `00–08`, focused research docs and independent specs separate concerns.
- dated plans moved to archive; negative results remain visible.
- every formal Markdown document now carries standard status/authority metadata.
- a repository-local link/status validator was added.
