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
- centralized migrations 001–025 and migration 024 PostgreSQL-only binding;
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

## Acceptance boundary

Local PostgreSQL integration, concurrency and replay tests establish engineering
behavior only. They do not establish production operations, PIT correctness,
OOS Alpha, Shadow readiness or trading authority.
