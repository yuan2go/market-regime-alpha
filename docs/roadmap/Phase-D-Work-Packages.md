# Phase D Work Packages

> **Status:** ROADMAP  
> **Authority:** Executable ordered roadmap for the A-share daily decision engine  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md, ../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be linked by each work package

| Work package | Objective | Bounded context | Dependencies | New contracts/outputs | Code work | Acceptance tests/evidence | Explicit non-goals |
|---|---|---|---|---|---|---|---|
| WP-D0 | Merge platform governance kernel | Platform/Governance | PR #12 or equivalent | Model/Target/Evaluation/Experiment registries | Review/rebase, migrations and tests | CI green; no main semantic regression | No daily data or Alpha claim |
| WP-D1 | Daily data source manifest and quality gates | Data/PIT | provider adapters/time contracts | SourceManifest, DataQualityReport | canonical ingestion and fail-closed checks | replay reconstructs exact inputs | No new model |
| WP-D2 | Daily calendar, stock/ETF universe and eligibility | Calendar/Universe | WP-D1 | DailyResearchSnapshot shell, UniverseSnapshot | PIT stock/ETF builders and mappings | unknowns block; snapshots content-addressed | No context scoring |
| WP-D3 | Market/ETF/theme/capital context | Context | WP-D2 | four context snapshots | transparent baseline context features | ablation-ready snapshots and quality | No hard gate authority |
| WP-D4 | Multi-model Candidate Prediction Ledger | Candidate | WP-D0–D3 | PredictionRun, CandidateRecommendation | adapt B0/B1 and challengers | full ranks/rejections frozen; comparable lane | No Entry/portfolio |
| WP-D5 | Entry Assessment V1 | Entry | WP-D4, Entry Path targets | EntryAssessment | fixed baselines and first Entry model | MAE/MFE incremental evaluation | No auto order |
| WP-D6 | Manual Trade and canonical Position state | Manual/Lifecycle | WP-D4–D5 | ManualTradeRecord, PositionSnapshot | write API and reconciliation | actual fills create state; deviations tracked | No broker sync |
| WP-D7 | Holding and Exit V1 | Lifecycle/Exit | WP-D6 | HoldingAssessment, ExitAssessment | independent targets/models | giveback/drawdown/regret evaluation | No inverse Entry |
| WP-D8 | Outcome, review and failure attribution | Review | WP-D4–D7 | RecommendationOutcome, DailyReviewReport | automatic matching and scorecards | 5/20/60-day reproducible reports | No model mutation |
| WP-D9 | Portfolio and execution simulation | Portfolio/Execution | validated D4–D8 | PortfolioDecision, SimulationResult | T+1/cost/concentration/capacity | risk-adjusted simulations | No real order |
| WP-D10 | Codex research feedback | Feedback | WP-D8 | ResearchEvidencePack, Proposal | sandboxed diagnosis and experiment drafting | facts/hypotheses separated; human approval | No auto promotion |
| WP-D11 | Qualified Xuntou replication and shadow | Validation/Ops | external input + D4/D8 | formal artifacts/shadow ledger | run sealed protocol and daily shadow | authority only if gates pass | No profitability promise |
| WP-D12 | QuantDesk workbench integration | Application | stable Phase D APIs | read/write workbench APIs | UI projections/manual capture | UI has no model/data/account authority | No logic duplication |

## Stop conditions

A work package stops when required PIT evidence is unavailable, a parent model fails its gate, population coverage is below protocol, or the proposed change cannot be isolated. Failure results are documented; scope is not expanded to manufacture success.

## Documentation update rule

Each merged WP updates Current-State, Capability-Matrix, Gap-Register, relevant specification and code evidence. Constitution changes require explicit user authorization.
