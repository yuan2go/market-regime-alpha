# ADR-015: Hard Cutover and Schema Epoch

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Implementation State:** DESIGN_CHECKPOINT_ONLY
> **Authority:** Approved-principle target decision for WP-ARCHITECTURE-REFOUNDATION-01
> **Owner:** Market Regime Alpha maintainers
> **Decision Date:** 2026-08-27
> **Starting Main:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Code Evidence:** `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests/persistence/postgres`

## Context

The current PostgreSQL authority schema has 106 incremental migrations and 283
tables. Code audit found repeated lifecycle journals, state/current/transition
families, campaign-specific research tables, compatibility identities, and
multiple writer paths. Historical business data does not need migration or
retention for this work package. Preserving the old schema would force target
Domain boundaries to inherit accidental abstractions and dual Authority.

An automatic “upgrade” is unsafe: an old database may contain operator-relevant
state even when migration is not required. Startup must never infer permission
to drop or rewrite it.

## Decision

Adopt a hard cutover to one new PostgreSQL schema epoch:

```text
schema       = mra
epoch        = MRA_REFOUNDATION_1
baseline     = 001_baseline.sql
legacy data  = not migrated
compatibility writers/readers = none after cutover
```

The target baseline is created from the frozen logical catalog in
[PostgreSQL, Temporal and Evidence Architecture](../Data-and-Evidence-Architecture.md).
The approximate 41-table estimate is not a constraint; the design checkpoint
retains 91 tables because each protects a declared semantic/transactional
boundary.

## Ordinary startup and bootstrap

Before constructing any writer, startup inspects the catalog:

- absent `mra` schema and no recognized legacy MRA catalog: bootstrap may create
  the baseline;
- exact epoch/baseline/seed checksums: verify only, then continue;
- `mra` objects without epoch, mismatched epoch/checksum, or recognized legacy
  tables: fail with a typed error;
- unexpected objects in the application schema: fail and report them.

Ordinary startup, migrate, inspect, and runtime commands execute no `DROP`,
`TRUNCATE`, implicit rename, legacy import, or destructive repair. A failed or
interrupted baseline leaves no committed partial schema because its transactional
DDL and epoch insert are atomic.

## Destructive recreate

Destruction is a separate offline operator command with plan/apply phases. The
plan records:

- exact server/database name and OID;
- database owner and application schema;
- detected epoch or approved legacy catalog fingerprint;
- full object/catalog hash;
- active connections and unexpected objects;
- backup/retention attestation;
- a short-lived confirmation challenge bound to the plan hash.

Apply requires the same operator identity, exact plan hash/challenge, unchanged
catalog/database OID, maintenance role, and no unexpected connection/object.
It refuses `postgres`, template databases, unresolved variables, wildcard
targets, or a catalog different from the plan.

The preferred legacy cutover is to provision and bootstrap a new empty
application database, switch the explicit DSN after qualification, and retain
the old database until separately approved disposal. If an application-owned
database is recreated in place, the offline command operates through a
maintenance connection and reports exactly what was removed. It is never called
by Runtime or tests against an unverified target.

## Future migrations

Once `001_baseline.sql` is released:

- its bytes/checksum and seed checksum are immutable;
- all changes use forward-only `002+` migrations;
- each migration has an exact checksum and transactional/non-transactional
  declaration;
- non-transactional operations have an explicit resumable state;
- no downgrade, legacy compatibility schema, dual read, or v1/v2/v3 table family
  is introduced;
- destructive semantic changes require a new ADR and, when incompatible, a new
  schema epoch;
- rollback restores backup or switches database; it never rewrites migration
  history.

## Seed boundary

Seed initializes only the epoch and stable system reference vocabulary needed to
validate closed schemas/Runtime step kinds. Provider qualification, instrument
master, Market facts, accounts, research evidence, Model/Strategy qualification,
and Production admission are never seeded as positive facts.

## Verification obligations

The implementation checkpoint must prove:

1. clean PostgreSQL → baseline → seed → verify;
2. bootstrap retry is idempotent;
3. mismatch/legacy/unexpected objects fail before DDL;
4. baseline and seed checksum drift fail;
5. interrupted baseline leaves no partial catalog;
6. explicit recreate plan becomes invalid after catalog drift;
7. normal Runtime cannot invoke destructive code;
8. canonical Runtime reaches Market mutation, Decision query, Outcome, and
   Evidence on an empty database;
9. all retained tables have declared PK/FK/check/index/retention ownership;
10. old migrations, repositories, compatibility paths, and tests with no retained
    invariant are physically absent.

## Consequences

Benefits:

- target Domain and Authority boundaries are not distorted by data migration;
- one reviewable baseline replaces patch accumulation;
- legacy databases are protected by fail-fast catalog identity;
- future migrations have a clean forward-only contract.

Costs:

- old databases cannot run the new application;
- operators must provision/recreate explicitly;
- all fixtures/integration tests and operational commands must be rebuilt;
- rollback is database-level rather than application-level compatibility.

## Rejected alternatives

- **Incrementally migrate all 283 tables:** retains duplicate Authority and
  compatibility semantics.
- **Dual-write old and new schemas:** creates two truth sources and untestable
  cutover races.
- **Create target tables beside legacy tables and prefer new when present:**
  makes availability-dependent Authority.
- **Drop/recreate automatically at startup:** violates explicit destructive
  authorization and can silently destroy data.
- **Force an approximate table count:** optimizes a proxy over semantics and
  auditability.

## Review status

The Hard Cutover principle is approved. This ADR and its exact 91-table target
remain a design checkpoint for the next review. No schema or business code is
changed by this commit.
