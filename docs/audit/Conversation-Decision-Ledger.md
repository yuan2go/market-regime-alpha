# Conversation Decision Ledger

> **Status:** CURRENT_STATUS  
> **Authority:** Traceability record for available conversation decisions  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Conversation-to-Repository-Traceability.md, ../status/Current-State.md  
> **Code Evidence:** Conversation evidence; no runtime authority

| decision_id | decision | decision_date_or_order | decision_type | status | supersedes | affected_domains | affected_documents | supporting_conversation |
|---|---|---|---|---|---|---|---|---|
| CD-001 | Alpha Research OS identity | 2026-07 project sequence | PROJECT_IDENTITY | FROZEN | single-strategy/Dividend-T identity | All | constitution, README | Current project conversation and audit instruction |
| CD-002 | Current product is A-share research and manual decision support | latest | PROJECT_IDENTITY | FROZEN |  | Application, execution | Current State, Phase D | Current user instruction |
| CD-003 | Canonical end-to-end chain includes context, Candidate, Entry, Lifecycle, Exit, Portfolio, review | latest | ARCHITECTURE | FROZEN |  | All | Architecture 00–05 | Current user instruction |
| CD-004 | Prediction/action authorities remain separate | latest | ARCHITECTURE | FROZEN |  | Candidate through execution | Strategy Constitution/specs | Current user instruction |
| CD-005 | Target horizon does not dictate holding/exit | latest | RESEARCH | FROZEN |  | Target/Lifecycle/Exit | Research/specs | Current user instruction |
| CD-006 | Exit is independent, not inverse Entry | latest | MODEL | FROZEN |  | Entry/Exit | Exit Research/spec | Current user instruction |
| CD-007 | Score is not probability without calibration | latest | MODEL | FROZEN |  | Models | AGENTS/specs | Current user instruction |
| CD-008 | Empty Candidate/NO_ACTION valid; NO_ACTION != HOLD | latest | RESEARCH | FROZEN |  | Decision/Lifecycle | Specs | Current user instruction |
| CD-009 | Xuntou primary; public data auxiliary/exploratory | latest | DATA | CURRENT |  | Data/Provider | Data semantics/status | Current user instruction |
| CD-010 | No automatic QMT/PTrade/unattended execution in current stage | latest | NON_GOAL | FROZEN |  | Execution | Project Vision/Current State | Current user instruction |
| CD-011 | Legacy migrates incrementally via Strangler boundary | latest | LEGACY_MIGRATION | FROZEN | big-bang rewrite | Legacy | Legacy Migration | Current user instruction |
| CD-012 | QuantDesk is workbench/UI only | latest | APPLICATION_UI | CURRENT |  | Application | QuantDesk Boundary | Current user instruction |
| CD-013 | Candidate first, then Entry/Lifecycle/Exit as separate validation layers | project sequence | ROADMAP | CURRENT |  | Research domains | Current Research Program | Project conversation |
| CD-014 | Theories must become versioned Observables/Features/Signals | today | MODEL | FROZEN |  | Knowledge/Factor | Factor Constitution | Today discussion |
| CD-015 | Models compare only in frozen comparable lanes | today | RESEARCH | FROZEN |  | Evaluation | Validation/Ablation | Today discussion |
| CD-016 | No naive all-model leaderboard across strategy families | today | RESEARCH | FROZEN |  | Evaluation/Portfolio | Research framework | Today discussion |
| CD-017 | Codex diagnoses/proposes but cannot mutate/promote/execute | today | RESEARCH | FROZEN |  | Feedback/Governance | Failure Attribution/Ops | Today discussion |
| CD-018 | Daily feedback fast; model decisions slow and controlled | today | RESEARCH | CURRENT |  | Feedback | Current Research Program | Today discussion |
| CD-019 | Free data can run engineering/exploratory loop with explicit ceiling | today | DATA | CURRENT |  | Data/Daily loop | Data semantics | Today discussion |
| CD-020 | Incrementally platformize this repository; no second platform or big-bang rewrite | today | ARCHITECTURE | FROZEN | finish-old-then-new | Repository | Roadmap | Today discussion |
| CD-021 | Platform kernel five-item work package | today | ROADMAP | CURRENT |  | Platform | PR #12 status | Today discussion |
| CD-022 | Phase D daily products include context, Candidate, Entry, positions, review, attribution | latest | ROADMAP | FROZEN |  | Phase D | Architecture/Specs | Current user instruction |
| CD-023 | Profit is evidence outcome, never an implementation promise | project-wide | RESEARCH | FROZEN |  | Validation | Validation Constitution | Project instructions |

## Evidence limitation

The current project conversation and supplied audit instruction are available. A separately preserved raw transcript referenced by older repository audits is not a tracked file and was not supplied independently. Exact quotes from that missing artifact are classified `MISSING_CONVERSATION_EVIDENCE`; this ledger does not reconstruct them from memory.
