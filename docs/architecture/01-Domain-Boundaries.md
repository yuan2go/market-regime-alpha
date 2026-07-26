# Domain Boundaries

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context ownership index  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 00-System-Context.md, domains/README.md, 02-End-to-End-Research-and-Decision-Flow.md, ../specs/README.md  
> **Code Evidence:** path:src/market_regime_alpha

| Domain | Responsibility | Owned entities | Current code mapping | Missing implementation |
|---|---|---|---|---|
| [Data Source and PIT](domains/00-Data-Source-and-PIT.md) | Own provider identity, raw payload preservation, field semantics, availability/finality, source manifests and evidence ceilings. | ProviderReference, RawSourceArtifact, SourceManifest, DatasetContract, DataQualityReport | src/market_regime_alpha/data/**, src/market_regime_alpha/research/xuntou_*, Tencent/BaoStock exploratory adapters | canonical daily SourceManifest service, cross-provider semantic conformance suite, daily freshness SLA registry |
| [Calendar and Universe](domains/01-Calendar-and-Universe.md) | Own sessions, PIT stock/ETF membership, eligibility and complete population accounting. | TradingCalendar, MarketSession, UniverseSnapshot, EligibilitySnapshot, ExclusionRecord | src/market_regime_alpha/data/trading_calendar.py, src/market_regime_alpha/universe/** | canonical daily stock/ETF universe service, PIT theme/industry/ETF mappings, production liquidity policy registry |
| [Market Context](domains/02-Market-Context.md) | Own descriptive market breadth, regime and risk-state snapshots; no default hard-gate authority. | MarketContextSnapshot, MarketBreadthRow, RegimeAssessment | MR2 research paths, Legacy market environment components | Phase D MarketContextSnapshot implementation, ablation-ready context registry, role-specific approval for feature/gate/budget use |
| [ETF Direction](domains/03-ETF-Direction.md) | Own PIT ETF universe, relative-strength/flow context and ETF-specific ranking evidence. | ETFDirectionSnapshot, ETFDirectionRow, ETFMapping | no canonical Phase D implementation, Legacy/prototype ETF backtests | PIT ETF universe and mappings, ETFDirectionSnapshot service, ETF outcome and scorecard lane |
| [Theme Direction](domains/04-Theme-Direction.md) | Own PIT theme membership, breadth, leaders, relative strength and quantified lifecycle state. | ThemeDirectionSnapshot, ThemeDirectionRow, ThemeMembershipSnapshot | no canonical Phase D implementation, Legacy concept/theme observations | PIT mapping store, theme breadth/leader materializer, theme lifecycle validation lane |
| [Capital Context](domains/05-Capital-Context.md) | Own market liquidity and capital-flow observations with per-field availability and authority. | CapitalContextSnapshot, CapitalFieldAvailability | partial Legacy features, no canonical Phase D implementation | CapitalContextSnapshot service, availability registry, incremental validation |
| [Feature and Factor](domains/06-Feature-and-Factor.md) | Own versioned feature definitions, materialization, lineage, availability and approval state. | FeatureDefinition, FeatureMaterialization, FeatureSetDefinition, ObservableDefinition | src/market_regime_alpha/features/** | persistent Feature registry, theory/observable approval workflow, broader approved feature catalog |
| [Candidate Discovery](domains/07-Candidate-Discovery.md) | Own complete eligible cross-section predictions, rankings and explainable recommendation projections. | CandidatePopulation, CandidatePrediction, PredictionRun, CandidateRecommendation | src/market_regime_alpha/candidates/**, WP3 provider-backed Candidate research; non-canonical V1 compatibility recommendation under `daily_research/**` | canonical daily multi-model Prediction Ledger, structured CandidateRecommendation persistence/API, regularized B2+ challengers |
| [Entry](domains/08-Entry.md) | Own path-aware opening suitability and the incremental comparison against Candidate-only baselines. | EntryAssessment, EntryModelDefinition, EntryPathTarget | src/market_regime_alpha/strategies/entry/**; non-canonical V1 compatibility assessment under `daily_research/**` | canonical Entry model/gate, EntryAssessment service, incremental Entry scorecards |
| [Position Lifecycle](domains/09-Position-Lifecycle.md) | Own actual position state, thesis continuity and HOLD/ADD/REDUCE/ROTATE assessments. | PositionSnapshot, HoldingAssessment, PositionThesis | Legacy PositionState only | canonical position ledger, reconciliation service, Holding model/assessment |
| [Exit](domains/10-Exit.md) | Own independent exit/reduction reasons, continuation targets and exit-quality evaluation. | ExitAssessment, ExitModelDefinition, ExitContinuationTarget | Legacy sell-side rules only | canonical Exit targets/models/assessments, control arms, exit scorecards |
| [Portfolio](domains/11-Portfolio.md) | Own capital/risk allocation across validated proposals and simulation under A-share constraints. | PortfolioDecision, RiskBudget, SimulationResult | Legacy position sizing/backtests | canonical PortfolioDecision, strategy composition validator, execution simulator |
| [Manual Execution Record](domains/12-Manual-Execution-Record.md) | Own human decisions, order intent, actual fills, cancellations and deviations from proposals. | ManualTradeRecord, Fill, ManualDecision | no canonical implementation | write API/UI, fill reconciliation, manual deviation analytics |
| [Review and Attribution](domains/13-Review-and-Attribution.md) | Own observed outcomes, layer-specific metrics, failure attribution, rolling scorecards and controlled research proposals. | RecommendationOutcome, DailyReviewReport, FailureAttribution, RollingScorecard | Candidate diagnostics and research artifacts | automatic outcome matcher, daily review pipeline, failure taxonomy runtime, rolling scorecards |
| [Research Artifact](domains/14-Research-Artifact.md) | Own immutable experiment, model, target, run, outcome, evaluation and promotion identities. | ExperimentIdentity, ModelDefinition, TargetDefinition, EvaluationProtocol, ResearchArtifact, PromotionDecision | src/market_regime_alpha/research/**, src/market_regime_alpha/platform/** | hardened persistent/recoverable platform repositories, canonical daily decision artifact profiles, promotion workflow integration |
| [Application and QuantDesk](domains/15-Application-QuantDesk.md) | Own read models, workflow initiation and human capture surfaces without owning model/data/account truth. | WorkbenchView, TaskRequest, ApprovalRequest | Legacy FastAPI dashboards | Phase D API gateway/read models, three workbenches, manual capture/approval flows |
| [Legacy Compatibility](domains/16-Legacy-Compatibility.md) | Characterize, adapt and retire Legacy behavior without expanding Legacy God Objects. | LegacyAdapter, CharacterizationEvidence, MigrationDecision | src/market_regime_alpha/dividend_t/**, src/market_regime_alpha/legacy/** | component extraction inventory, caller migration ledger, retirement gates |

Detailed Commands, Queries, Events, input/output contracts, invariants and failure modes are maintained in [the domain design index](domains/README.md).

## Global invariants

1. Each authoritative entity has one owning domain.
2. Dashboards never recompute canonical predictions.
3. Candidate outputs do not contain Entry/Exit/trade actions.
4. Position state comes from observed manual/broker records.
5. Exit is independently modeled and evaluated.
6. Result-affecting data and model evidence are immutable and content-addressed.
