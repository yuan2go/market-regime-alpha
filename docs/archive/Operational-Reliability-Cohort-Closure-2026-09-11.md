# Operational reliability and validity cohort closure observation

> **Status:** HISTORICAL
> **Work package:** WP-OPERATIONAL-RELIABILITY-AND-VALIDITY-COHORT-CLOSURE-01
> **Evidence class:** ENGINEERING_ONLY; DESCRIPTIVE / NOT_ALPHA_EVIDENCE
> **Operational cutoff:** 2026-09-11 11:04:48.216573+08:00

The installed reliability correction and controlled backup/restart pass their
bounded observations. **The work-package exit gate is NO:** the successor
ExperimentalModelUse cannot yet be registered through the original database's
owner authentication boundary. No v3 has been declared. The service is running
with the original ModelUse and preserves its pending frozen Prediction.

The [machine-readable record](Operational-Reliability-Cohort-Closure-2026-09-11.json)
contains exact observations, stages, capacity rosters, commands, failures and
private evidence hashes. It projects canonical facts; it creates no research
truth or qualification. Its final delivery SHA is the Git commit containing this
record, also recorded in the private `final-delivery-attestation.json`. Embedding
that commit's own SHA in its bytes would be circular.

## Source and installed scope

| Identity | Exact binding |
|---|---|
| Fetched baseline main | `09917b6e7072dfc66f172bde3ef504cff511ae2c` |
| Current remote main at final read | `09917b6e7072dfc66f172bde3ef504cff511ae2c` |
| Frozen implementation / installed wheel source | `d2c794f152e2f2670a78d9f295f42a1baad8a42b` |
| Source tree | `a517e329343db1c8137920c154a76b8d3be6c807` |
| Test tree | `c3277deb01a4d5c387af8c9b17dce19ca2c74846` |
| Wheel SHA-256 | `66f18696472af8c48918a29c6884e9f99224a80361a3db9c13bc9708284d837e` |
| Installed source SHA-256 | `37a399ff4af267a5f7eb71241a197c13ae575ced2c0e7859a2e441d69a43d7cf` |
| Current profile SHA-256 | `d413f1223da544ba4a5b8ec67ab3adcf0c6fa3ce43174d64838311c042ab504e` |
| Deployment receipt SHA-256 | `f65b59f0d183b51589483141faceb510a28c11d3ea4c9ac498697da1f4d7a092` |
| Original database / OID | `mra_wp18q_r2_operational_20260905` / `287543` |
| Cluster identity | `7681924516459622681` |
| Schema | PostgreSQL 16; `MRA_REFOUNDATION_1`; 194 research tables; no migration |
| Catalog SHA-256 | `44a27e01109567395ad803e0c0c3b2859e8890fb23cf27b0b2c26b98db559e51` |
| Artifact-root binding | `a44c60d4bbf9045fd33a119de4da520d965364d37904a79275fdc2236a7678a0` |
| Runtime principal / OID | `mra_r2_runtime_20260909` / `6775405` |

The isolated branch is `agent/wp-operational-reliability-validity-cohort-01`.
The original worktree, its unrelated IDE modification and previous installations
are preserved. No push, merge or PR was performed. Absolute deployment paths and
credentials remain in the private deployment record.

## Current operational state

At entry, 08:44:09+08:00, the owned service was stopped, its last exit was 2,
and the 03:00 backup job had failed. There was no unresolved Attempt. The actual
captured calendar ended Sep-17. Historical snapshots were not substituted for
these current observations.

At the cutoff, LaunchAgent `local.mra.prospective.r2-xshg32` is running with
observed PID 73892. That PID is an observation, not a future identity. The backup
LaunchAgent is loaded and idle. `KeepAlive=false` prevents an unbounded restart
loop. The exact principal allowlist passes at preparation, deployment and final
inspection; no privilege was added. Login identity/OID, memberships, dangerous
role attributes, database/schema/table/column/sequence/function grants and owner
boundaries remain checked before actions.

All-history Attempt states are 27,558 SUCCEEDED, 45 FAILED_TERMINAL and four
ABANDONED; active/expired/unknown Attempts are zero at the snapshot. An ACTIVE
parent Run is not an active Attempt. One real daily cycle is complete; the
Sep-11 Prediction remains PENDING_MATURITY. There is no pending settlement,
integrity-blocked daily work or overdue unterminalized prospective work.

## Reliability root causes and correction

The old installed controlled profile measured 87 before-action checks consuming
22.050 seconds, including 87 full installed-source hashes consuming 17.542
seconds. Principal verification consumed 4.341 seconds. These are overlapping
inclusive times, not independent quantities to sum.

Startup now fully verifies package, wheel, source, metadata and receipt. It
validates owned Python bytecode against the actual source, including the code
object and header, and disables subsequent bytecode writes. Before-action checks
compare the complete owned file roster and inode/ctime/mtime/size/mode/uid/gid
identity. Added, removed or changed source, resources, bytecode, wheel, metadata
or receipt fails closed. Profile, original DB/OID/cluster, restricted principal
and Runtime fence checks remain live; mutable business state is not cached.

The actual human-research-disposition health path scanned all 112,247 command
receipts twice. The correction restricts the query to the existing indexed
REGISTER_ARTIFACT command kind and exact business scope. Measured warm plans
were 148.025 ms for the original diagnostic query and 20.530 ms for the bounded
diagnostic candidate; the installed runtime-role query took 134.476 ms under
different I/O conditions. No new index or schema change was justified. This does
not claim the historical QueryCanceled timing was fully reproduced. Historical
failures and full population denominators remain visible.

An additional real P1 failure was found after the calendar acquisition. Run
`2a47cb6d-406f-5927-b8ea-ab647589fd1f`, step
`f7633eb9-38b6-49b8-90aa-13f672c8c91a`, failed with
NORMALIZER_OUTPUT_REJECTED on a successful empty BaoStock response before any
five-minute interval matured. The old normalizer filtered future gaps and then
rejected the empty batch. Its published bytes and terminal Run are unchanged.
An exact read-only Capture/receipt/Attempt/fence/Artifact/normalizer reconciliation
now recognizes this failure. Future pre-maturity empty Captures complete a
separate NO_MATURE_INTERVAL readiness contract; they manufacture no bar, gap or
label. Mature empty responses retain the original typed SourceGap semantics.
No failed Run was reopened and no failed Provider request was retried blindly.

A later delivery check found another real failure: the frozen 10:30–10:31 Run
`c55cb50f-b531-5bef-b279-e13b79bbb817` ended DEADLINE_EXHAUSTED. The installed
profile allowed only 16 attempts per tick for a 32-member roster. Sixteen actual
requests succeeded, and the last Attempt finished at 10:30:32.953716+08:00,
leaving 27.046284 seconds in the original window. The cap stopped further work;
the subsequent 30-second post-tick wait and framework processing reached the
remaining work after its deadline. One recovery Attempt became FAILED_TERMINAL;
15 other Steps remain READY beneath that permanently FAILED Run. All 16 absent
Captures remain absent. This was neither Provider error nor a 120-second tick
stop.

The same frozen wheel now has a new canonical profile/receipt with the shared
engineering attempt/step budget raised from 16 to the exact 32-member roster.
This field governs prospective attempts and daily maximum steps. It changes no
research plan, ModelUse, Target/window, label, cadence or 120-second guard. A new
backup, mirror, prepare-deployment and preflight preceded the controlled profile
handoff. The old profile is preserved. Its explicit original hash, operation
intent and new owner receipt form the predecessor chain; the receipt API's
previous_profile field itself identifies the explicit intent hash.

Two actual new-profile ticks took 26.102 and 26.255 seconds. The correction
removes the observed cap starvation, but a future complete one-minute window is
**NOT_OBSERVED_AFTER_CORRECTION**. Shared-generation demand, post-tick cadence and
Provider/framework variance remain timing risks for ongoing evidence. The old
FAILED Run was not reopened or relabeled as recovered.

## Performance evidence and budgets

| Installed observation | Ticks | Min | Median | p95 | Max | Resource stops | QueryCanceled |
|---|---:|---:|---:|---:|---:|---:|---:|
| Previous f30d45ab installation, available full log scope | 64 | 13.271 s | 62.284 s | 99.471 s | 123.923 s | 2 | 1 |
| New d2c794f1 installation, completed ticks | 37 | 23.394 s | 29.090 s | 40.909 s | 48.006 s | 0 | 0 |

The report uses nearest-rank p95. These are different actual workloads, not a
paired benchmark or a proof of sustained reliability. New logs contain 38 emitted
ticks: 37 completed and one 13.924-second gracefully stopped partial tick during
the profile handoff. No service-error/resource-stopped tick occurred. The
DEADLINE_EXHAUSTED Runtime Attempt above remains a separate actual failure; a
completed service tick does not imply every due member was captured. Three
new-install process activations are observed: deployment, manual backup restart
and the later budget-profile handoff. The earlier seven-tick observation remains
in the machine record with its own cutoff.

The new installed controlled profile took 28.577 seconds, including 16 actual
Provider requests. Full-source hashing on its hot path is **zero calls**.
Prospective continuation took 26.057 seconds; daily research 1.437 seconds;
prospective health 0.254 seconds; daily health 0.823 seconds. Within those stages,
124 before-action checks took 15.708 seconds inclusive, file-identity checks
8.597 seconds, principal checks 6.835 seconds, DB cursor execution 13.300 seconds,
and normalization 0.951 seconds. Provider transport execution is separately
recorded. Nested DB, filesystem and Provider timings must not be added to parent
stages. The preflight profile segment took 7.500 seconds; it is not whole cold
process-start latency.

Real startup logs additionally separate installed-profile verification,
principal/Artifact/backup preflight, Provider login and daily preparation. The
machine report preserves every measured stage and its inclusive-child marker.
The Prediction classification denotes the observed daily call path; it does not
assert that a new Prediction was published in each tick. Dedicated warm-idle,
mature Outcome/Evaluation and report/replay mutation timings remain NOT_OBSERVED
where they did not occur. They are not assigned zero latency.

The hard tick budget remains **120 seconds**. Warm-idle p95 below 60 seconds and
ordinary maximum below 90 seconds remain operational targets. Startup performs
full verification outside the tick. Prediction and Outcome/Evaluation retain
the same 120-second boundary and frozen Runtime continuation. Backup/restart has
one owned restart request and explicit phase receipts. No Provider batching or
timeout increase was introduced.

Exact historical process-stop-to-ready downtime is NOT_ESTIMABLE: log gaps do
not prove downtime. For the actual manual backup, the supervisor is known to be
unloaded from 02:17:17.054491Z through the restart request at
02:24:08.750225Z. This 411.696-second interval is a bounded stopped-supervisor
observation, not a precise application downtime estimate.

## Backup and recovery

The new shared backup/restart path actually passed as **MANUAL_BACKUP** in
receipt `refresh-20260911T021714505324Z`:
owned-service inspection → graceful drain → unresolved-Attempt/fence check →
snapshot backup → Artifact verification → second-device mirror → three-field
backup profile renewal → preflight → one restart → verified subsequent tick.
The full receipt duration was 491.475 seconds. Canonical backup verification
completed at 02:20:57.287026Z; its age at the earlier 10:26:31+08:00 snapshot was
334.126 seconds. That snapshot backup SHA-256 is
`09338ce78d7d43a9a715345578220f3333d28fc75f8941f5db16db752a31051f`.

The verifier rereads the exact restart observation and tick bytes, checks the
current configuration and backup receipt, and compares owned PID identity twice.
The recorded subsequent tick took 32.214 seconds and matched the renewed profile.
One explicit stopped-service recovery is bounded by backoff and current
Attempt/fence inspection. Unknown effects block restart/retry, and terminal Runs
remain terminal. Service and backup do not automatically relaunch each other.

The later attempt-budget profile handoff created a fresh original backup,
verified at **03:00:01.042738Z**. At the final cutoff its age is 287.174 seconds.
Its receipt SHA-256 is
`bd0e6b59263374ad046e45979267f0576d0354f34a05e5d34cbdf56758db6cb7`.
The mirror, new receipt/profile preflight and two actual subsequent ticks passed.
This is MANUAL_PROFILE_HANDOFF, separate from scheduled-fire reliability.

The Sep-10 19:00 and Sep-11 03:00 scheduled failures remain failures:
SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED. The new classified scheduled
receipt denominator is zero because no new scheduled fire occurred during this
observation; older unmarked receipts remain UNCLASSIFIED in that format and are
preserved in the all-receipt list. SCHEDULED_BACKUP_RELIABILITY is NOT_ESTIMABLE,
with NO_CLASSIFIED_SCHEDULED_RECEIPT. No manual recovery is called scheduled PASS.
03:00/19:00 schedules are still installed. The schedule witness explicitly admits
that an operator kick inside the allowed time window is indistinguishable.

**same-host redundancy != offsite disaster recovery**.

## Calendar capacity, ModelUse and v2

Real BaoStock Capture `da74567d-49ff-4e45-91bd-4c7291c50d50`, known at
2026-09-11T00:59:19.290427Z, requested Sep-11 through Dec-31. Its 112 civil rows
contain 74 actual open-session flags and zero missing calendar dates. Market
normalization receipt `34d5ab15-8c65-472d-b3a6-bbfe31139beb` owns these facts.
No weekday-derived sessions or silent Provider substitution were used. BaoStock
remains EXPLORATORY. The service now refreshes a bounded future calendar through
the existing Runtime/Market path, with duplicate, terminal and unknown-effect
guards; it does not introduce a scheduler or a second calendar owner.

The unchanged current Use is `60902ae3-5776-5460-91b1-90ed3bc03525`, valid from
2026-09-08 05:51:44.824938+08:00 through
2026-10-08 05:51:44.824938+08:00, with revoked_at null. v2 starts Sep-14 and still
requires **20 sessions / 500 observations**. Before expiry, the captured eligible
sessions are Sep-14, 15, 16, 17, 18, 21, 22, 23, 24, 28, 29 and 30: **12 sessions,
at most 384 sampled observations**, before any missingness. Capacity therefore
fails with **MODEL_USE_LIFETIME_INSUFFICIENT**. The now-complete calendar horizon
rules out an unknown-calendar explanation for this failure.

v1 and v2 bytes were compared to baseline main and remain identical. v2 hash is
`efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de`.
The generic feasibility reader distinguishes calendar uncertainty from lifetime
failure, counts exact pending populations, retains unavailable formal sessions,
and does not treat elapsed failures as remaining future capacity.

## Successor and cohort blocker

A reviewed, single-use maintenance procedure is prepared, **not executed**. It
would register an explicit new ExperimentalModelUse through the existing Model
owner using the same ModelVersion, Feature, Target, baseline and population
semantics. Proposed expiry is 2026-12-31T08:00Z; valid_from must be a fresh DB
clock plus two minutes after explicit approval. It would create a new
authorization Artifact and never rebind old Predictions.

The original `pg_hba.conf` explicitly rejects owner login to this database, while
runtime/diagnostics/backup allowlists correctly cannot register ModelUse. The
pending request is for a bounded exact-database, local Unix peer rule for owner
`yuan`, followed by original-byte restoration and ACL revalidation. HBA SHA-256
remains `183f3c28c132ab76aa7fa094e194c456372b6b49152d522e6a122d731bd67cf1`.
No owner impersonation, runtime grant expansion or HBA bypass was performed.

Only after registration and capacity revalidation can v3 be declared with a real
DB clock, predecessor v2 hash, the new Use, a strictly future first session and
the unchanged 20/500 floors. The planned first eligible date Sep-15 is not a
declaration. Ten downtime sessions and 20% missing-observation planning buffers
remain part of the prepared successor scope. There is **no v3 hash, declared_at,
registered new Use or passing successor capacity gate** at this cutoff.

Rollover implementation/tests preserve published or abstained windows across
Uses; original pending Outcomes retain their frozen Use; new windows require the
new explicitly authorized template. Reports show multiple Uses, while formal
validity cohorts remain separate. The live rollover gate is blocked until a real
successor exists. v2 has zero formal observations and has not been retroactively
populated with Sep-10 or Sep-11.

## Frozen work and health denominators

Completed Prediction `3c3e181e-692d-535b-aea0-f855c9e9e418`, plan SHA-256
`eae5144cbdca838cc32e2b673f0a620dcb89455a3b8760cbe9fb37410f3e0442`,
still owns Evaluation `2849c414-da2a-5a8d-bb9f-483aed6df465`. Every field in the
initial completed-cycle projection, including its original Evaluation metrics,
publication, labels, source references and replay, equals the final value. The
new projection adds richer canonical lineage fields. Final replay is matched,
mismatch_count=0, business_writes=0. No second label set or report metric was
created. The original 31 canonical labels remain finality UNKNOWN.

Prediction `53e60935-9130-5898-8a3a-f53e71d0743b` remains the original Sep-11
pending work, published Sep-10 at 23:33:34.510317+08:00, with the old Use. Its
current frozen plan and publication were owner-reloaded. The older installed
entry projection did not export pending-plan bytes, so the comparison record
does not claim an independent before/after pending-byte snapshot. No replacement
Prediction was created; the daily request ledger remains six entries.

| Daily health scope | Requests | Timely publications | Completed Outcomes | Evaluations / reports | Replay checks / mismatches |
|---|---:|---:|---:|---:|---:|
| ALL_HISTORY | 6 | 3 | 31 | 1 / 1 | 3 / 0 |
| POST_CURRENT_CUTOVER | 4 | 2 | 31 | 1 / 1 | 2 / 0 |
| LAST_N_TRADING_SESSIONS (Sep-7 through Sep-11) | 6 | 3 | 31 | 1 / 1 | 3 / 0 |

Publication denominators are DECLARED_PREDICTION_OR_ABSTENTION_REQUESTS,
respectively 3/6, 2/4 and 3/6, state ESTIMABLE, reason_code null. The canonical
cutover remains 2026-09-09T15:45:50.016124Z; the technical deployment did not reset
it. All scopes retain their historical failed/missed requests.

Prospective ALL_HISTORY retains **752 MISSED** windows, including the original
544, the 32 windows terminalized after the pre-open failure and the 16 uncaptured
10:30 members. Its 800 opened expected windows contain 48 on-time Captures and
800 terminal windows; capture/on-time rates are 48/800 and terminal coverage is
800/800. Expected future windows remain separate. There is one historical planning gap, zero due backlog,
zero overdue unterminalized work, zero expired active lease and zero unknown
effect. ATTENTION_REQUIRED preserves these historical alerts. There are 768
runtime-failure window classifications, including 16 captured members whose
parent Run failed; these are not 768 failed Attempts and do not erase the
successful Capture numerator.

## Validation, build and deployment

| Command/scope | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| Final affected pytest scope | PASS, 324 tests |
| Docs/hygiene contract pytest | PASS, 28 tests |
| Final capacity correction | PASS, 55 directed tests |
| Operation guard PostgreSQL scope | PASS, 12 tests |
| Principal/restricted-login directed correction | PASS, five cases after recorded initial failures |
| Calendar/admission/terminal/rollover/query/replay PostgreSQL scopes | PASS on disposable databases; original command receipts indexed |
| Backup proof / installed identity / performance projection tests | PASS; original directed receipts indexed |
| Global Ruff / configured mypy | PASS; mypy checked 647 files |
| Inventory/hygiene / documentation links | PASS |
| Frozen wheel and sdist build | PASS |
| Isolated installed CLI and real read-only v2 report | PASS |
| Fresh backup, prepare-deployment, preflight, activation and multiple ticks | PASS |
| Actual installed manual backup and subsequent tick | PASS |
| Same-wheel 16→32 budget profile handoff | PASS; new backup/receipt/preflight and two actual ticks |
| Full repository regression | NOT_RUN; no Pool/UoW/schema/common Runtime engine change |

The command index retains failed runs rather than relabeling them: shared-cluster
disposable PostgreSQL lock exhaustion, fixture calendar isolation, missing test
URL configuration, three type-inference errors and an intermediate inventory
check were corrected and directed checks rerun. No production database was a
destructive fixture, no database lock budget or runtime permission was increased,
and no failing assertion was weakened.

The first private deployment preparation failed with ActiveSqlTransaction before
backup or mutation. Its helper was corrected to use an autocommit diagnostic
connection before the repeatable-read projection; the failure record and old
helper were preserved. The frozen wheel did not change. A wrong installed CLI
option was rejected before database access, then the documented command passed.
The first private budget-handoff invocation could not import its helper module
from the evidence directory and failed before main or any live mutation; the
byte-identical reviewed helper ran from its dependency directory. The first
delivery docs check rejected an unsupported archive metadata status; it was
corrected to the existing HISTORICAL vocabulary and the unchanged checker passed.

Deployment used a frozen wheel, isolated install, fresh original backup,
registered preparation, exact-scope preflight and owned activation. Old wheel,
profiles, receipts and wrapper/plist bytes remain preserved. The actual final
backup renewed only permitted backup identity fields and reverified installation
on restart. Documentation delivery does not redeploy the service again.

## Exit gates and next boundary

| Gate | Result |
|---|---|
| OPERATIONAL_PERFORMANCE_BOUNDARY_PASS | PASS, bounded current installed observation |
| SCHEDULED_BACKUP_RECOVERY_CONTRACT_PASS | PASS, tests and actual shared manual path; no new scheduled PASS |
| COHORT_CAPACITY_FEASIBILITY_PASS | BLOCKED; successor not registered; v2 FAIL |
| MODEL_USE_ROLLOVER_PASS | Implemented/tested; LIVE_BLOCKED |
| VALIDITY_V3_PREDECLARED_PASS | BLOCKED; not declared |
| OPERATIONAL_RELIABILITY_AND_VALIDITY_COHORT_CLOSURE_EXIT_GATE_PASS | **NO** |
| SUSTAINED_MULTI_DAY_PROOF | BLOCKED_BY_ELAPSED_REAL_TIME; one completed real session |
| MODEL_VALUE / ALPHA_PROVEN | NOT_ESTIMABLE / NO |

The service continues natural operational observations under the old exact Use.
Formal long-lived cohort accumulation requires the pending owner maintenance,
successor registration, real capacity validation and immutable future v3
declaration. No Alpha iteration, formal PIT promotion or Production admission is
permitted by this engineering evidence.
