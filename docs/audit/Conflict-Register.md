# Conflict Register

> **Status:** CURRENT_STATUS  
> **Authority:** Resolved and open documentation/repository authority conflicts  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Conversation-Decision-Ledger.md, Code-Evidence-Registry.tsv, ../status/Current-State.md  
> **Code Evidence:** Commit-bound audit and current branch documentation

| conflict_id | source A | source B | type | description | code evidence | conversation evidence | affected documents | authority analysis | resolution | status |
|---|---|---|---|---|---|---|---|---|---|---|
| CF-001 | AGENTS historical implementation section | current code/tests | STATUS_DRIFT | Xuntou/Entry Path work was described as missing. | path:AGENTS.md; path:src/market_regime_alpha/strategies/entry | CE-004 | AGENTS.md; status/Capability-Matrix.md | Executable evidence wins. | Rewritten with separate fact authority. | RESOLVED |
| CF-002 | multiple R5/implementation status documents | Current-State.md | AUTHORITY_COLLISION | Several documents presented themselves as current. | path:docs/research/R5-Current-Status.md; path:docs/constitution/implementation-status.md | CE-004, CE-005 | docs/research/R5-Current-Status.md; docs/constitution/implementation-status.md | Unique current status is required. | Superseded metadata plus secondary-status cleanup. | RESOLVED |
| CF-003 | Constitution 08 current repository audit | status/audit evidence | NORMATIVE_FACT_MIX | Time-sensitive implementation facts lived in Constitution. | path:docs/constitution/08-Roadmap.md | CE-005 | docs/constitution/08-Roadmap.md; docs/audit/Constitution-Implementation-State-Extraction.md | Constitution is normative. | Extracted to audit; replaced with timeless principle. | RESOLVED |
| CF-004 | public-source runnability | formal PIT evidence | EVIDENCE_INFLATION | Runnable Tencent/BaoStock paths could be read as formal evidence. | path:src/market_regime_alpha/research | CE-007 | docs/status/External-Blockers.md; WP-D2E | Evidence ceiling follows source contract. | Hard EXPLORATORY ceiling and separate formal WP-D11. | RESOLVED |
| CF-005 | B1 descriptive lift | MR-2B primary hypothesis | RESEARCH_INTERPRETATION | Positive descriptive slices could be mistaken for supported primary hypothesis. | path:src/market_regime_alpha/candidates | CE-008 | docs/research/Candidate-Research.md; Negative-and-Inconclusive-Results.md | Frozen protocol conclusion wins. | Negative primary result retained. | RESOLVED |
| CF-006 | Candidate rank | Entry/trade action | DOMAIN_COLLAPSE | Ranking could be presented as buy instruction. | symbol:CandidatePrediction | CE-006 | docs/specs/CandidateRecommendation.md; EntryAssessment.md | Separate domain authorities. | Candidate schema forbids action fields. | RESOLVED |
| CF-007 | Legacy PositionState | canonical actual position | AUTHORITY_COLLISION | Legacy inferred state could be mistaken for actual account truth. | path:src/market_regime_alpha/dividend_t | CE-006 | docs/specs/PositionSnapshot.md; WP-D6 | Observed fills own position truth. | Legacy becomes view/control only. | OPEN_IMPLEMENTATION |
| CF-008 | Draft PR #12 | main implementation | BRANCH_STATE | Pending platform kernel could be reported as merged. | path:docs/status/Current-State.md | CE-003 | docs/status/Current-State.md; Capability-Matrix.md | Current branch code wins. | Recorded as PENDING_PR. | RESOLVED |
| CF-009 | single authority order | normative vs factual authority | AUTHORITY_MODEL | One list put design documents ahead of code for implementation facts. | path:docs/README.md; path:AGENTS.md | CE-005 | docs/README.md; AGENTS.md | Different questions need different orders. | Split into two explicit orders. | RESOLVED |
| CF-010 | Target horizon | mandatory holding/exit | SEMANTIC_COLLAPSE | Prediction horizon could dictate lifecycle behavior. | path:docs/research/Entry-Research.md | CE-006 | Strategy Constitution; Lifecycle/Exit research | Target and policy are independent. | Explicit invariant retained. | RESOLVED |
| CF-011 | Codex daily diagnosis | automatic model changes | GOVERNANCE | Fast feedback could become daily auto-tuning. | path:docs/research/Failure-Attribution.md | CE-001 | WP-D10; Current Research Program | Human-governed slow loop wins. | Typed proposals and approval gate. | RESOLVED |
| CF-012 | dated superpowers plans | current roadmap | NAVIGATION_COLLISION | Old dated tasks obscured current dependencies. | path:docs/archive/superpowers | CE-004 | docs/roadmap/work-packages/README.md | Current roadmap must be unique. | Archived and superseded. | RESOLVED |

Open implementation conflicts remain visible until code, tests and artifacts close them.
