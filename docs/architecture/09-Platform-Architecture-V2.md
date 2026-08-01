# Platform Architecture V2

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Current architecture for the Platform V2 research boundary  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 01-Domain-Boundaries.md, 03-Research-Artifact-Architecture.md, 05-Phase-D-Daily-Decision-Engine-V1.md, 10-Production-Decision-Lifecycle.md, decisions/ADR-003-Platform-V2-Research-Artifact-Boundary.md, decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../roadmap/work-packages/WP-PAV2-Platform-Architecture-V2-and-Research-Layer-MVP.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md  
> **Code Evidence:** Platform V2 implementation baseline `feat/platform-architecture-v2-research-layer@45fdaa9`; production-decision extension is documented target state only.

## Scope

Platform V2 adds stable domain seams around the existing evidence, Candidate and daily-decision implementations. It does not move or rename established contracts. The first executable vertical slice is an offline Research Layer:

```text
ResearchInputBundle
→ MarketRegimeSnapshot
→ ThemeRotationSnapshot
→ CapitalEvolutionSnapshot
→ CandidateSet
→ ResearchLayerArtifact
```

This slice accepts only explicitly labelled synthetic fixtures or historical immutable archives. It is not a LIVE Provider path and it establishes neither formal PIT nor formal OOS Alpha.

## Six layers and authority

The executable boundary catalog is `src/market_regime_alpha/platform/architecture_v2.py`.

| Layer | Owns | Must not own in this delivery |
|---|---|---|
| 0 — Data & Evidence | SourceManifest, time, lineage, eligibility and immutable evidence | model rank, trade state or orders |
| 1 — Research & Opportunity Discovery | regime, theme priority, inferred capital state and CandidateSet | buy/sell, position or execution |
| 2 — Signal & Timing | versioned SignalSnapshot and forecast contracts | live entry authority |
| 3 — Trade Decision & Risk | research decision and PositionPlan contracts | broker mutation |
| 4 — Position Lifecycle & Execution | simulation records and future actual-position boundary | unattended trading in this repository |
| 5 — Outcome Evaluation & Learning | layer-scoped EvaluationReport | automatic model mutation or promotion |

The packages `signals`, `forecasting`, `decision`, `portfolio`, `execution`, `position` and `evaluation` define only the future ownership boundary in the WP-PAV2 delivery. Layer 1 is the only executable Platform V2 model flow at the current implementation baseline.

## Evidence boundary

`ResearchInputBundle` is a strict typed boundary around:

- the existing SourceManifest;
- existing Universe, Eligibility and Decision Price snapshots;
- decision-time market, theme, ETF and symbol observations;
- theme membership and daily-bar evidence;
- existing immutable B0/B1 PredictionRuns;
- input Artifact identities and hashes.

Every observation has an Availability Time, and bundle construction rejects values available after Decision Time. The boundary exposes no `LIVE` fixture alias: evidence is either `SYNTHETIC_FIXTURE` or `HISTORICAL_IMMUTABLE_ARCHIVE`.

Internals may use ordinary numerical collections, but no untracked DataFrame crosses this boundary.

## Research contracts

### Market Regime

`MarketRegimeSnapshot` is a research gate, not a trading signal. V0 adapts the four observable MR2A metrics and an optional limit-structure proxy into direction, breadth, liquidity, volatility and risk-appetite scores. Missing coverage produces `DATA_INSUFFICIENT`, `PROHIBIT` and zero maximum gross exposure; no default `RISK_ON` exists.

### Theme Rotation

`ThemeRotationSnapshot` ranks configured themes by deterministic, versioned relative-strength, amount, breadth, leader, participation and persistence proxies. It emits theme priority, never stock action.

The current V0 label is calculated from the current observation and score. It does not yet establish a historical lifecycle state machine with previous-state duration or hysteresis.

### Capital Evolution

`CapitalEvolutionSnapshot` contains theme-level and symbol-level inferred states. V0 is explicitly a deterministic scoring and gate model over observable proxies. It does not claim hidden institutional or individual actor intent.

The current state label is a score classification for one input bundle. A future historical lifecycle model must receive a separate contract and validation protocol rather than silently changing V0 semantics.

### Candidate Discovery

`CandidateSet` reconciles every Universe member to `SELECTED`, `WATCHLIST`, `REJECTED` or `DATA_INSUFFICIENT`. It requires Market, Theme and Capital gates plus eligibility, liquidity, history and known status. The legacy B0 and B1 outputs enter only through `LegacyCandidateDiscoveryAdapter` as frozen percentile factors; they remain immutable PredictionRuns and are never described as probabilities.

## Gate semantics

- `TradePermission.PROHIBIT` preserves Theme and Capital research but rejects the complete Candidate population with `MARKET_REGIME_PROHIBITS_RISK`.
- insufficient Theme evidence blocks Candidate selection; there is no market-wide stock fallback.
- insufficient Capital Evolution evidence cannot be bypassed by B0/B1.
- falling below the Research Pipeline minimum emits `CANDIDATE_POPULATION_INSUFFICIENT`; this is distinct from the Phase D source DataQuality status.
- every input symbol remains present with explicit reasons.

## Artifact and replay

`ArtifactEnvelope` provides a strict common V1 envelope for new Platform V2 Artifacts. `ResearchLayerArtifact` is a separate exact-file-set package with atomic non-overwrite publication, SHA-256 checksums, a semantic Reader, versioned Reader registry and deterministic recomputation.

The Application entry point is `PlatformResearchRunner`; the CLI is `scripts/run_research_layer.py`. Replaying verifies the package before recomputing all four layers with the frozen configuration and code revision. An equality mismatch is a hard failure.

## Compatibility boundary

The following remain independent:

- the historical `daily_research` V1 six-file Artifact, IDs, Reader and `ENTER` semantics;
- Phase D Daily Decision Artifact and Reader registry;
- DailyLoop acquisition, Runtime Journal and settlement;
- B0/B1 definitions, weights, ranks and PredictionRun identities.

Platform V2 does not rename any of them or route old schemas through the new Research Layer Reader.

## Authority ceiling

Every new Artifact records:

```text
data_eligibility = EXPLORATORY
formal_pit = FORMAL_PIT_NOT_ESTABLISHED
formal_oos_alpha = FORMAL_OOS_ALPHA_NOT_ESTABLISHED
trading_authority = TRADING_AUTHORITY_NOT_GRANTED
```

Successful replay cannot raise that ceiling.

## Production decision lifecycle extension

[Production Decision Lifecycle](10-Production-Decision-Lifecycle.md) defines the
next architecture increment. Its Phase 0–7 engineering slices are implemented
on the delivery branch without changing the authority ceiling of Platform V2:
the evidence remains EXPLORATORY, parameters remain unvalidated and no LIVE
execution authority exists.

The accepted organization is:

```text
existing repository
+ modular monolith
+ explicit bounded contexts
+ application orchestration
+ immutable evidence authority
+ manual fill authority for actual positions
+ optional external broker adapter only after separate approval
```

The dependency-ordered target work is:

1. operational Daily Artifact to ResearchInputBundle adapter;
2. durable Model Registry and Experiment Governance;
3. executable Signal Engine and multi-horizon PathForecast;
4. TradingOpportunity and TradingThesis;
5. PortfolioDecision and independent RiskDecision;
6. append-only manual execution ledger and fill-derived PositionSnapshot;
7. independent Holding/Exit assessments and complete-trade attribution;
8. sustained shadow operation and operator surface.

The fixed MR1 next-session 10:30 path remains independent. Phase 0–7
components may be described only at their observed engineering status in the
Current State, Capability Matrix and delivery audit; none may be described as
production-qualified without separate evidence.
