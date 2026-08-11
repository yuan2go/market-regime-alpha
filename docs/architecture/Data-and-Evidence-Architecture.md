# Data and Evidence Architecture

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical data, time and evidence rules
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
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

`UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL` and `FORMAL_RESEARCH` are distinct. Tencent and BaoStock currently support recorded exploratory operation only. Xuntou/ThinkTrader/XtQuant remains the formal Provider direction, but no current real bundle establishes formal qualification.

A downstream artifact may retain or lower the minimum input eligibility. It may never raise it. A valid Summary or receipt ID does not upgrade data authority.

## PostgreSQL-only persistence

- Packaged migrations are contiguous from 001 through 057 and checksummed.
- `schema_migrations` and the schema catalog are verified at startup/tests.
- Runtime database bindings exclude credentials and fail closed on a different database/schema.
- Journals use leases, fencing, CAS and append-only events.
- Immutable evidence tables reject update/delete.
- Migration 046 makes Research Validation incapable of persisting qualification, Production authorization or non-owner-resolved Formal OOS states.

The schema catalog currently contains 201 tables. That count includes immutable authorities, workflow journals, read models and projections; table count alone is not an Authority count. Migrations 047–055 add exploratory sample, Research Universe, Portfolio Shadow, engineering access-governance owners, Path Calibration Hypothesis evidence and fail-closed Phase C gates. Migration 056 adds a Calendar payload snapshot anchored to the existing PIT Artifact Authority and Formal Protocol owner-resolution receipts. Migration 057 adds owner-computed Forecast receipts, frozen multi-target families, one-time raw OOS unlock, Target-specific consumption, family evaluation, per-record PIT/Historical/Forecast bindings and typed operator command audit. New Formal Protocols admit only Train/Validation Historical Dataset records into C3. Their metadata-only owner seam runs before the pre-OOS readiness barrier, and Target Label metadata must match the Forecast DecisionTime before its realized payload can be read. Migration-027 Model Registry action envelopes remain replay-only for pre-057 Protocols. None weakens migration 046 or creates a second Calendar/PIT/Forecast/Evaluation owner.

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
