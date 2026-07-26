# Conversation Decision Ledger

> **Status:** CURRENT_STATUS  
> **Authority:** Traceability record for available conversation decisions  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Conversation-Evidence-Index.md, Conversation-to-Repository-Traceability.md, ../status/Current-State.md  
> **Code Evidence:** Conversation evidence; no runtime authority

| decision_id | decision | status | affected domains | affected documents | conversation evidence | confidence |
|---|---|---|---|---|---|---|
| CD-001 | Alpha Research OS identity | FROZEN | All | constitution, README | CE-001, CE-008 | HIGH |
| CD-002 | Current product is A-share research and manual decision support | FROZEN | Application, execution | Current State, Phase D | CE-004 | HIGH |
| CD-003 | Canonical chain includes context, Universe, Features, Candidate, Entry, Lifecycle, Exit, Portfolio, review | FROZEN | All | Architecture 00–05 | CE-001, CE-004 | HIGH |
| CD-004 | Prediction/action authorities remain separate | FROZEN | Candidate through execution | Strategy Constitution/specs | CE-006 | HIGH |
| CD-005 | Target horizon does not dictate holding/exit | FROZEN | Target/Lifecycle/Exit | Research/specs | CE-006 | HIGH |
| CD-006 | Exit is independent, not inverse Entry | FROZEN | Entry/Exit | Exit Research/spec | CE-006 | HIGH |
| CD-007 | Score is not probability without calibration | FROZEN | Models | AGENTS/specs | CE-004 | HIGH |
| CD-008 | Empty Candidate/NO_ACTION valid; NO_ACTION != HOLD | FROZEN | Decision/Lifecycle | Specs | CE-004 | HIGH |
| CD-009 | Xuntou formal direction; public data auxiliary/exploratory | CURRENT | Data/Provider | Data semantics/status | CE-007 | HIGH |
| CD-010 | No unattended QMT/PTrade execution in current stage | FROZEN | Execution | Project Vision/Current State | CE-004 | HIGH |
| CD-011 | Legacy migrates incrementally through compatibility boundaries | FROZEN | Legacy | Legacy Migration | CE-002 | HIGH |
| CD-012 | QuantDesk is workbench/UI only | CURRENT | Application | QuantDesk Boundary | CE-004 | MEDIUM |
| CD-013 | Candidate first; Entry/Lifecycle/Exit remain separate validation layers | CURRENT | Research | Current Research Program | CE-006 | HIGH |
| CD-014 | Theories become versioned Observables/Features/Signals | FROZEN | Knowledge/Factor | Factor Constitution | CE-001 | HIGH |
| CD-015 | Models compare only in frozen comparable lanes | FROZEN | Evaluation | Validation/Ablation | CE-001 | HIGH |
| CD-016 | No naive all-model leaderboard across strategy families | FROZEN | Evaluation/Portfolio | Research Framework | CE-001 | HIGH |
| CD-017 | Codex diagnoses/proposes but cannot mutate/promote/execute | FROZEN | Feedback/Governance | Failure Attribution/Ops | CE-001 | HIGH |
| CD-018 | Daily feedback is fast; model decisions are slow and governed | CURRENT | Feedback | Current Research Program | CE-001 | HIGH |
| CD-019 | Free data runs engineering/exploratory loop under explicit ceiling | CURRENT | Data/Daily loop | Data semantics/WP-D2E | CE-007 | HIGH |
| CD-020 | Platformize this repository; no second platform/big-bang rewrite | FROZEN | Repository | Roadmap | CE-002 | HIGH |
| CD-021 | Platform kernel five-item work package | CURRENT | Platform | PR #12 status | CE-003 | HIGH |
| CD-022 | Phase D includes context, Candidate, Entry, positions, review and attribution | FROZEN | Phase D | Architecture/Specs | CE-004 | HIGH |
| CD-023 | Profit is an evidence outcome, never an implementation promise | FROZEN | Validation | Validation Constitution | CE-008 | HIGH |
| CD-024 | Documentation correction set P0/P1/P2 is required before Ready for Review | CURRENT | Documentation | PR #13 | CE-005 | HIGH |

## Evidence rule

`DIRECT_CURRENT_CONVERSATION` is strongest for this reconstruction. `PROJECT_CONVERSATION` and `PROJECT_INSTRUCTION` are retained with explicit grades. No row is presented as a verbatim quote unless the raw transcript is repository-addressable.
