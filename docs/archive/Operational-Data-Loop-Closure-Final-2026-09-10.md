# Operational closure — final correction and observed recovery

> **Status:** HISTORICAL
> **Work:** WP-OPERATIONAL-DATA-LOOP-CLOSURE-01
> **Observation cutoff:** 2026-09-10 02:47:42.966112 UTC / 10:47:42 +08:00

This continues the same branch and evidence chain after the immutable
[10:07 observation](Operational-Data-Loop-Closure-Verification-2026-09-10.md).
That observation was followed by a real service failure; its earlier PASS at a
cutoff is not reused as a claim that the service remained running afterward.
The [final index](Operational-Data-Loop-Closure-Final-2026-09-10.json) binds the
additional source, raw failure, query plans, tests, deployment and observation.

## Actual failure and bounded correction

At **10:08:02**, PostgreSQL backend 94097 cancelled the daily health freshness
statement after its 30-second statement timeout. The exact server error and SQL
are retained in `postgres-query-canceled-exact.log`. The service failed closed;
there were zero active/expired/unknown Attempts and no Provider effect to retry.
The parallel-worker termination lines are PostgreSQL cancellation cleanup,
not a manual kill of unknown processes.

The query aggregated `max(recorded_at)` across an entire Provider's bars,
with a planned parallel scan of about **196,635 rows**. This was also a scope
error: a later normalization for a different security or session could make a
frozen daily plan appear fresh. A canonical Market normalization counterexample
failed on the original query. Both independent session/security exclusions now
pass through the full daily and restricted-login contracts.

`PostgresDailyPredictionReads.operational_health` now restricts bar freshness
to the frozen plan's instrument IDs and input/target session IDs. It emits
`bar_scope=FROZEN_PLAN_INSTRUMENTS_INPUT_AND_TARGET_SESSIONS`.
Capture and SourceGap timestamps remain explicitly Provider-product scoped.
This read-only projection changes no DataReady admission, price/Outcome label,
forecast, metric, strategy, Model, Target or historical report bytes.

An actual `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` now uses the existing
`market_bar_exact_asof_idx`, visits **32 bars**, and completes in **3.143 ms**;
the full health projection took 1.236 seconds. No index, migration, pool/UoW or
timeout changed. The failed statement and its unbounded/scope defect are proven.
Warm repetitions of the old parallel/serial query also completed in 72–141 ms,
so the underlying intermittent I/O/latency cause is **not** claimed fully solved.

## Final revision and installation

| Binding | Identity |
|---|---|
| Baseline main | `90c5af03c905b1c91a4c284cd838ea39166a5c42` |
| Final implementation | `55d4aba91f7eb9781b45204f8765edc3fcba05b1` |
| Source tree | `75d6c367b8e1320e5ebd17d6b1da63019522bb42` |
| Tests tree | `080d5b7a0d2185c96365c8ee51b3cc404d12042c` |
| Wheel SHA256 | `f28ae7a508877fc77a942fab8ff487072010eb54b38bccf8fa83d4d1df5fef5f` |
| Installed source hash | `3c21c9351cb064c32203c1817771a9ae61437f6ff750de503633cb97a398b41c` |
| Installed package roster | `bb9e15f7a4ef494da681b85497dc5e4022d91826df634e2c04843bcc2c1fcc1c` |
| Operation profile SHA256 | `2c4d40bff5a62a62240342776620c0dab54cc18796e50b960c11b2dd6d7a550a` |
| Deployment receipt SHA256 | `ea8338d971ed55b71118c3f682dc2e117e895cbdd7211d39bd5dd0bad0c1c0ba` |

The final delivery commit is documentation/evidence only and is bound in the
external delivery attestation. The unchanged schema remains v8, epoch
`MRA_REFOUNDATION_1`, 194 tables, catalog `44a27e01109567395ad803e0c0c3b2859e8890fb23cf27b0b2c26b98db559e51`.
All 113 released SQL resources and the dependency lock remain unchanged.

At the clean implementation, **42 affected tests passed** in **71.543 pytest /
73.323 wall seconds**: daily normal/missing/maturity, restricted login, recovery,
handoff, principal drift, deployment and CLI. Ruff, mypy, wheel/sdist build and
seven isolated installed CLI checks passed. Earlier unchanged admission/scoped
health/import checks retain their exact source-bound reuse; counts are not added
as distinct tests. The final index records documentation/hygiene/diff checks.
Full repository regression remains NOT_RUN under the authorized directed scope.

An installed smoke was first started before dependency installation completed;
its ModuleNotFoundError is retained. Repeating it after completed installation
passed without changing package code or assertions. No failure is hidden.

## Actual handoff, backup and recovery

The original database remains `mra_wp18q_r2_operational_20260905`, OID 287543,
cluster 7681924516459622681. Principal `mra_r2_runtime_20260909`, OID 6775405,
still passes the 88-table / 25-reference-column positive and negative envelope.
No subsequent role, HBA or business-schema change was needed for the query fix.

The stopped exact owned job was unloaded only after inspection and zero
active/unknown Attempt confirmation. The new wheel was installed separately;
new immutable intent/profile/receipt were generated through the canonical
deployment command. A current backup, full physical verification, independent
restore and live preflight passed before activation.

New backup: **2,975 Artifacts**, dump **209,567,901 bytes**, SHA256
`3791f8e90fa980ba00ae7f8a6f739abb84729dc64c03f308e2733f8b97e95c26`.
Compared with the preceding 2,974-Artifact snapshot, 190 table hashes remain
identical and four tables each gain one row for this installed code Artifact,
verification, Receipt and Audit. No prediction, Outcome or failed Run changes.

Independent restore `mra_closure_repair_restore_20260910`, OID **3812198**,
cluster **7683543274548948162**, reconciled all 194 table hashes and referenced
bytes, then repeated the original publication replay with **matched=true,
mismatch_count=0, business_writes=0**. It remains a verification scope. A
byte-verified mirror is on a second physical device on the same host, not offsite.

The existing owned job `local.mra.prospective.r2-xshg32` activated the corrected
installation at **10:43:04**. At the cutoff its observed PID was **4005** and
three completed ticks took **51.600, 45.620 and 45.294 seconds** against the
unchanged 120-second budget. Active/expired/unknown Attempts were zero. Existing
03:00/19:00 backup refresh uses the same new interpreter, preserving the actual
03:00 scheduled-run evidence and the original cutover cohort boundary. No
unconditional restart or future scheduled success is claimed.

## Frozen prediction, health and independent gates

Prediction `3c3e181e-692d-535b-aea0-f855c9e9e418` remains the original timely
02:17 publication for today's **09:30–15:00** Target. Original plan code
`1b5377d6…`, ModelVersion `fe47f296…`, experimental use, Dataset, Decision and
Target identities remain unchanged. **32 sampled / 31 model / 31 baseline /
31 common / 1 UNKNOWN**; **31 expected Outcome commitments, 0 completed**.
Publication JSON/Markdown identities and bytes still reconcile with zero writes.
Outcome/Evaluation statistics remain NOT_ESTIMABLE / TARGET_NOT_NATURALLY_MATURE.

The day ledger and ALL_HISTORY / POST_CURRENT_CUTOVER / LAST_N_TRADING_SESSIONS
counts remain those in the earlier complete ledger: historical 544 MISSED stay
visible; post-cutover has 320 future prospective windows and zero opened,
therefore no estimable success rate. Post-cutover daily requests are 3, with one
timely publication, one terminal failure and one missed publication. One planning
gap remains explained. No integrity-blocked or unknown-effect backlog is hidden.

| Gate | Final observation decision |
|---|---|
| OPERATIONAL_HANDOFF_PASS | PASS at the corrected-installation cutoff |
| CURRENT_OPERATIONAL_HEALTH_PASS | PASS at cutoff; declared failures/gap retained |
| REAL_MATURE_EVALUATION_PASS | BLOCKED_BY_REAL_TIME |
| OPERATIONAL_DATA_LOOP_PROOF_EXIT_GATE_PASS | BLOCKED_BY_REAL_TIME |
| SUSTAINED_MULTI_DAY_PROOF | BLOCKED_BY_ELAPSED_REAL_TIME |
| Alpha iteration / Model or formal PIT promotion / Production | NO |

The service is left to accumulate real facts through its original pending plan.
No waiting, backdating, historical substitution or terminal reopening was used.
Continue observing the bounded service and its failure logs; do not claim stable
multi-day operation or start Alpha iteration before real Outcome/Evaluation closes.
