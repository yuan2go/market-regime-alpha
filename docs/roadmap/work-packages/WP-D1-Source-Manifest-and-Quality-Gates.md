# WP-D1 — Daily Source Manifest and Data Quality Gates

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D1  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Freeze exact daily source inputs, semantic times and field-level quality so every downstream artifact is reproducible and fail-closed.

## Bounded contexts

- Data Source and PIT

## Dependencies

- WP-D0 for artifact identity
- existing provider/data/time contracts

## Inputs

- Tencent/Xuntou/BaoStock/Tushare/AKShare adapters as explicitly scoped
- provider field mappings
- semantic-time policy

## Outputs

- SourceManifest
- DataQualityReport
- raw immutable archive
- freshness and authority gates

## Expected files/modules

- src/market_regime_alpha/data/**
- src/market_regime_alpha/research/provider_*
- tests/data/**
- scripts/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- SourceManifest
- SourceFieldRecord
- DataQualityReport
- ProviderContract

## Code work

- canonical ingest command
- raw payload hashing
- field availability/finality records
- fail-closed quality evaluation
- replay reader

## Tests

- same payload produces same manifest hash
- stale/unknown field blocks required stage
- silent provider substitution rejected
- replay reconstructs exact normalized input

## Acceptance conditions

- all daily inputs have event/available/ingestion/decision times
- manifest is immutable
- downstream evidence ceiling is computable
- blocked reasons are machine-readable

## Evidence required

- replay artifact
- tamper test
- field semantics table
- quality-gate test report

## Risks

- provider schema drift
- incorrect availability assumptions
- overly permissive fallback

## Stop conditions

- required provider semantics cannot be established
- raw payload cannot be preserved
- quality gate needs guessed timing

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Replaces ad-hoc provider calls as the source authority; existing adapters remain transport implementations.

## Documentation updates

- docs/architecture/04-Data-and-Time-Semantics.md
- docs/status/External-Blockers.md
- docs/status/Capability-Matrix.md

## Explicit non-goals

- broad provider coverage
- model changes
- formal evidence promotion
