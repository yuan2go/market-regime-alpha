# ADR-005: Feature Materialization Precedes Lifecycle V1

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Accepted architecture decision for Canonical Feature scheduling
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../12-Canonical-Runtime-and-Legacy-Migration.md, ../13-Canonical-Market-Data-and-Feature-Spine.md
> **Code Evidence:** `FeatureMaterializationRunner`; `CanonicalLifecycleInputManifest`; unchanged `LIFECYCLE_STAGE_ORDER`

## Decision

Canonical Market Data and Feature materialization run before the existing
16-stage Canonical Decision Lifecycle. The resulting Dataset and FeatureBundle
are immutable, verified input references consumed by `SignalStageHandler`.

The V1 lifecycle enum, migration 011 and historical Reader/replay semantics are
not changed.

## Rationale

- Feature production is input preparation, not a trading-decision transition.
- Independent publication permits content-addressed reuse across lifecycle runs.
- Crash/retry behavior remains local to the Feature Run.
- Historical V1 Journal stage order and receipts stay readable.
- H8 can later schedule Evidence, Feature and Lifecycle Runs without embedding a
  scheduler into domain stages.

## Rejected alternatives

Inserting a stage into the V1 enum would silently change persisted stage order
and migration-011 semantics. Computing Features inside Signal would mix raw-data
authority, computation and model assembly and would prevent independent replay.

## Consequences

Lifecycle input manifests must bind Dataset, FeatureBundle, Feature Set, Feature
models and Signal mapping with IDs, hashes, Readers, locators and evidence
availability. A future graph change requires an explicit V2 graph, migration and
cross-version Reader/replay tests.

This decision grants no Entry, execution or Broker authority.
