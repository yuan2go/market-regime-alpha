# Data Source and PIT Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Data Source and PIT  
> **Owner:** Data Source and PIT domain  
> **Last Updated:** 2026-08-08
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/data/**; path:src/market_regime_alpha/research/xuntou_*; path:Tencent/BaoStock exploratory adapters

## Responsibility

Own provider identity, raw payload preservation, field semantics, availability/finality, source manifests and evidence ceilings.

## Owned entities

- `ProviderReference`
- `RawSourceArtifact`
- `SourceManifest`
- `DatasetContract`
- `DataQualityReport`
- `PITSourceQualification`
- `PITFactRevision`
- `PITAsOfSnapshot`
- `FormalPITEvidenceArtifact`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RegisterProviderContract`
- `AcquireSourceArtifact`
- `NormalizeSourceArtifact`
- `FreezeSourceManifest`
- `AssessDataQuality`
- `QualifyOrSuspendPITSource`
- `RecordPITFactRevision`
- `ValidateFormalPIT`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetProviderContract`
- `GetSourceManifest`
- `GetArtifactLineage`
- `GetFreshnessStatus`
- `GetPITAsOfSnapshot`
- `ReplayFormalPITEvidence`

Queries are read-only projections and return canonical source IDs.

## Events

- `SourceArtifactAcquired`
- `SourceManifestFrozen`
- `DataQualityAssessed`
- `SourceBlocked`
- `PITSourceAuthorityChanged`
- `PITFactRecorded`
- `FormalPITValidated`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- provider credentials/runtime outside stored artifacts
- raw provider payloads
- semantic-time policy
- field mapping specification

## Output contracts

- SourceManifest
- DataQualityReport
- qualified or blocked normalized artifacts

## Upstream domains

- external providers
- trading calendar

## Downstream domains

- Calendar and Universe
- Market/ETF/Theme/Capital Context
- Feature and Factor

## Invariants

- Raw payloads are immutable and hash-addressed.
- No silent provider substitution.
- Derived evidence never exceeds the weakest required input.
- event_time, available_time, ingestion_time and decision_time remain distinct.
- `FORMAL_RESEARCH` fact admission requires exact active SourceManifest,
  Provider and contract qualification; caller declarations never suffice.
- Historical reconstruction is pinned to the original PostgreSQL authority
  revision and never substitutes current rows.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | provider unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | schema drift | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | stale data | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | unknown adjustment/finality | Fail closed; emit domain error/event and preserve input evidence. |
| `5` | field authority insufficient | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/data/**`
- `src/market_regime_alpha/research/xuntou_*`
- `src/market_regime_alpha/data/pit_authority.py`
- `src/market_regime_alpha/data/postgres_pit_authority.py`
- PostgreSQL migration 028
- `Tencent/BaoStock exploratory adapters`

## Missing implementation

- canonical daily SourceManifest service
- cross-provider semantic conformance suite
- daily freshness SLA registry
- qualified real Provider archive ingestion into the formal PIT ledger

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
