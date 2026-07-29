# Platform Architecture V2

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Current architecture for the Platform V2 research boundary
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** 01-Domain-Boundaries.md, 03-Research-Artifact-Architecture.md, 05-Phase-D-Daily-Decision-Engine-V1.md, decisions/ADR-003-Platform-V2-Research-Artifact-Boundary.md, ../roadmap/work-packages/WP-PAV2-Platform-Architecture-V2-and-Research-Layer-MVP.md
> **Code Evidence:** `feat/platform-architecture-v2-research-layer@45fdaa9`

## Scope

Platform V2 adds stable domain seams around the existing evidence, Candidate
and daily-decision implementations. It does not move or rename established
contracts. The first executable vertical slice is an offline Research Layer:

```text
ResearchInputBundle
→ MarketRegimeSnapshot
→ ThemeRotationSnapshot
→ CapitalEvolutionSnapshot
→ CandidateSet
→ ResearchLayerArtifact
```

This slice accepts only explicitly labelled synthetic fixtures or historical
immutable archives. It is not a LIVE Provider path and it establishes neither
formal PIT nor formal OOS Alpha.

## Six layers and authority

The executable boundary catalog is
`src/market_regime_alpha/platform/architecture_v2.py`.

| Layer | Owns | Must not own in this delivery |
|---|---|---|
| 0 — Data & Evidence | SourceManifest, time, lineage, eligibility and immutable evidence | model rank, trade state or orders |
| 1 — Research & Opportunity Discovery | regime, theme priority, inferred capital state and CandidateSet | buy/sell, position or execution |
| 2 — Signal & Timing | versioned SignalSnapshot and forecast contracts | live entry authority |
| 3 — Trade Decision & Risk | research decision and PositionPlan contracts | broker mutation |
| 4 — Position Lifecycle & Execution | simulation records and future actual-position boundary | unattended trading in this repository |
| 5 — Outcome Evaluation & Learning | layer-scoped EvaluationReport | automatic model mutation or promotion |

The packages `signals`, `forecasting`, `decision`, `portfolio`, `execution`,
`position` and `evaluation` define only the future ownership boundary in this
work package. Layer 1 is the only newly executable model flow.

## Evidence boundary

`ResearchInputBundle` is a strict typed boundary around:

- the existing SourceManifest;
- existing Universe, Eligibility and Decision Price snapshots;
- decision-time market, theme, ETF and symbol observations;
- theme membership and daily-bar evidence;
- existing immutable B0/B1 PredictionRuns;
- input Artifact identities and hashes.

Every observation has an Availability Time, and bundle construction rejects
values available after Decision Time. The boundary exposes no `LIVE` fixture
alias: evidence is either `SYNTHETIC_FIXTURE` or
`HISTORICAL_IMMUTABLE_ARCHIVE`.

Internals may use ordinary numerical collections, but no untracked DataFrame
crosses this boundary.

## Research contracts

### Market Regime

`MarketRegimeSnapshot` is a research gate, not a trading signal. V0 adapts the
four observable MR2A metrics and an optional limit-structure proxy into
direction, breadth, liquidity, volatility and risk-appetite scores. Missing
coverage produces `DATA_INSUFFICIENT`, `PROHIBIT` and zero maximum gross
exposure; no default `RISK_ON` exists.

### Theme Rotation

`ThemeRotationSnapshot` ranks configured themes by deterministic, versioned
relative-strength, amount, breadth, leader, participation and persistence
proxies. It emits theme priority, never stock action.

### Capital Evolution

`CapitalEvolutionSnapshot` contains theme-level and symbol-level inferred
states. V0 is explicitly a scoring, gate and state-machine model over observable
proxies. It does not claim hidden institutional or individual actor intent.

### Candidate Discovery

`CandidateSet` reconciles every Universe member to `SELECTED`, `WATCHLIST`,
`REJECTED` or `DATA_INSUFFICIENT`. It requires Market, Theme and Capital gates
plus eligibility, liquidity, history and known status. The legacy B0 and B1
outputs enter only through `LegacyCandidateDiscoveryAdapter` as frozen
percentile factors; they remain immutable PredictionRuns and are never
described as probabilities.

## Gate semantics

- `TradePermission.PROHIBIT` preserves Theme and Capital research but rejects
  the complete Candidate population with
  `MARKET_REGIME_PROHIBITS_RISK`.
- insufficient Theme evidence blocks Candidate selection; there is no
  market-wide stock fallback.
- insufficient Capital Evolution evidence cannot be bypassed by B0/B1.
- falling below the Research Pipeline minimum emits
  `CANDIDATE_POPULATION_INSUFFICIENT`; this is distinct from the Phase D
  source DataQuality status.
- every input symbol remains present with explicit reasons.

## Artifact and replay

`ArtifactEnvelope` provides a strict common V1 envelope for new Platform V2
Artifacts. `ResearchLayerArtifact` is a separate exact-file-set package with
atomic non-overwrite publication, SHA-256 checksums, a semantic Reader,
versioned Reader registry and deterministic recomputation.

The Application entry point is `PlatformResearchRunner`; the CLI is
`scripts/run_research_layer.py`. Replaying verifies the package before
recomputing all four layers with the frozen configuration and code revision.
An equality mismatch is a hard failure.

## Compatibility boundary

The following remain independent:

- the historical `daily_research` V1 six-file Artifact, IDs, Reader and
  `ENTER` semantics;
- Phase D Daily Decision Artifact and Reader registry;
- DailyLoop acquisition, Runtime Journal and settlement;
- B0/B1 definitions, weights, ranks and PredictionRun identities.

Platform V2 does not rename any of them or route old schemas through the new
Research Layer Reader.

## Authority ceiling

Every new Artifact records:

```text
data_eligibility = EXPLORATORY
formal_pit = FORMAL_PIT_NOT_ESTABLISHED
formal_oos_alpha = FORMAL_OOS_ALPHA_NOT_ESTABLISHED
trading_authority = TRADING_AUTHORITY_NOT_GRANTED
```

Successful replay cannot raise that ceiling.
