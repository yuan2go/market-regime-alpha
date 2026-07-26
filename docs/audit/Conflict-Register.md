# Conflict Register

> **Status:** CURRENT_STATUS  
> **Authority:** Resolved documentation and implementation conflicts for the 2026-07-26 reconstruction  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Docs-Inventory-and-Migration-Plan.md, ../status/Current-State.md  
> **Code Evidence:** main source and tests at audited HEAD

| conflict_id | source_a | source_b | conflict_type | description | authority_analysis | resolution |
|---|---|---|---|---|---|---|
| CF-001 | AGENTS.md current implementation state | Xuntou adapter code/tests | IMPLEMENTATION_CLAIM_CONFLICT | AGENTS said native adapter not implemented; main contains xuntou_provider_adapter and v4 adapter/contracts/tests. | Code/tests win for implementation fact. | Rewrite AGENTS current state. |
| CF-002 | AGENTS.md current implementation state | strategies/entry contracts/materialization/tests | IMPLEMENTATION_CLAIM_CONFLICT | AGENTS said Entry Path Target code contract was not implemented. | Code/tests win. Infrastructure exists; Entry model does not. | Separate Entry Path Target infrastructure from Entry Assessment/model. |
| CF-003 | R5-Current-Status marked CURRENT | Commits #8–#11 and daily program | STALE_STATUS | R5 status predates latest PIT replication hardening and current product program. | Newest code/artifacts and new Current-State win. | Mark R5 status SUPERSEDED. |
| CF-004 | Multiple architecture audits marked CURRENT | No unique architecture entry | STATUS_CONFLICT | Several R3/R4/R5/readiness audits claim current authority. | New architecture 00–08 becomes unique current architecture. | Mark old audits HISTORICAL/SUPERSEDED. |
| CF-005 | Legacy platform/readme presents broker adapters and auto fallback | Current non-goals | PROJECT_IDENTITY_CONFLICT | Legacy capabilities can look like current automated trading product. | Constitution/current product decision wins. | Move runbooks under Legacy archive and label no authority. |
| CF-006 | Public-source runtime availability | Formal provider-backed claims | DATA_SEMANTICS_CONFLICT | Tencent/BaoStock paths can run but lack historical PIT/availability/finality authority. | Data Constitution and Dataset eligibility win. | Expose explicit EXPLORATORY ceiling. |
| CF-007 | B1 positive descriptive lift in some artifacts | MR-2B primary hypothesis result | STATUS_CONFLICT | Descriptive Candidate lift can be mistaken for context-conditioned Alpha/model winner. | Formal assessment remains PRIMARY_HYPOTHESIS_NOT_SUPPORTED; no OOS Alpha. | Separate descriptive result from authority. |
| CF-008 | Candidate rank output | Entry/trading action language in Legacy/UI | TERMINOLOGY_CONFLICT | High rank may be interpreted as buy. | Strategy Constitution wins. | Use CandidateRecommendation and EntryAssessment separately. |
| CF-009 | Legacy certainty/score fields | Probability language | TERMINOLOGY_CONFLICT | Legacy “certainty” is not calibrated probability. | Score-is-not-probability rule wins. | Label score/uncertainty, require calibration contract. |
| CF-010 | Constitution roadmap and many dated task plans | Current Phase D direction | ROADMAP_CONFLICT | Detailed R5/MACD task plans obscure current Phase D order. | Phase D executable roadmap becomes current; dated plans historical. | Archive superpowers plans/specs. |
| CF-011 | Draft PR #12 implementation | main audit baseline | STATUS_CONFLICT | Platform kernel is CI-verified but unmerged. | main is implementation authority. | Record PR #12 as pending and dependency. |
| CF-012 | QuantDesk future integration discussion | No code in repository | ARCHITECTURE_OWNERSHIP_CONFLICT | UI role could be mistaken for current implementation. | Current design only. | Publish integration boundary and mark NOT_STARTED. |

No conflict is resolved by deleting negative evidence. Historical research outcomes and implementation plans remain available under historical status or archive paths.
