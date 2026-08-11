# Roadmap

> **Status:** ROADMAP
> **Authority:** Current forward engineering order
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-12
> **Code Evidence:** `docs/status/Current-State.md`, `docs/status/Gap-Register.md`

## Phase C current order

1. **C0 engineering complete:** freeze Target, Calendar and evaluation partitions;
   reload every result-affecting component from its PostgreSQL owner; durably
   compute Forecasts from owner-resolved PIT/Model inputs; freeze a multi-target
   Hypothesis Family; unlock each raw OOS path once and correct all registered
   Target/metric/slice/sensitivity/fold hypotheses as one family.
2. **C1 engineering complete, evidence rejected:** collect independent
   Provider archive/version/revision/availability evidence by Contract and Fact
   Kind. Current BaoStock/Tencent assessments do not satisfy the floor.
3. **C2–C6 engineering ready, evidence blocked:** do not create Formal PIT,
   Historical qualification, Locked OOS, Calibration or strategy qualification
   until the immediately preceding owner has satisfied evidence.
4. **C7 engineering ready, evidence accumulating:** operate the one Continuous
   Runtime prospectively under a pre-frozen policy; Replay/Fixture/history never
   count as sessions.
5. **C8–C9 engineering fail-closed:** keep Production Admission and Controlled
   Execution blocked until all Formal, authentication, approval and external
   Broker floors independently exist.

Phase C must not add model parameters, Alpha claims or trading permissions to
make a gate pass.

## Phase D engineering complete, evidence bounded

[ADR-008](../architecture/decisions/ADR-008-Phase-D-Research-Execution.md)
records the implemented Shared Decision Session Kernel, PostgreSQL Historical
Journal and Free-Data-First boundary. Migrations 058–064 and the existing
`continuous-research` surface now provide Full-A Runtime Scope, owner-resolved
Shadow Observations, multi-period Performance/Attribution, deterministic
exploratory Model training/inference and ordered fail-closed Formal assessment.
This is executable engineering, not Provider, PIT, OOS Alpha, calibration or
Production evidence.

The next Phase D work is operational evidence, not another framework:

1. freeze representative real multi-year free-data corpora and record
   coverage/missingness without inventing availability;
2. exercise interruption/resume/replay across long ranges and daily Shadow;
3. compare research challengers and preserve negative/inconclusive results;
4. keep Formal execution blocked until independently qualified Provider Fact
   and Formal PIT owners exist.

## P1 Operational evidence completion

1. Run exact-window free-data Research/Shadow operations and recovery drills.
2. Accumulate real prospective outcome/attestation evidence under trusted clock/origin rules.
3. Bind external authentication and execute repeated backup/restore, recovery-audit and observability drills; the RBAC/Approval owners already exist.
4. Resolve the existing narrow qualification writers only when their owner evidence exists.

## P2 Free-data operational research

Use recorded public data to test operational reliability, coverage, missingness, turnover and data-quality hypotheses. Keep `EXPLORATORY`/`PIT_INCOMPLETE`; do not use P2 to infer Formal PIT or production readiness.

## P3 Empirical validation

After qualified inputs and frozen protocols exist, run purged/embargoed comparisons, ablation, calibration and locked OOS evaluation. Preserve negative and inconclusive results. No automatic promotion follows.

## P4 Qualification

Owner-resolved PIT, OOS, economic, capacity, calibration, Entry, Holding/Exit and sustained Shadow evidence may enter Model Governance. Operator/RBAC floors remain independent.

## P5 Controlled production

Only a separately approved program may introduce authenticated Production Admission and later broker work. It requires explicit security, reconciliation, kill-switch and operational evidence. This roadmap grants none of that authority.
