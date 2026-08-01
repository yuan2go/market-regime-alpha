# Domain Boundaries

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context ownership index  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 00-System-Context.md, domains/README.md, 02-End-to-End-Research-and-Decision-Flow.md, 09-Platform-Architecture-V2.md, 10-Production-Decision-Lifecycle.md, ../specs/README.md  
> **Code Evidence:** `src/market_regime_alpha`; target mappings are explicitly distinguished from current implementation.

| Domain | Responsibility | Owned entities | Current code mapping | Missing implementation |
|---|---|---|---|---|
| [Data Source and PIT](domains/00-Data-Source-and-PIT.md) | Own provider identity, raw payload preservation, field semantics, availability/finality, source manifests and evidence ceilings. | ProviderReference, RawSourceArtifact, SourceManifest, DatasetContract, DataQualityReport | `data/**`, `research/xuntou_*`, Tencent/BaoStock exploratory adapters | formal provider/PIT authority, cross-provider conformance, freshness SLA registry |
| [Calendar and Universe](domains/01-Calendar-and-Universe.md) | Own sessions, PIT stock/ETF membership, eligibility and complete population accounting. | TradingCalendar, MarketSession, UniverseSnapshot, EligibilitySnapshot, ExclusionRecord | `data/trading_calendar.py`, `universe/**` | canonical daily stock/ETF universe service, PIT theme/industry/ETF mappings, production liquidity policy registry |
| [Market Context](domains/02-Market-Context.md) | Own descriptive market breadth, regime and risk-state snapshots; no stock action authority. | MarketContextSnapshot, MarketBreadthRow, RegimeAssessment | `research/market_regime/**`, MR2 research paths, Legacy market components | operational input adapter, historical evaluation, approved role as context/gate/budget input |
| [ETF Direction](domains/03-ETF-Direction.md) | Own PIT ETF universe, relative-strength/flow context and ETF-specific ranking evidence. | ETFDirectionSnapshot, ETFDirectionRow, ETFMapping | Platform V2 ETF observation contract; Legacy/prototype ETF backtests | PIT ETF universe/mappings, ETFDirectionSnapshot service, ETF outcome and scorecard lane |
| [Theme Direction](domains/04-Theme-Direction.md) | Own PIT theme membership, breadth, leaders, relative strength, cross-sectional priority and quantified lifecycle state. | ThemeDirectionSnapshot, ThemeRotationSnapshot, ThemeLifecycleSnapshot, ThemeMembershipSnapshot | `research/theme_rotation/**` V0 plus typed observations | PIT mapping store, operational materializer, historical lifecycle/hysteresis and validation lane |
| [Capital Context](domains/05-Capital-Context.md) | Own market liquidity and observable capital-flow context with per-field availability and authority. | CapitalObservableSnapshot, CapitalLifecycleSnapshot, CapitalFieldAvailability | `research/capital_evolution/**` V0 plus partial Legacy features | operational observables, historical lifecycle, overlap ablation and incremental validation |
| [Feature and Factor](domains/06-Feature-and-Factor.md) | Own versioned feature definitions, materialization, lineage, availability and approval state. | FeatureDefinition, FeatureMaterialization, FeatureSetDefinition, ObservableDefinition | `features/**` | persistent Feature registry, theory/observable approval workflow, broader approved feature catalog |
| [Candidate Discovery](domains/07-Candidate-Discovery.md) | Own complete eligible cross-section predictions, rankings and explainable candidate reconciliation. | CandidatePopulation, CandidatePrediction, PredictionRun, CandidateSet, CandidateRecommendation projection | `candidates/**`, `platform/prediction_run.py`, `research/candidate_discovery/**`, `daily_decision/recommendation.py`; compatibility recommendation under `daily_research/**` | durable/formal Prediction Ledger authority, historical evaluation, structured query/API surface and B2+ challengers |
| [Entry](domains/08-Entry.md) | Own path-aware opening suitability, signal timing and incremental comparison against Candidate-only baselines. | SignalSnapshot, PathForecast, EntryAssessment, EntryModelDefinition, EntryPathTarget | `strategies/entry/**`, contract boundaries under `signals/**` and `forecasting/**`, non-ENTER plumbing under `daily_decision/entry.py`; historical compatibility assessment under `daily_research/**` | executable Signal Engine, multi-horizon PathForecast, validated Entry/Opportunity protocol and incremental scorecards |
| [Trade Decision and Risk](domains/17-Trade-Decision-and-Risk.md) | Own TradingOpportunity, TradingThesis, invalidation, portfolio proposal and independent hard-risk permission before execution. | TradingOpportunity, TradingThesis, InvalidationCondition, RiskDecision | thin simulation boundary in `decision/contracts.py`; target design in Architecture 10 | stateful aggregates, repositories, expiry/invalidation, audit, permissions and fail-closed Risk Authority |
| [Position Lifecycle](domains/09-Position-Lifecycle.md) | Own actual position state, thesis continuity and HOLD/ADD/REDUCE/ROTATE assessments. | PositionSnapshot, PositionLot, HoldingAssessment, PositionThesis | Legacy PositionState; thin target contracts under `position/**` | canonical fill-derived position ledger, reconciliation service and Holding model |
| [Exit](domains/10-Exit.md) | Own independent exit/reduction reasons, continuation targets and exit-quality evaluation. | ExitAssessment, ExitModelDefinition, ExitContinuationTarget | Legacy sell-side rules; thin target contract under `position/contracts.py` | canonical Exit targets/models/assessments, control arms and exit scorecards |
| [Portfolio](domains/11-Portfolio.md) | Own capital/risk allocation across validated theses under A-share constraints. | PortfolioDecision, TargetPosition, RiskBudget, PortfolioConstraint, SimulationResult | Legacy position sizing/backtests; thin target contract under `portfolio/**` | canonical constructor, hard-risk integration, strategy composition validator and simulator |
| [Manual Execution Record](domains/12-Manual-Execution-Record.md) | Own human decisions, order intent, actual fills, corrections, cancellations and deviations from proposals. | ManualTradeRecord, Fill, ManualDecision, ExecutionDeviation | simulation-only boundary under `execution/**`; no canonical manual ledger | append-only write API/CLI, idempotency, fill correction, reconciliation and deviation analytics |
| [Review and Attribution](domains/13-Review-and-Attribution.md) | Own observed outcomes, layer-specific metrics, failure attribution, rolling scorecards and controlled research proposals. | RecommendationOutcome, TradeOutcome, DailyReviewReport, AttributionReport, FailureAttribution, RollingScorecard | Candidate diagnostics, research artifacts, generic `evaluation/**` contract and exploratory MR1 Outcome/DailyReview under `daily_decision/**` | broader-horizon outcome matching, complete-trade attribution, failure taxonomy runtime and rolling scorecards |
| [Research Artifact](domains/14-Research-Artifact.md) | Own immutable experiment, model, target, run, outcome, evaluation and promotion identities. | ExperimentIdentity, ModelDefinition, TargetDefinition, EvaluationProtocol, ResearchArtifact, PromotionDecision | `research/**`, `platform/**`, `evidence/**` | persistent/recoverable Model Registry and Experiment Governance, later-layer artifact profiles and promotion integration |
| [Application and QuantDesk](domains/15-Application-QuantDesk.md) | Own workflow initiation, orchestration, queries and human capture surfaces without owning model/data/account truth. | WorkbenchView, TaskRequest, ApprovalRequest, ApplicationCommand, ApplicationQuery | `application/daily_loop/**`, `application/research_layer/**`, Legacy FastAPI dashboards | operational-research bridge, trading-lifecycle/review application services, API/read models, operator capture and approval flows |
| [Legacy Compatibility](domains/16-Legacy-Compatibility.md) | Characterize, adapt and retire Legacy behavior without expanding Legacy God Objects. | LegacyAdapter, CharacterizationEvidence, MigrationDecision | `dividend_t/**`, `legacy/**`, frozen `daily_research/**` compatibility | component extraction inventory, caller migration ledger and retirement gates |

Detailed Commands, Queries, Events, input/output contracts, invariants and failure modes are maintained in [the domain design index](domains/README.md). The target cross-domain orchestration and persistence strategy is defined in [Production Decision Lifecycle](10-Production-Decision-Lifecycle.md).

## Global invariants

1. Each authoritative entity has one owning domain.
2. Dashboards and adapters never recompute canonical predictions.
3. Candidate outputs do not contain Entry, Exit or execution actions.
4. Signal and Forecast evidence do not create actual positions.
5. TradingOpportunity and TradingThesis precede Portfolio and Risk decisions.
6. Risk rejection cannot produce an approved execution intent.
7. Position state comes only from observed manual or future broker fills.
8. Fill and governance transition histories are append-only.
9. Exit is independently modeled and evaluated.
10. Result-affecting data and model evidence are immutable and content-addressed.
11. Application services orchestrate domains but do not own their truth.
12. Existing MR1 and `daily_research` compatibility identities do not change meaning silently.
