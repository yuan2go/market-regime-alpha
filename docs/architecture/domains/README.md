# Phase D and Production Decision Domain Design Index

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Detailed bounded-context ownership, commands, queries, events and failure behavior  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../02-End-to-End-Research-and-Decision-Flow.md, ../10-Production-Decision-Lifecycle.md  
> **Code Evidence:** `src/market_regime_alpha`; target production-decision domains are documentation-only until delivery evidence exists.

1. [Data Source and PIT](00-Data-Source-and-PIT.md)
2. [Calendar and Universe](01-Calendar-and-Universe.md)
3. [Market Context](02-Market-Context.md)
4. [ETF Direction](03-ETF-Direction.md)
5. [Theme Direction](04-Theme-Direction.md)
6. [Capital Context](05-Capital-Context.md)
7. [Feature and Factor](06-Feature-and-Factor.md)
8. [Candidate Discovery](07-Candidate-Discovery.md)
9. [Entry](08-Entry.md)
10. [Position Lifecycle](09-Position-Lifecycle.md)
11. [Exit](10-Exit.md)
12. [Portfolio](11-Portfolio.md)
13. [Manual Execution Record](12-Manual-Execution-Record.md)
14. [Review and Attribution](13-Review-and-Attribution.md)
15. [Research Artifact](14-Research-Artifact.md)
16. [Application and QuantDesk](15-Application-QuantDesk.md)
17. [Legacy Compatibility](16-Legacy-Compatibility.md)
18. [Trade Decision and Risk](17-Trade-Decision-and-Risk.md)

## Cross-domain rules

1. One authoritative owner exists for every aggregate and mutable ledger.
2. Commands cross boundaries through typed application ports or events, never direct table mutation.
3. Every result-affecting output references immutable upstream identities.
4. Missing evidence and unavailable risk dependencies fail closed.
5. Application and UI projections do not recalculate domain truth.
6. Candidate and Signal outputs do not create actual positions.
7. Risk approval precedes any system-approved manual execution intent.
8. Position state is derived only from observed fills.
9. Holding and Exit remain independently modeled and evaluated.
10. Existing MR1 and `daily_research` compatibility identities do not change meaning silently.
