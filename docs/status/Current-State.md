# Current implementation state

> **Status:** CURRENT_STATUS
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/schema.py`, `tests/contracts`

This page describes checked-out implementation, not an operational database or
research qualification. Verification results must match the affected implementation and consumer
scope; earlier hygiene evidence remains in the archive index.

## Research Validity baseline

The read-only baseline is implemented on main
`c61a133995c015530a992a87421e750e64f4d5ef`. `mra research validity daily`
consumes exact frozen Prediction, acquired OutcomeRevision and Evaluation truth;
it does not acquire prices, train, tune or update historical metrics.

Protocol v2 was declared from the original database clock at
2026-09-11 00:37:36.769896+08:00, before its first eligible Target session Sep-14.
Its exact SHA-256 is
`efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de`.
It requires 20 real estimable sessions and 500 common observations, a 20-session
rolling window, K=5 and five-quantile tails. Model/use/Feature/Target, Candidate,
Eligibility, Context, Provider, classification and the complete fixed 32-member
instrument scope are bound. v1 bytes remain unchanged; a pre-Outcome review found
its missing exact population binding, so it cannot establish a validity baseline.
Sep-11 remains descriptive under that predecessor; no session is deleted.

The new read projection includes exact source/normalization clocks, all acquired
Outcome revisions, complete population/exclusions and original report/replay.
Evaluation-owned Decimal formulas provide common-population errors, direction,
calibration, ranking and per-session/aggregate/rolling IC statistics. Calendar
and lineage reads preserve the entire cohort; date filters only select a
descriptive view. The default operational health budget remains unchanged.

The first new CLI observation still has only Sep-10 complete: 32 sampled,
31 common estimable, 31 complete labels with finality UNKNOWN, and temporal PASS.
Its original 10 metrics/report bytes remain unchanged. New historical statistics
are `POST_HOC_DESCRIPTIVE`, including any direction/calibration result. The future
v2 cohort has zero observations: `MODEL_VALUE=NOT_ESTIMABLE`, `ALPHA_PROVEN=NO`.
Real sample minima and repeatable information gain are required before any
Alpha-iteration proposal.

Walk-forward dry-run, source/time/model boundary checks and an advancing actual
calendar cutoff are implemented; currently 168 completed captured sessions and
one completed canonical session are insufficient for the 337-session window.
`WALK_FORWARD_READY=NO`. Additional regime slices, economic/tradability and Formal
PIT readiness remain NOT_READY. BaoStock evidence remains EXPLORATORY. Independent
episode economics does not establish continuous-account returns or T+1 execution.

The initial fresh observation at Sep-11 00:18 confirms the original service is
running with no unresolved Attempts and Sep-11 Prediction pending maturity.
Its observed tick maximum is 82.08 seconds, below the unchanged 120-second budget.
This analysis package does not stop or redeploy that service. Final validation
and operational cutoff are recorded with source-bound evidence after installation
smoke; sustained proof still requires three consecutive naturally completed days.

## Latest operational cutoff

At **2026-09-10 23:46:12.905706+08:00**, installed implementation
`f30d45ab2680798c67ead58d5453e00ed2f2d74e` is running in the original database,
Artifact root and restricted principal. The original Prediction's real mature
Evaluation, complete-cycle zero-write replay, current scoped health and operational
data-loop exit gates pass. The final health snapshot has no active/expired/unknown
Attempt or unprocessed mature daily work. Historical terminal failures and all
704 MISSED windows (including the original 544) remain visible. This is a bounded
observation, not a service-uptime or Alpha guarantee.

The 19:00 backup job actually fired and failed because service was stopped. A
separate authorized manual recovery now proves graceful drain, backup, Artifact
verification, mirror, profile advance, restart and a subsequent current-profile
tick. New profile SHA-256: `d4dfb191f5b681469b412a1f071de8b5f6c76bf2e0f5aa7e2bf469a8dcfcc088`.
Both physical devices are on the same host; there is no offsite disaster-recovery
claim. The first new-deployment tick took 67.75 seconds while publishing the next
real session's Prediction; after backup restart the first tick took 47.83 seconds,
within the unchanged 120-second budget. Complete latency and downtime observations
are in the [immutable report](../archive/Real-Maturity-Operational-Closure-2026-09-10.md).

The next Target session, 2026-09-11, has a timely frozen Prediction and remains
PENDING_MATURITY. One actual completed session permits the narrow Research Validity
entry; it does not satisfy sustained evidence. **SUSTAINED_MULTI_DAY_PROOF remains
BLOCKED_BY_ELAPSED_REAL_TIME** until at least three consecutive real sessions.
All model comparisons remain **DESCRIPTIVE / NOT_ALPHA_EVIDENCE**.

## Reproducible schema facts

<!-- schema-facts:start -->
Epoch: `MRA_REFOUNDATION_1`.
Research table count: **194**.
<!-- schema-facts:end -->

These values are checked against the executable SchemaManager contract.
The schema inventory records SQL checksums; fresh PostgreSQL bootstrap/verify
checks the complete catalog. There is no hardcoded index/constraint count or
mixed-version operational checksum table here.

## Current execution

| Surface | Implemented/wired fact | Limit |
|---|---|---|
| Generic Backtest | Specification, Runtime action execution, owner reconciliation, Model lineage, report and comparison are composed by `bootstrap_application` | A declared/finished Runtime is not sufficient without complete owner replay |
| Prospective collection | Guarded serve, DB due query, atomic writer admission, lease/fence, overdue and planning-gap recovery | Current service/due/success cannot be inferred from source, old status or a running process |
| Daily research | Post-close DataReady; exact experimental Model use; independent forecasts; frozen publication; real mature Outcome/Evaluation, report/replay and delivery recovery | Availability, actual publication time and real maturation are separately observed facts |
| Economics | Typed deterministic fully funded independent episodes; root/child field reconciliation and full-path slicing | No continuous-account/tradability/Alpha claim; historical formula meanings remain unchanged |
| Evidence operations | Exact database/Artifact identity, backup, integrity and restore/replay operations | A successful copy is a separate scope; missing original evidence remains missing |
| Retained execution/account | Decision/account and formal governance commands remain installed; separate research CLI dispatch is retired | No account Runtime migration or broker admission |

Repository maintenance by itself does not change or requalify a live service,
Provider capture or research result. Separately authorized activation evidence
is recorded below. Current operational facts must be obtained through the runbook's exact-scope status/health/replay
commands under the relevant authorization.

## Consumer convergence

Four commands are installed: `mra`, `decision-system`, `model-governance` and
`pit-authority`. The canonical research import closure does not depend on
`research`, `platform`, `application/historical_corpus` or `persistence`.
The generated inventory includes the complete executable consumer matrix and
SQL-adapter closures. Historical tools are outside current execution; exact
readers and the observed-account/governance exceptions remain explicit.

Consumer convergence changed no released SQL bytes, schema membership, research
formula, Model/Outcome identity or operational database. Source retirement does not prove
live deployment or authorize account Runtime cutover.

## Research Runtime cutover verification

Baseline: `a8cf743dc504f9574f490a64e2dc96e68025371c`.
Implementation: `4b65c14cc445034b340c83e34aa9277c7e67151f`.
Source tree: `9a45fb76c44b104a89929fa3a4adb813a053b89e`.
Tests tree: `a7ca20db9e4b4fd5f0acee4ff80a5264106b2377`.
The final delivery commit changes only current status/runbook prose; the source,
tests, SQL, dependencies and executable templates match this implementation.

New current research enters `mra` through `bootstrap_application`. The remaining
all-day runner and FreeData service wiring are removed. Account journal values,
observed-Fill commands, formal Model/PIT governance and explicit historical
inspection/verification retain their distinct owners.

Installed execution requires a verified source/wheel/package/dependency receipt
and exact operation profile. Canonical non-Attempt owner commands and retained
write connections participate in reservation admission. Runtime inspection uses
a database-enforced read-only UoW. Original daily plans remain recoverable after
installation or Model-use changes; completed settlement/report recovery does not
reacquire Market inputs or repeat completed Evaluation.

| Check / scope | Executed evidence at this implementation |
|---|---|
| Canonical contracts, architecture, repository scripts | 1,229 passed in 1,075 seconds; includes Runtime/fence, daily normal/missing/crash, Outcome/Evaluation, schema/upgrade and historical decoder contracts |
| Retained persistence, CLI, account, execution and formal governance | 664 passed in 579 seconds; rerun after the shared connection change |
| Independent installed wheel | 23 checks passed; four installed commands, verified profile generation, old profile/new implementation refusal, wrong scope/extra installed file refusal |
| Preserved vertical slice and independent restore | 32-member prediction → mature Outcome → Evaluation → report/replay; new restore DB/root, complete table/Artifact reconciliation and repeated installed CLI replay match with zero business writes |
| Query scope | 11 actual EXPLAIN ANALYZE/BUFFERS JSON plans; replay/health/worklist 0.10 seconds on the 32-member fixture; not a production-load benchmark |
| Static/build/docs | Frozen sync, Ruff, mypy (635 configured files), inventory/hygiene, links and diff checks pass; isolated build/install pass using cached offline dependencies after an online TLS failure |
| Schema/dependencies | All 113 SQL resources and dependency lock unchanged; 194 canonical tables, no new migration |
| Repository collection / full execution | 4,138 collected; full repository execution NOT_RUN under the explicitly bounded regression scope |
| Operational mutation / real prospective proof | NOT_AUTHORIZED / NOT_RUN; no actual service, LaunchAgent, writer or operational database changed |

The source-bound incremental bundle `canonical-runtime-cutover-20260909.tar.gz`
contains `verification.json`, raw failures and repairs, exact commands/exit codes,
CLI/owner inventory, wheel and installed identities, disposable DB/Artifact
identities, backup bytes, restore/replay receipts and query plans. The engineering
research Runtime cutover gate passes. This does not establish live activation,
sustained collection, formal qualification or research validity.

Previous consumer-convergence evidence remains in
`canonical-consumer-convergence-20260908.tar.gz`; its source-bound verification
SHA256 is `1af0b50072d40bb3ed4be0851b39f09cb25f4a2ca73f3bbde91337f9af25ed8f`.
Prior failures and released SQL retain their original bytes and meaning.

## Original-scope operational activation

The one-time activation prerequisite at merged main
`876b995268673b6556c1f148c9c9af485cd8f135` passed **4,142 repository tests**,
including PostgreSQL, and **7 explicit historical tests** with locally recovered
prerequisites. Ruff, mypy, build, installed-wheel smoke, docs, inventory and
hygiene passed. This does not automatically qualify later changes.

Initial activation used `1b5377d6adf46b61b06f34356bd37f2e599c74e5`;
source tree `1e8f6682340c8591f25d7575f2960ae13197c3fc`. Its final directed
43-test regression passed at test-only commit
`0d09cda03f24146dbef4a224b91076bd17305e3e`, which preserves that source tree.
The previous one-test fixture failure remains in the evidence chain. Later
status prose does not change installed code. Exact scope receipts, raw commands,
failures and hashes are indexed through the historical archive, not used as
configuration defaults.

Activation uses the original research database and Artifact root discovered from
the private deployment record. The existing registered v8 additive upgrade was
applied after backup and isolated verification; no released SQL/lock bytes were
edited. A dedicated runtime login, read-only diagnostics/backup logins and exact
project-database authentication rules exclude stale generic-login clients. This
is an operational boundary, not protection from a trusted OS/cluster admin.

Actual input collection completed 32 daily bars and normalized the Provider's
300-member classification. One earlier normalization failure and its explicitly
requested successor retain separate identities. An expired Artifact prerequisite
caused the old mature prediction's settlement to fail; a missing reference-lock
grant caused the initial current prediction to fail. Both terminal Runs remain
failed. The repairs refresh owner-verified bytes, validate the restricted login's
complete daily call chain and expose terminal prediction failure without
blocking other pending plans. No model, Target, formula or failed result was
rewritten.

The distinct current-time prediction
`3c3e181e-692d-535b-aea0-f855c9e9e418` completed all nine owner/Runtime actions.
Publication at **2026-09-10 02:17:35 +08:00** precedes its exact **09:30–15:00**
Target. Its frozen population contains 32 members: 31 included/eligible,
feature-ready and predicted by both the original Ridge and baseline; one
membership UNKNOWN remains visible with its reason. The publication report and
repeated request reconcile with unchanged identities and report bytes. The
original ModelVersion and experimental use remain unchanged.

The owned service completed a graceful drain and restart on the same installed
artifact. The post-publication backup binds 2,973 Artifacts to an exported
PostgreSQL snapshot; a separate DB/root restored it and reproduced the complete
installed CLI report/replay with zero business writes. Existing backup refresh
is enabled at 03:00 and 19:00 with bounded fault behavior. At the frozen
observation cutoff, six final-installation ticks took 41–51 seconds each against
a 120-second budget; active, expired and unknown Attempts were all zero.
Historical failures keep health at attention-required; startup does not erase them.

Natural Outcome maturity and multi-day service are separate, still unobserved
requirements. The old mature terminal failure cannot satisfy them. Current
health retains missed prospective windows and planning gaps rather than treating
terminal coverage as collection success. New daily captures do not retroactively
qualify the separate intraday prospective series. No Alpha, formal Provider/PIT,
Model or Production qualification is granted.

## Prior operational closure observation

The first closure installation was
`db69cd34f6ef569663fac4f7029d79783b52948e`, based on merged main
`90c5af03c905b1c91a4c284cd838ea39166a5c42`. Source tree
`0b76762931fafeee4f86b07bc3dcc89d9d6db0c3` and tests tree
`433d9dc81485f3bf0d8ebd88a7be9410d59a140c` bind the implementation.
No SQL resource, schema membership, model, Target or dependency changed.

The authenticated runtime login now has an explicit positive and negative
privilege envelope in `infrastructure/postgres/runtime_privileges.py`.
Preflight and before-action checks reject impersonation, changed role identity,
dangerous role flags, additional table/column/sequence writes, role memberships,
grant options and unapproved routines. Reference-owner identity-column grants
support row locks; they do not authorize schema, Account, formal Model/PIT or
research qualification. The original role's excess GC-candidate INSERT and
whole-table UPDATE were revoked after a verified backup. The trusted cluster
administrator remains outside this untrusted-client threat boundary.

`mra research daily health` reconciles original frozen plans and reports a
complete day ledger. The daily and prospective projections expose ALL_HISTORY,
POST_CURRENT_CUTOVER and exact recent TradingSession cohorts. Rates retain
explicit numerators, denominators, denominator kinds and unavailable reasons.
No history is deleted and an unchecked replay is not a passing replay.

At **2026-09-10 10:07:13 +08:00**, the original owned service was running the
new isolated wheel/profile after activation at 09:58:55. Six completed ticks
took **36–66 seconds** against the unchanged 120-second budget. Active, expired
and unknown Attempts were zero. The earlier service's 09:11 resource stop
(123-second tick) remains recorded; its historical latency cause is unproven.
It was recovered through the exact owned-service handoff, without reopening
terminal Runs or increasing a timeout.

The priority prediction remains the original timely publication above, with
31 predicted/common members and one UNKNOWN in the 32-member population. Its
31 Outcome commitments are pending natural maturity at 15:00. Publication
report/replay still matches with zero business writes. There is no real mature
Evaluation yet, and no financial metric or Alpha inference is substituted.

| Independent observation | Result at this cutoff |
|---|---|
| Current health | Privilege envelope, identity, fresh backup and complete ledger pass; known terminal failures and one planning gap remain explained and visible |
| Historical / post-cutover prospective windows | Historical 544 MISSED retained; post-cutover 320 future, zero opened, no estimated success rate |
| Daily requests | All-history 5 requests / 2 publications; post-cutover 3 / 1; request denominator includes terminal failures and abstention |
| Scheduled backup continuity | Actual 03:00 fire, graceful drain, backup, integrity verification, mirror and restart completed in about 885 seconds; the 03:00/19:00 job now uses the new installation |
| Updated backup and restore | 2,974 referenced Artifacts; all 194 restored table hashes match; original prediction replay matches with zero writes; same-host second physical device is not offsite |
| Directed verification | 125 scoped cases passed; 26 affected cases rerun at the final implementation; Ruff, mypy, build and seven isolated installed CLI checks passed |
| Full repository regression | NOT_RUN: no shared pool/UoW/schema change in this scope; earlier full activation results are not relabeled as this revision's full PASS |
| Real mature Evaluation / complete data loop | BLOCKED_BY_REAL_TIME |
| Three-day sustained proof | BLOCKED_BY_ELAPSED_REAL_TIME |

Exact receipts, complete scope ledgers, failures, query plans and raw-log hashes
are retained in the [archive index](../archive/README.md). These are observations
at a frozen cutoff, not a guarantee that the service remains alive later.
Continue original pending work through the Runtime and inspect actual health;
research validity/Alpha iteration remains premature until a real Evaluation
closes the lineage.

## Subsequent health-query correction

After that immutable cutoff, the service stopped at **10:08:02** with
`QueryCanceled`. PostgreSQL's original error log identifies the actual statement:
`PostgresDailyPredictionReads.operational_health` scanned all Provider bars to
report the latest bar timestamp. The plan scanned about 196,635 rows. Besides
unbounded observation cost, a different security/session could incorrectly make
the current daily plan look fresh.

The correction is frozen at `55d4aba91f7eb9781b45204f8765edc3fcba05b1`, source
tree `75d6c367b8e1320e5ebd17d6b1da63019522bb42`, tests tree
`080d5b7a0d2185c96365c8ee51b3cc404d12042c`. Bar freshness now explicitly means
the frozen plan's instruments and input/target sessions. Capture and SourceGap
timestamps remain product-scoped; the new `bar_scope` field makes this distinction
visible. No financial result, label, model, deadline or owner validation changes.

The canonical-normalization counterexample failed before the fix for an unrelated
session; both session/security exclusions passed afterward. **42 affected tests passed** at
the corrected revision, including restricted-login daily prediction, maturity,
recovery/report and deployment. Ruff, mypy, build and seven isolated installed
CLI checks passed. The original read-only query now uses the existing
`market_bar_exact_asof_idx`, visits 32 bars and takes about 3.1 ms; no SQL resource,
index, migration, pool, UoW or timeout was changed. The exact failed-query trigger
is identified; warm reruns of the old query also succeeded, so the underlying
intermittent I/O/latency cause is not claimed solved.

Final installed handoff and post-recovery observation are recorded separately
in the archive index. The 10:07 snapshot cannot establish health after the 10:08
stop. Natural Target maturity remains a separate real-time requirement.

The corrected installation activated at **10:43:04 +08:00**. At the final
**10:47:42** cutoff, three ticks took 45–52 seconds, with no active/expired/unknown
Attempt. Original publication replay still matched with zero writes. The new
2,975-Artifact backup and another independent restore matched all 194 table
hashes and original report bytes. The owned service and existing scheduled
backup task use the corrected wheel/profile. Current health passes at this
bounded cutoff with explained terminal failures retained; naturally matured
Evaluation and three-day sustained service remain independently time-blocked.

## First naturally matured daily Evaluation

On **2026-09-10 at 22:51:58 +08:00**, the original timely Prediction
`3c3e181e-692d-535b-aea0-f855c9e9e418` completed canonical Outcome/Evaluation in
the original operational database using installed implementation `55d4aba9…`.
Its original plan hash `eae5144cbdca838cc32e2b673f0a620dcb89455a3b8760cbe9fb37410f3e0442`
and code, ModelVersion, Dataset, Decision and Target identities remain unchanged.

Actual late Provider requests from **22:46:31 through 22:49:15** produced
32 daily Captures and Bars. The original population retains 32 sampled members,
31 eligible/model/baseline/common predictions and one membership UNKNOWN.
All 31 commitments settled; Partition and Evaluation acquisition rosters are
exactly those 31. Evaluation `2849c414-da2a-5a8d-bb9f-483aed6df465` contains
10 frozen-protocol metrics and 310 metric observations. All 31 labels are complete
and estimable; Provider availability/finality qualification is not promoted.

Original Prediction report bytes, Evaluation report and completed-cycle replay
reconcile with `matched=true`, `mismatch_count=0`, `business_writes=0`.
Model/baseline MAE are **0.0097543 / 0.0106481** and rank IC are
**0.192742 / -0.192742**. Actual labels include 10 positive, 20 negative and one
flat value; all 31 model forecasts are positive. Directional accuracy is absent
from the frozen Evaluation protocol and is not invented by a reporting script.
This single-session result is **DESCRIPTIVE / NOT_ALPHA_EVIDENCE**.

The 19:00 scheduled backup actually fired but failed because the owned service
had stopped. Its failure is preserved. A prior 14:40 empty intraday response
caused v2 normalization to generate future SourceGaps, which Market correctly
rejected; a later pre-task recovery exceeded the unchanged 120-second tick budget.
The new prospective v3 normalizer bounds gaps by request time, retaining v2 and
all failed Runs. Operational recovery and the final installation/cutoff are
recorded separately; this first Evaluation does not itself prove current uptime.

The checked-out read-only `daily observations` command consumes canonical
Prediction/Outcome/Evaluation and enforces full roster equality. Scheduled backup
templates retain immutable complete day-ledger snapshots, verify completed
publication inputs across later dates, and require a subsequent current-profile
tick for restart proof. Three-day sustained evidence remains independent and
time-blocked. No Model, Factor, Target, risk, schema or qualification is changed.

## Prior repository hygiene evidence

The source-bound cleanup completed default and explicit historical PostgreSQL
regression, static checks, archive integrity and independent installed-schema/CLI
verification. Exact revisions, counts, failures and build identities are retained
in the [archive index](../archive/README.md). Future changes must run their own
affected checks; this record does not establish current operational health.

## Evidence limits

Code presence, canonical wiring, executed tests, runtime observation, research
qualification and Production admission remain distinct. Historical passing
counts cannot establish this revision's PASS. Unproved formal Provider/PIT/OOS,
model value, sustained service and Alpha are not promoted by this cleanup.
Production admission remains closed. New business work follows the
[Roadmap](Roadmap.md), not archived task instructions.
