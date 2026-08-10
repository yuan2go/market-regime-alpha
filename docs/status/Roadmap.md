# Roadmap

> **Status:** ROADMAP
> **Authority:** Current forward engineering order
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `docs/status/Current-State.md`, `docs/status/Gap-Register.md`

## P0 Architecture and Authority correctness

1. Preserve the single Continuous Runtime and PostgreSQL-only composition.
2. Keep migration 046 fail-closed while designing owner-specific Historical Sample and Formal OOS writers.
3. Inventory internal executable modules and either expose an intentional operator command or remove dead entry paths.
4. Continue Legacy consumer measurement; delete only after Reader/replay/migration demand reaches zero.

P0 must not add model parameters, Alpha claims or trading permissions.

## P1 Remaining engineering completion

1. Run exact-window free-data Research/Shadow operations and recovery drills.
2. Accumulate real prospective outcome/attestation evidence under trusted clock/origin rules.
3. Complete authentication, RBAC, backup/restore and observability foundations.
4. Implement narrow qualification writers only when their owner evidence exists.

## P2 Free-data operational research

Use recorded public data to test operational reliability, coverage, missingness, turnover and data-quality hypotheses. Keep `EXPLORATORY`/`PIT_INCOMPLETE`; do not use P2 to infer Formal PIT or production readiness.

## P3 Empirical validation

After qualified inputs and frozen protocols exist, run purged/embargoed comparisons, ablation, calibration and locked OOS evaluation. Preserve negative and inconclusive results. No automatic promotion follows.

## P4 Qualification

Owner-resolved PIT, OOS, economic, capacity, calibration, Entry, Holding/Exit and sustained Shadow evidence may enter Model Governance. Operator/RBAC floors remain independent.

## P5 Controlled production

Only a separately approved program may introduce authenticated Production Admission and later broker work. It requires explicit security, reconciliation, kill-switch and operational evidence. This roadmap grants none of that authority.
