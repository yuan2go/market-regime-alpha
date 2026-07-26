# WP-D2E — Tencent Exploratory Daily Vertical Slice

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D2E  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Run an early end-to-end daily engineering loop with Tencent/public sources under a hard EXPLORATORY evidence ceiling, using canonical contracts rather than a parallel temporary model.

## Bounded contexts

- Data Source and PIT
- Calendar and Universe
- Candidate Discovery
- Review and Attribution

## Dependencies

- WP-D0
- WP-D1
- WP-D2
- existing B0/B1 and target materializers

## Inputs

- Tencent current snapshot/minute data
- BaoStock/local historical bars where declared
- public metadata mappings
- fixed liquid A-share universe
- fixed decision time and target

## Outputs

- DailyResearchSnapshot profile
- B0/B1 PredictionRuns
- CandidateRecommendations
- next-session RecommendationOutcomes
- minimal DailyReviewReport
- raw/source archive

## Expected files/modules

- src/market_regime_alpha/application/daily_loop/**
- src/market_regime_alpha/data/providers/tencent/**
- src/market_regime_alpha/candidates/**
- src/market_regime_alpha/review/**
- scripts/run_exploratory_daily_loop.py
- tests/application/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- DailyResearchSnapshot
- PredictionRun
- CandidateRecommendation
- RecommendationOutcome
- DailyReviewReport

## Code work

- 14:50 source freeze
- existing B0/B1 adapter execution
- append-only prediction ledger
- next-session outcome matcher
- daily replay command

## Tests

- fixture replay
- 10-session synthetic/recorded sequence
- snapshot immutability
- restart idempotency
- EXPLORATORY ceiling cannot be promoted
- missing source produces DATA_BLOCKED

## Acceptance conditions

- one command replays a full day
- predictions freeze before outcomes
- next-session outcomes attach without mutation
- 10 consecutive available market sessions run or are explicitly blocked
- no silent source fallback

## Evidence required

- daily run manifests
- replay hashes
- outcome ledger
- blocked-day report
- operator runbook

## Risks

- public endpoint instability
- false confidence from runnable loop
- parallel contract creation
- manual mapping drift

## Stop conditions

- Tencent semantics change without mapping update
- canonical contracts would need bypassing
- outcomes cannot be matched reproducibly
- engineering scope begins tuning model weights

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Implements a thin vertical subset of later D3–D8 on the same contracts. Later packages enrich or replace providers, not identities. Artifacts remain EXPLORATORY.

## Documentation updates

- docs/research/Current-Research-Program.md
- docs/status/Current-State.md
- docs/status/External-Blockers.md
- docs/roadmap/work-packages/README.md

## Explicit non-goals

- formal PIT claim
- model promotion
- weight tuning
- real trade authority
- profitability claim
