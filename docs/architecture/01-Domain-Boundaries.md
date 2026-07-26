# Domain Boundaries

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context ownership  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 00-System-Context.md, 02-End-to-End-Research-and-Decision-Flow.md, ../specs/README.md  
> **Code Evidence:** src/market_regime_alpha/**

| Domain | Responsibility | Owned entities | Current main mapping | Missing implementation |
|---|---|---|---|---|
| Data Source and PIT | Provider identity, raw artifacts, availability/finality, data eligibility | ProviderReference, SourceArtifact, DatasetContract | `data`, `research/xuntou_*`, Tencent composite | unified daily source manifest |
| Calendar and Universe | sessions, PIT membership and eligibility | TradingCalendar, UniverseSnapshot, EligibilitySnapshot | `data/trading_calendar.py`, `universe/**` | canonical stock/ETF daily universe service |
| Market Context | market breadth/regime/liquidity descriptors | MarketContextSnapshot | MR2 research, Legacy environment | Phase D canonical snapshot |
| ETF Direction | ETF universe, strength, flow/context | ETFDirectionSnapshot | no canonical implementation | full domain |
| Theme Direction | theme mapping, breadth, leaders, decay | ThemeDirectionSnapshot | no canonical implementation | PIT mappings and domain |
| Capital Context | turnover/liquidity/funding proxies | CapitalContextSnapshot | partial Legacy features | canonical domain |
| Feature and Factor | definitions, materialization, lineage | FeatureDefinition/Materialization | `features/**` | persistent registry and broader approved features |
| Candidate Discovery | complete population, ranking/predictions | CandidatePopulation, CandidatePrediction | `candidates/**`, WP3 | daily CandidateRecommendation ledger |
| Entry | path-aware opening suitability | EntryAssessment | Entry Path Target infrastructure | Entry model/gate and assessment |
| Position Lifecycle | actual manual position authority and thesis state | PositionSnapshot, HoldingAssessment | Legacy PositionState | canonical position authority |
| Exit | independent continuation/invalidation research | ExitAssessment | sell-side Legacy only | canonical target/model/assessment |
| Portfolio | capital/risk allocation across ideas | PortfolioDecision | position sizing Legacy | canonical portfolio simulator |
| Manual Execution Record | user decision/order/fill/deviation | ManualTradeRecord | no canonical implementation | complete domain |
| Review and Attribution | outcomes, rolling metrics, failures | RecommendationOutcome, DailyReviewReport | Candidate diagnostics/research artifacts | daily loop and attribution taxonomy |
| Research Artifact | immutable identity, readers, verifiers | Experiment/Artifact identities | `research/**` | unified daily decision artifacts |
| Application/QuantDesk | queries, visualizations, task initiation | read models/workbench state | Legacy FastAPI dashboards | Phase D API boundary |
| Legacy Compatibility | characterize and adapt old behavior | adapters/characterization evidence | `dividend_t`, `legacy/**` | component extraction inventory |

## Invariants

1. Each authoritative entity has one owning domain.
2. Dashboards never recompute canonical predictions.
3. Candidate outputs do not contain trade actions.
4. Position state comes from manual/broker records, not from yesterday's recommendation.
5. Exit is independently modeled and evaluated.
6. Data and model evidence are immutable and content-addressed where result-affecting.
