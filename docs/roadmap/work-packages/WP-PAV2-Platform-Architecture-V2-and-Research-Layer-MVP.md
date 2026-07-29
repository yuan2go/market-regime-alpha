# WP-PAV2 — Platform Architecture V2 and Research Layer MVP

> **Status:** CURRENT_STATUS
> **Authority:** Implemented and verified work-package boundary for Platform V2
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** README.md, ../../architecture/09-Platform-Architecture-V2.md, ../../architecture/decisions/ADR-003-Platform-V2-Research-Artifact-Boundary.md, ../../audit/WP-PAV2-Platform-Architecture-V2-Delivery.md
> **Code Evidence:** `feat/platform-architecture-v2-research-layer@45fdaa9`

## Objective

Define the six platform ownership layers and deliver a runnable, replayable
Research Layer MVP:

```text
Market Regime → Theme Rotation → Capital Evolution → Candidate Discovery
```

## Bounded contexts

- Data and Evidence Foundation;
- Research and Opportunity Discovery;
- Signal and Timing contracts;
- Trade Decision and Risk contracts;
- Position Lifecycle and Execution contracts;
- Outcome Evaluation and Learning contracts.

Only Research and Opportunity Discovery receives executable model behavior.

## Dependencies and inputs

Dependencies:

- SourceManifest V2;
- PIT Universe and Eligibility snapshots;
- Decision Price snapshot;
- Feature definitions;
- immutable B0/B1 PredictionRuns;
- content-addressed Artifact conventions.

Inputs are carried by `ResearchInputBundle`. It accepts a synthetic fixture or
historical immutable archive, never unlabelled live-like data.

## Outputs

- Platform V2 Artifact Envelope;
- MarketRegimeSnapshot;
- ThemeRotationSnapshot;
- CapitalEvolutionSnapshot;
- CandidateSet;
- Signal/Forecast/Decision/Position/Execution/Evaluation boundary contracts;
- ResearchLayerArtifact, Reader, Reader Registry and semantic Replay;
- PlatformResearchRunner and offline CLI.

## Affected modules

```text
src/market_regime_alpha/evidence/
src/market_regime_alpha/research/market_regime/
src/market_regime_alpha/research/theme_rotation/
src/market_regime_alpha/research/capital_evolution/
src/market_regime_alpha/research/candidate_discovery/
src/market_regime_alpha/research/platform_v2/
src/market_regime_alpha/application/research_layer/
src/market_regime_alpha/{signals,forecasting,decision,portfolio,execution,position,evaluation}/
scripts/run_research_layer.py
```

Existing daily runtime and historical compatibility packages are not moved.

## Contracts and configuration

All new Artifact contracts use strict canonical serialization and explicit
lineage. Model configurations are content-addressed and versioned:

- MarketRegimeModelConfig;
- ThemeRotationModelConfig;
- CapitalEvolutionModelConfig;
- CandidateDiscoveryModelConfig;
- ResearchPipelineConfig.

Every configuration declares `MODEL_ASSUMPTION` and
`NOT_EMPIRICALLY_VALIDATED`.

## Tests and acceptance evidence

Automated evidence covers:

- deterministic and strict Envelope/config identities;
- every required Market, Theme and Capital state;
- Candidate gates, full reconciliation, tie break and Top-N;
- future Availability Time rejection;
- exact-file-set publication, checksum and semantic tamper rejection;
- Reader routing and deterministic replay;
- CLI run/replay/report;
- legacy DailyLoop, B0/B1 and Reader compatibility.

At delivery, all 1,170 repository tests pass; mypy, Ruff, pip check and
`git diff --check` pass.

## Risks and stop conditions

Risks:

- initial weights may be mistaken for empirical Alpha;
- incomplete Theme membership can collapse Candidate coverage;
- observable capital proxies may be narrated as hidden actor intent;
- a future orchestrator may accidentally conflate Research gates with trade
  authority.

Stop instead of producing Candidates when:

- Market permission is `PROHIBIT`;
- all Theme evidence is insufficient;
- all Capital evidence is insufficient;
- qualified Candidate population is below the configured minimum;
- input lineage, time or Artifact verification fails.

## Migration effect

MR2A and B0/B1 are integrated by Adapter without changing their historical
contracts. Old daily artifacts and Readers remain independently routed.

## Documentation updates

- Platform Architecture V2;
- ADR-003;
- delivery audit;
- Current State, Capability Matrix and Gap Register.

## Explicit non-goals

- LIVE Research Provider integration;
- Signal model or forecast model;
- real Entry, Position, Exit, Portfolio or execution logic;
- real 14:55 or T+1 10:30 validation;
- 100–300 symbol acquisition;
- model tuning, OOS claims or trading authority.
