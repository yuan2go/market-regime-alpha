# Data and Evidence Architecture

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical data, time and evidence rules
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-20
> **Code Evidence:** `src/market_regime_alpha/data`, `src/market_regime_alpha/market_data`, `src/market_regime_alpha/evidence`, `src/market_regime_alpha/data/postgres_pit_authority.py`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`

## Evidence is not a reference

`ArtifactId + SHA-256` proves stable content identity. It does not prove who owns the object, when it was available, whether it was qualified, or whether its lineage is semantically compatible.

An Authority consumer must reload from the owning PostgreSQL Repository and verify:

1. exact ID and hash;
2. immutable stored payload restoration;
3. declared kind and schema;
4. event, effective, available, recorded and system-imported time;
5. Provider contract and source qualification;
6. model/dataset/feature/protocol lineage;
7. current status, revocation and supersession state;
8. the consumer-specific qualification floor.

Generic evidence resolution is intentionally not a universal framework. Formal PIT owns PIT resolution; Model Governance owns model evidence/decisions; State System owns State receipts; Research and Strategy repositories own their artifacts.

## Time semantics

- `event_time`: when the observed event occurred.
- `effective_from/to`: when a fact applies.
- `available_at`: earliest legitimate decision-time availability.
- `recorded_at`: when the owner accepted the fact.
- `system_imported_at`: PostgreSQL system-time evidence.
- `DecisionTime` and `AsOfTime`: consumer cutoffs, never aliases for wall-clock ingestion.

No stage may infer PIT from a filename, current API response, caller timestamp or replay timestamp. Late, missing, conflicting or non-final evidence fails closed.

## Data eligibility and Provider ceiling

`UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL` and `FORMAL_RESEARCH` are distinct. BaoStock, Tencent, AKShare and other available public sources may be combined by Provider × Contract × Fact Kind for Research/Shadow operation and cross-checking. They remain Provider-specific evidence behind canonical facts, never downstream dependencies or a second Authority. Paid terminals are optional future Formal Provider candidates, not Phase D dependencies. No current real bundle establishes Formal qualification.

A downstream artifact may retain or lower the minimum input eligibility. It may never raise it. A valid Summary or receipt ID does not upgrade data authority.

## PostgreSQL-only persistence

- Packaged migrations are contiguous from 001 through 092 and checksummed.
- `schema_migrations` and the schema catalog are verified at startup/tests.
- Runtime database bindings exclude credentials and fail closed on a different database/schema.
- Journals use leases, fencing, CAS and append-only events.
- Immutable evidence tables reject update/delete.
- Migration 046 makes Research Validation incapable of persisting qualification, Production authorization or non-owner-resolved Formal OOS states.

The schema catalog currently contains 270 tables. That count includes immutable
owners, workflow journals, read models and projections; table count alone is not
an Authority count. Migrations 047–067 establish the fail-closed Phase C/Phase D
owners and exact Strategy/Portfolio lineage. Migrations 068–084 establish the
Historical Corpus, selective-read, effective-dated reference and longitudinal
feature-configuration owners. Migration 085 adds the minimal Strategy business
facts needed for the shared Overnight/Swing runtime, cross-strategy Portfolio,
observed-Fill allocation, Path Outcomes and feedback. Migration 086 adds one
immutable, fill-derived realized Strategy Outcome table under the existing
Strategy Shadow owner. Strategy sleeve state remains a deterministic projection
of Fill allocations, the exact PIT Trading Calendar and account observations,
not a second Position table. Migration 087 extends the existing ManualTrade and
realized Outcome owners with exact Strategy execution authorization and
append-only Outcome supersession. Migration 088 adds owner-resolved account
reconciliation and canonical Market Bar/Dataset projections, the Proposal
quantity ceiling and active-account indexes to `manual_trade_records`. The full
Canonical Market Data Dataset owner (artifact, adjustment policy and partitions)
and selected Market Bar are frozen in the append-only Strategy cycle. Sizing
reconstructs the Dataset, verifies its ID/hash and exact Bar membership, then
checks the projected price/times; the projection cannot substitute price.
Reservations and post-observation Fill/correction deltas are reconstructed from
the existing ManualTrade and Fill facts under PostgreSQL transaction locks, so
088 adds no table or Authority. The migrations extend the existing
Continuous child constraint with `STRATEGY_RUNTIME`; it creates neither another
scheduler nor another Position owner. None weakens migration 046 or creates a
second Calendar/PIT/Forecast/Evaluation owner. Migration 089 admits immutable
Golden Loop V2 `RESEARCH_EVALUATION` session components and
`METHODOLOGY_ASSESSMENT` evidence under the existing Historical Research
owners. Migration 090 removes the invalid uniqueness assumption that a
tie-aware Dynamic Pool can have only one member at a rank. Neither migration
creates another Runtime, Portfolio owner, Outcome owner, or physical Position
path.

Migration 091 admits the five Alpha Research Phase II kinds into the existing
append-only Historical Evidence owner and admits Strategy Contract V2 plus the
`CONDITIONAL_PREDICTION` family into the existing Strategy Registry. Contract
V2 freezes `FORECAST_REQUIRED` versus `FORECAST_NOT_REQUIRED`; required
Strategies fail closed unless their Runtime input binds symbol-level Signal,
Forecast, Context, Risk state and Model/version lineage. No new table,
Evidence authority, Runtime or qualification owner is introduced.

Migration 092 adds the database-level semantic constraint omitted by 091:
existing Overnight/Swing V1 payloads remain unchanged and contain no Forecast
field; V2 Conditional Prediction must declare `FORECAST_REQUIRED`, and every
other V2 family must declare `FORECAST_NOT_REQUIRED`. This prevents an existing
PostgreSQL Registry from gaining duplicate active versions through an incumbent
identity rewrite.

Strategy evidence is keyed by exact Strategy Version and retains Dataset, PIT,
Universe, Decision Time, Target/Horizon, cost, evaluation, code and configuration
references. A run-level inspection additionally follows Outcome/feedback source
lineage so another cycle of the same Strategy Version cannot appear in the
inspected cycle. Identity and lineage prevent contamination; they do not prove
the underlying research claim.

## Replay

Replay reads the original owner rows and frozen inputs. It may re-run pure computation, but may not call a replacement Provider, manufacture absent evidence or rewrite historical identity. Recovery resumes the same run/tick under lease/fence rules. Corrections append a new version or explicit supersession.

## Evidence ceiling

```text
FORMAL_PIT_ESTABLISHED = false
FORMAL_OOS_ALPHA_ESTABLISHED = false
CALIBRATED_PROBABILITY_ESTABLISHED = false
SUSTAINED_STRATEGY_SHADOW_PROVEN = false
PRODUCTION_AUTHORIZED = false
BROKER_INTEGRATION_PROVEN = false
```
