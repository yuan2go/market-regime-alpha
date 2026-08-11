# Phase C Formal Research Runtime Final Closure Implementation Plan

**Goal:** Close caller-controlled Formal Forecasts, model pre-registered
multi-target OOS correctly, evaluate multiplicity at family scope, and expose a
governed operator workflow without changing evidence floors.

## 1. Baseline and red tests

- Pin baseline SHA, migration 056 and PostgreSQL 16 schema evidence.
- Add domain tests for reference-only forecast requests and frozen family
  identity.
- Add PostgreSQL red tests for caller estimate rejection, backdating, owner
  lineage, replay, raw-path substitutions, family concurrency and migration 046.
- Add CLI red tests for typed inputs, idempotency and RBAC denial.

## 2. Migration 057 authority schema

- Add append-only Formal Forecast computation request/receipt/input tables and
  explicit legacy/formal authority classification.
- Add frozen hypothesis family, raw unlock and target-observation consumption
  tables with exact constraints and indexes.
- Add family evaluation result/binding tables and Phase C operator command
  ledger.
- Add no-update/no-delete triggers, schema catalog declarations, contiguous
  migration tests and upgrade tests from migration 056.

## 3. Formal Forecast computation

- Implement typed request, resolved computation context, executor result and
  receipt contracts.
- Implement exact installed-executor selection with a fail-closed unsupported
  executor.
- Implement PostgreSQL owner resolution, PIT temporal/lineage checks, clocked
  materialization, idempotent transaction, read-back and replay.
- Reclassify the old caller writer as exploratory and exclude it from formal
  consumers.

## 4. Frozen family and OOS consumption

- Materialize the family during Formal Protocol freeze and verify it on replay.
- Replace new formal OOS consumption with raw unlock plus target consumption.
- Enforce exact replay, concurrent first-writer behavior and cross-revision
  substitution rejection.

## 5. Family-level evaluation

- Add typed target-grouped input and target-keyed metrics.
- Reuse the current statistic implementations while moving p-value adjustment
  to the complete frozen family.
- Require exact target coverage and family receipts in Formal OOS qualification.
- Preserve legacy single-target results as engineering-only replay.

## 6. Operator workflow

- Add owner-specific freeze/snapshot/replay commands to existing CLIs.
- Use PostgreSQL time, exact command hashes, existing RBAC/audit and read-back.
- Add command help and operations documentation; do not add an executable or
  generic registration command.

## 7. Evidence replay and C0-C9 decision

- Run the clean-schema owner workflow and current Provider assessments.
- Record only real decisions: current C1 rejection, C2-C6 blocked, C7
  accumulating, C8-C9 blocked unless external state has genuinely changed.
- Update Current State, Capability Matrix, Gap Register and Roadmap from runtime
  evidence.

## 8. Full verification and publication

- Run focused tests, PostgreSQL suites, platform tests and full pytest.
- Run Ruff, mypy, build, docs links, migration/schema, replay/recovery and
  `git diff --check`.
- Perform two-axis standards/spec review and fix blockers.
- Commit the final tree, rerun Exact-SHA verification, push and open a Draft PR.
- Report CI as `CI_NOT_RUN` unless GitHub Actions actually runs.
