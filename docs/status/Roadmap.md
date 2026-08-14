# Roadmap

> **Status:** ROADMAP
> **Authority:** Current forward engineering order
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `docs/status/Current-State.md`, `docs/status/Gap-Register.md`

## Multi-Strategy convergence

The migration-085–087 engineering slices are complete: stable Strategy
Contract/Version/Run identities, shared Overnight/Swing execution, explicit
Candidate gate attribution, simple cross-strategy Portfolio/Risk, observed-Fill
strategy sleeves, multi-horizon Path Outcomes, version-scoped feedback,
Continuous/Historical/Replay wiring and runtime inspection all use the existing
PostgreSQL modular monolith and control planes.

Accepted Portfolio lines now create Strategy-authorized intents in the existing
manual ledger. A single action may accumulate multiple observed partial Fills;
corrections reproject allocation, physical Position and Strategy sleeve, and a
corrected realized Outcome supersedes rather than overwrites its predecessor.
Executable quantity is lot/T+1/budget aware, holding age uses the canonical PIT
Calendar, and stale prices fail closed. The existing `decision-system` CLI is
the operator surface for intent, Fill and recovery; there is no execution
scheduler or broker path.

Account-bound Continuous execution now restores owner-resolved Strategy sleeve
state across sessions, settles fully closed observed-Fill lifecycles, and freezes
the exact state in replay input. The retained T+1 Shadow Entry consumes the
canonical Overnight Proposal when available. This closes the stateful Runtime
seam; it does not establish empirical strategy value.

The next dependency order is empirical rather than another governance build:

1. automatically materialize exact 3/5/10/20-session Path Outcomes over the
   frozen longitudinal corpus;
2. freeze and run version-scoped Overnight/Swing gate, ranking, path and
   economic comparisons with purging/embargo and uncertainty;
3. resolve real cost, liquidity, fillability and capacity inputs;
4. acquire qualified Provider/PIT evidence before Formal OOS or calibration;
5. accumulate prospective Shadow evidence before any Production consideration.

Legacy T+1 Shadow artifact shapes and Portfolio Shadow remain only while active
settlement and qualification consumers depend on them. Their Entry decision is
already proposal-gated; further retirement requires consumer-specific replay
proof rather than deleting immutable history.

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

## Phase D Alpha proof foundation implementation order

Phase D is an approved engineering program on top of the Phase C fail-closed
qualification boundary. It does not assert Alpha, Formal PIT, Formal OOS,
calibration, prospective performance or Production qualification.

1. **Statistical validity — engineering complete:** freeze explicit per-hypothesis null, benchmark,
   alternative, inference method and economic threshold. Separate effect,
   sampling interval, hypothesis test and economic assessment. Implement
   date-cluster moving-block confidence intervals, null-centred block tests and
   family-level FWER/FDR semantics. Prove deterministic null size, injected
   signal power, dependency handling and leakage rejection.
2. **Experiment and target semantics — engineering complete:** extend the existing Formal Protocol with
   one immutable Experiment Definition. Introduce Target Definition V2 with
   explicit decision, entry, observation, evaluation, return, excursion,
   barrier-ordering and market-data policies. Preserve V1 replay, but permit no
   silent V1/V2 conversion.
3. **Forecast computation — engineering complete, Formal evidence blocked:** separate deterministic measure kernels from the
   existing Formal qualification gate. Install owner-resolved benchmark linear,
   raw-logit and regime-conditioned executors. Each measure independently
   reports availability; no uncalibrated score is represented as probability.
4. **Research execution and Alpha decomposition — engineering complete, empirical results pending:** port the useful runtime
   scope, session journal, historical runner, observation and performance
   capabilities from the earlier Phase D inventory onto new migrations based on
   migration 057. Add replayable feature policies, Candidate/Signal ablation,
   ranking benchmarks, regime slices and incremental lift. Preserve negative
   and inconclusive results.
5. **Strategy economics and Portfolio risk — engineering complete, empirical calibration pending:** bind strategy experiments to the
   canonical target while keeping Holding/Exit policies distinct. Report gross,
   explicit costs, net, turnover, drawdown and capacity; add basic name,
   exposure, liquidity, ADV, cluster, volatility, cash and drawdown constraints.
   Unqualified PIT membership remains exploratory or fail-closed.
6. **Attribution and feedback — engineering complete:** persist structured, non-causal diagnostic
   attribution from regime through costs/capacity. A diagnosis can propose a
   hypothesis, but only a newly frozen Experiment Protocol may execute it.
7. **Architecture convergence — engineering complete:** move source freezing behind a dedicated
   service, resolve operational packages through the PostgreSQL authoritative
   locator with immutable hash verification, expose real lifecycle boundary
   sets, and remove only code proven to have no consumer.
8. **Verification and publication — engineering complete:** the repository
   quality gates, PostgreSQL fresh/upgrade/idempotency/concurrency migrations,
   recovery/replay, CLI integration and deterministic statistical proof suite
   pass on the Phase D closure branch. Phase D is
   `PHASE_D_ENGINEERING_COMPLETE`; publication remains a Draft PR until review
   is complete.

## Phase E Historical Alpha Evidence Production

The representative vertical slice, Phase E2 expansion and Phase E3
longitudinal engineering expansion are complete locally.
Phase E2 freezes 300 real historical CSI 300 constituents plus `000300.SH` and
`510300.SH`, keeps PostgreSQL owner/lineage Authority, and uses bounded
timeframe/date/symbol-bucket Parquet reads for the same Canonical Decision-Time
materialization, T+1 Outcome, Panel, cumulative ablation, Strategy Economics,
Portfolio Performance, Research Evidence, interruption recovery and replay.

Phase E3 replaces the frozen cohort with 29 exact effective-date owners, runs
126 Decision Sessions over 6.5 months and consumes owner-resolved Industry,
published share and corporate-action facts. Decision and streaming Evidence
memory are bounded by session/keyset batches. This establishes longitudinal
engineering evidence, not completion of the empirical program: the frozen ETF
returns no observations, so Capital, Candidate, Signal and Forecast remain
not estimable; acquisition publication still has a 5.03 GiB peak; and no Formal
PIT/OOS or empirically calibrated execution input exists.

Phase E priority order is now:

1. Resolve a real, traceable intraday ETF source for the frozen context without
   index substitution, Daily-only fill or current-state projection.
2. Stream Provider acquisition and package publication so 1--3 year corpora do
   not inherit the current 5.03 GiB publisher peak.
3. Extend the same frozen methodology to 1--3 years and additional periods;
   retain the current negative/not-estimable findings without tuning thresholds.
4. Increase published-at-Decision share coverage and empirically resolve costs,
   fillability, impact and capacity before making an economic-value claim.

Engineering completion still does not supply qualified Provider history,
Formal PIT, qualified Historical Samples, pristine Formal OOS observations,
Calibration, prospective Strategy evidence or Production Admission.

### Earlier Phase D capability inventory

The prior branch is never merged or mechanically cherry-picked. Its capability
classification is:

| Capability | Disposition | Reason |
| --- | --- | --- |
| decision-session kernel | PORT | approved seam; rebase identities on the canonical target |
| PostgreSQL historical journal/runner | PORT | useful replay/recovery behavior; redesign migrations after 057 |
| full-A runtime scope | PORT | useful owner boundary; keep Provider-independent facts |
| observation/performance builders | PORT | extend with target identity and economic/diagnostic semantics |
| regularized linear math kernel | REUSE after proof | estimator is Provider-independent and deterministic |
| research-model persistence | REWRITE | bind Experiment, feature and target identities explicitly |
| formal-execution assessment | DROP/REWRITE | old form predates measure-oriented Forecast and explicit hypotheses |
| migrations 058--064 | DROP | current semantics require a new coherent migration history |
| historical branch documentation | DROP | current architecture documents remain the sole documentation hierarchy |

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
