# Conversation-to-Repository Traceability

> **Status:** CURRENT_STATUS  
> **Authority:** Decision-to-Constitution-to-code traceability  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Conversation-Decision-Ledger.md, ../status/Capability-Matrix.md  
> **Code Evidence:** main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

| Decision | Constitution | Current design/spec | Main code/test evidence | Current state | Action |
|---|---|---|---|---|---|
| Alpha Research OS identity | `00`, `02` | architecture `00–02` | package/domain structure | CURRENT | Keep and clarify. |
| Candidate ≠ Entry ≠ Lifecycle ≠ Exit | `06`, `09` | Candidate/Entry/Lifecycle/Exit research and specs | Candidate contracts; Entry Path Target only | PARTIAL | Implement Phase D contracts separately. |
| PIT and availability semantics | `04` | architecture `04` | core/time, data/contracts, universe, Xuntou v4 | IMPLEMENTED_AND_VERIFIED for contracts | Preserve; real provider remains blocked. |
| Candidate B0/B1 | `03`, `05`, `07` | Candidate Research | candidates/baselines, composite_baseline and tests | IMPLEMENTED_AND_VERIFIED | Connect to daily prediction ledger. |
| Model Registry/experiment governance | `03`, `07` | Phase D roadmap | Draft PR #12 only | PENDING_PR / CONTRACT_ONLY on main | Review and merge before platform work. |
| Entry Path Target | `06`, `07` | Entry Research, existing Entry Path spec | strategies/entry and tests | IMPLEMENTED_AND_VERIFIED infrastructure | Do not mislabel as Entry model. |
| Position/Holding/Exit | `06` | Lifecycle and Exit research/specs | Legacy PositionState only | DESIGNED_ONLY / LEGACY_ONLY | Implement canonical position authority. |
| Manual execution attribution | `06`, `07` | ManualTradeRecord spec | no canonical main implementation | DESIGNED_ONLY | Phase D WP-D6. |
| Codex feedback | `03`, `07` | Failure Attribution and Ops | no canonical evidence pack | DESIGNED_ONLY | Phase D WP-D8. |
| Auto execution non-goal | `00`, `01`, `06` | Current State | Legacy broker adapters only | LEGACY_ONLY | Keep adapter boundary; no execution authority. |
| QuantDesk workbench | `02` | architecture `07` | no code in repository | NOT_STARTED | Integrate only via read/query APIs later. |
