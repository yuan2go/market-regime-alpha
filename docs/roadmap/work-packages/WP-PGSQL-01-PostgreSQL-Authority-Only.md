# WP-PGSQL-01 — PostgreSQL Authority Only

> **Status:** ROADMAP
> **Authority ceiling:** database/runtime mechanics only

## Objective

Remove the executable file-database backend and make native PostgreSQL 16 the
only persistence, Journal, migration, replay and repository-integration
database.

## Delivered scope

- PostgreSQL-only `DatabaseSettings` and `RepositoryFactory`;
- native bounded PostgreSQL repositories without SQL translation or DB-API
  bridge;
- centralized migrations 001–026 and migration 024 PostgreSQL-only binding;
- randomly isolated PostgreSQL schemas for repository, runtime, CLI and replay
  tests;
- explicit unavailable-database failure;
- removal of file-database repositories, schemas, migrations, factories,
  adapters, importer, configuration, CLI paths and backend tests;
- preservation of immutable historical Artifact Readers and the fixed 14:55
  Target identity.

The published PostgreSQL migration 017 remains immutable for checksum-safe
upgrade. Migration 024 removes its historical backend alternative from the
current catalog constraint.

Migration 025 is likewise checksum-preserved. Migration 026 applies the receipt
lease/schema constraints forward while preserving prerelease v1 Decision rows;
new v2 writes require the Lease-bound canonical schema and configuration FKs.
Empty 001→026 and 023→026 upgrades are supported release paths.

## Acceptance boundary

Local PostgreSQL integration, concurrency and replay tests establish engineering
behavior only. They do not establish production operations, PIT correctness,
OOS Alpha, Shadow readiness or trading authority.
