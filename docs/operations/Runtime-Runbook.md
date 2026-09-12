# Runtime operations

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `src/market_regime_alpha/interfaces/cli`, `src/market_regime_alpha/interfaces/prospective_service.py`, `src/market_regime_alpha/interfaces/prospective_operation_guard.py`, `src/market_regime_alpha/interfaces/daily_service.py`, `docs/operations/templates`

An independently authorized historical study starts with `mra research
prepare-historical --plan "$FROZEN_STUDY_PLAN" --wheel "$PINNED_WHEEL"
--lockfile "$PINNED_LOCKFILE" --source-checkout "$SOURCE_CHECKOUT"
--code-sha "$IMPLEMENTATION_SHA"
--output "$PERSISTENT_STUDY_DIRECTORY" --expected-database-name
"$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID"
--actor-id "$RESEARCH_OPERATOR"`. The plan pins Archive/seal/template hashes,
the complete fixed security roster and explicit FIT/purge/embargo/validation
Calendar dates. The executing package must match the wheel. Preparation checks
all Calendar sessions (including stride gaps and the
immediate final next-session label) resolve to the selected Archive's captured
normalization bindings before its seal cutoff. Another Archive's calendar cannot
substitute; a shared canonical session is valid when both Archives bind it.
It then writes immutable study metadata and predeclares a canonical Backtest;
it does not execute one.
Use the returned `mra backtest run --run-id` and `mra backtest resume --run-id`
entries for execution and recovery, then the existing report and replay commands.
Use persistent research storage, with a separate disposable test database.
The static roster is a Selection declaration, not dated Market membership.
It requires the Provider's Instrument capability and the exact sealed Archive
instrument bindings; classification capability is required only for classified
universes. Static members keep missing membership evidence and remain barred
from ordinary/prospective Selection.
It is marked `STATIC_RESEARCH_ROSTER` / `SURVIVORSHIP_LIMITED_V1`; ordinary
Eligibility and Dataset paths reject its retrospective scope. The registered
`static_research_universe_v9` upgrade adds deferred constraints; use the exact
research database backup and `db upgrade-plan`/`db upgrade-apply` before running
this package against an existing v8 research database. Never upgrade the operating
scope under historical research authorization.

Use `backtest run` or `resume` with `--maximum-actions 20 --maximum-seconds 300`
for bounded invocations. Actions finish their existing atomic owner work before
draining; the response retains the complete pending action roster, stop reason,
action time and reconciliation time. Limits are positive (at most 100,000 actions
and 7,200 seconds); omitted companion limits default to 100,000 / 3,600.
Omitting both flags preserves the original response and execution behavior.
Resume reloads the original frozen specification and rechecks owner evidence;
terminal failures require a new declaration, while completed actions are reused.
Empty populations retain zero rows and exact Calendar lineage in the versioned
empty Dataset manifest; they are never filled with synthetic observations.
This finite baseline entry is exploratory; it does not confer PIT or formal OOS.

The same `prepare-historical` entry also accepts `mra-historical-rolling-v2`.
Its nested `mra-rolling-study-v2` baseline fixes the ordered controls `zero`,
`training_mean`, `training_median`, `ridge_v2`; `ridge_candidates` adds explicit
ordered feature subsets and decimal-string alpha values within ten total arms.
`mode` is `ROLLING` (fixed FIT length) or `EXPANDING` (exact retained prefix).
`step_sessions` counts actual archived Calendar positions between validation
starts. Each split declares FIT, purge, embargo and validation dates; validation
must not repeat, and later FIT cutoffs must advance beyond earlier validation.
The explicit `update_policy` is
`MATURE_EARLIER_VALIDATION_ALLOWED_PROTECTED_LABELS_REQUIRE_OWNER_PERMISSION_V1`.
This permits mature earlier rolling observations, not reserved holdout access.
FIT is bounded to 2–252 sessions, validation to 1–250, and the plan to twelve folds.
These are engineering bounds; the retained holdout owner separately limits its
FIT to 250 and validation to 60 sessions. Use the narrower common range for a
campaign with a holdout. No existing reservation is changed or released.

For this version, `mra-robustness-campaign-boundary-v2` freezes independent
`COMMON_VALIDATION_MAE` and `DAILY_RANK_IC` objectives and declares
`EXPLORATORY_TIME_ISOLATION_NOT_BLIND_PIT`. The existing holdout reserve/select/
open and original-plan run/resume commands remain the execution path. Constants
use the exact archived listing-fact intercept, so unavailable price features do
not remove their otherwise eligible predictions. Their Rank IC remains
NOT_ESTIMABLE. Listing ambiguity, unbound Calendar or unreadable source bytes
still fail closed; the intercept is not historical membership evidence.

Parser reuse is local and bounded: eight exact byte strings, each at most two
MiB, plus their immutable parsed values. Keys also bind the complete Dataset and
Feature definitions (including code/config/formula/cutoff). Larger inputs are
parsed without retention; changed bytes/contracts miss and the least recently
used entry is evicted. No physical integrity, identity, permission, fence,
freshness or observed business state is cached. Owner reload and physical
verification precede parsing. The executor similarly retains only one immutable
graph; observations are reloaded, with complete reconciliation at dependency
boundaries and normal drain. Retained failures and unknown outcomes remain
owner facts.

The original `prepare-historical` entry accepts `mra-historical-matrix-v1`: a nested
baseline plan, explicit `additional_splits`, `step_sessions` from the archived
Calendar, and `ridge_candidates` containing a unique name, ordered factor names
and a decimal-string `ridge_alpha` (`0.1`, `1`, or `10`). It retains all seven
controls and allows at most twenty configurations and six separated rolling
periods. Each period has the same FIT/validation lengths, fresh planned model
versions and explicit maturity purge/embargo. Overlapping periods are rejected
before declarations by this bounded builder. They are not implicitly repaired.
The emitted Backtest input-v2 freezes exact Model feature subsets. Input-v1 and
historical specifications keep their full ordered feature-roster semantics.
Existing research databases use `backtest_model_subsets_v11` with an exact
research backup; this migration changes no historical business rows. Matrix
validation is exploratory and does not by itself provide a protected holdout.

`mra research history-compare --run-id "$RUN_ID" --expected-database-name
"$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID"`
projects exact completed fold Evaluation inputs and their original Outcome
revisions. It reconciles the Backtest, retains full/own/common populations and
every excluded day/name, and reports errors, daily Rank IC, distributions,
fold/month slices, paired differences and security error concentration. Constant
prediction ranks are NOT_ESTIMABLE. The five-session, 1,000-draw paired bootstrap
requires ten effective blocks and owner-verified contiguous Calendar windows;
otherwise the report is descriptive. Empty completed populations remain visible.
`--publish --actor-id "$RESEARCH_OPERATOR"` stores deterministic JSON through the
original Artifact owner with a content-bound idempotency key. This projection
does not create new Outcome labels, Evaluation metrics or model qualification.

The registered `backtest_exploratory_holdout_v12` upgrade adds two append-only
Backtest facts: a reservation and one opening. Use an exact research backup and
the existing upgrade plan/apply commands. Drain an older installed executor
before the upgrade; its original frozen specification and completed facts remain
unchanged. A maximum-seconds budget stops new actions, but the final complete
owner reconciliation can extend wall time. Include that drain in the run budget.

Before reading heldout results, freeze a `mra-historical-campaign-boundary-v1`
Artifact containing the entire development matrix, explicit heldout FIT/purge/
embargo/validation Calendar dates, future study code and finite selection rule.
The current contract retains seven controls plus one expanded Ridge candidate,
selected by all-arm-common validation MAE with ties broken by declared ordinal.
Use this sequence with the same exact database name/OID flags as above:

```bash
mra research holdout-reserve --development-run-id "$DEVELOPMENT_RUN" --protocol "$FROZEN_BOUNDARY" --expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID" --actor-id "$RESEARCH_OPERATOR" --idempotency-key "$RESERVATION_KEY"
mra research holdout-select --reservation-id "$RESERVATION_ID" --output-plan "$SELECTED_PLAN" --expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID"
mra research prepare-historical --plan "$SELECTED_PLAN" --reuse-contracts-from "$DEVELOPMENT_RUN" --wheel "$PINNED_WHEEL" --lockfile "$PINNED_LOCKFILE" --source-checkout "$SOURCE_CHECKOUT" --code-sha "$IMPLEMENTATION_SHA" --output "$HELDOUT_DIRECTORY" --expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID" --actor-id "$RESEARCH_OPERATOR"
mra research holdout-open --reservation-id "$RESERVATION_ID" --expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID" --actor-id "$RESEARCH_OPERATOR" --idempotency-key "$OPENING_KEY"
mra backtest run --run-id "$HELDOUT_RUN" --maximum-actions 100 --maximum-seconds 600
mra research holdout-inspect --reservation-id "$RESERVATION_ID" --expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid "$RESEARCH_DATABASE_OID"
```

Selection requires every original development Evaluation to be completed.
Preparation reuses exact Target, ordered Feature definitions, Candidate,
Eligibility, rule strategy and Evaluation protocols; new FIT data produce new
ModelVersions with the selected algorithm/parameters. Opening checks every
effective arm policy and cost, original Calendar bounds, complete Evaluation
input/metric identities, and the exact planned Evaluation/Partition/Experiment
mapping. Reserved runs expose all pending actions but execute none before opening.
Protocol and selection bytes are checked at execution admission and before
Outcome source reads; corrupted bytes block execution. Existing Partition access
facts record actual access. A new Run, Target or Partition cannot relabel the
reserved economic window as unused. The current protected labels cannot become
FIT inputs; a later research design needs a separately declared access contract.
Raw historical bars were already acquired and visible, so this protection is
exploratory temporal evidence, never formal blindness, LOCKED_OOS or PIT.

## Professional daily data recording contract

`mra research provider-recording-check --contract "$SOURCE_CONTRACT" --recording
"$RECORDED_RESPONSE" --expected-sha256 "$RECORDING_SHA256"
--expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid
"$RESEARCH_DATABASE_OID"` validates a bounded local recording without SDK access.
Add `--capture-product-id "$PROVIDER_PRODUCT_ID" --capture-key "$CAPTURE_KEY"`
only to store it through the original Market Capture owner in the authorized
research database. The request resource binds both the semantic contract hash
and the exact raw recording hash. Capture time comes from the existing database
clock; historical session dates never become source availability times.
The Capture Artifact uses envelope v2, containing the complete contract,
base64 of the exact original recording bytes and their original SHA-256,
plus the non-sensitive CaptureRequest identity. Replay reconstructs that
request hash and compares it with the original Capture owner. Envelope v1
remains decodable with LEGACY_UNVERIFIED request identity; it cannot satisfy
the exact owner replay check.
`mra research provider-recording-replay --capture-id "$CAPTURE_ID"
--expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid
"$RESEARCH_DATABASE_OID"` reloads the Capture owner, verifies its physical
Artifact, and recovers the same contract and raw-byte identity without writes.
The local request budget applies to one adapter invocation; its check/decrement
is synchronized. Canonical Capture idempotency remains responsible for repeated
requests. This does not implement a paid SDK download budget across restarts.

The version-1 contract requires exact SDK version, sorted stock codes, inclusive
date bounds, distinct dividend mode, evidenced volume units and timestamp
meaning, a semantic-evidence hash, and row/byte/request budgets. Currency is
CNY, prices are CNY per share, timezone is Asia/Shanghai, and `fill_data` must
be false. Recordings retain `time`, OHLC, volume, amount, preClose, suspendFlag
and a revision token. Duplicate/conflicting keys, nonfinite values, numeric
loss, unknown suspension flags and timestamp/date disagreement are rejected.
Suspended zero bars remain explicitly suspended. Calendar completeness, event
interval mapping, adjustment equivalence, membership history, publication
availability and finality still require their original owners and real evidence.

XtQuant documents separate `none`, `front`, `back`, `front_ratio` and
`back_ratio` modes, and a `fill_data` argument. They must not be collapsed into
BaoStock adjustment semantics or silently filled observations. Its suspension
flags distinguish normal, suspended and resumed observations.
See the [official xtdata API](https://dict.thinktrader.net/nativeApi/xtdata.html).
This package calls no paid service and imports no XtQuant SDK. Recordings marked
`LOCAL_PROTOCOL_SUBSTITUTE` prove the local contract only; real professional
Provider verification remains NOT_RUN. Permissions, history depth, latency,
fees and permitted data uses require future live verification.

For source comparisons, freeze a separate protocol and retain both sealed
archives. Reuse `history-inventory` for Calendar/Instrument/gap rosters, then
canonical Dataset manifests/cells, frozen Model inference, Outcome revisions
and reconciled Evaluation/Backtest reports in that order. Match exact security,
session, units, price basis and Target at each layer; mismatches block attribution
and missing benchmark observations remain missing. Do not compare only headline
metrics from runs that changed their populations or Targets.

| Experiment | Frozen controls | Deliberate change |
|---|---|---|
| Fixed model, changed data | Exact ModelVersion/preprocessing, ordered Features, Target, population and dates | Source facts/revisions and their downstream values |
| Fixed algorithm, retrained data | Algorithm/version/parameters, training and evaluation protocol, Target and population | Source plus fresh per-fold TrainingRun/ModelVersion |
| Fixed new data, changed models | Exact sealed Archive, Dataset protocol, Target, split and common population | Predeclared finite model/feature matrix |

Persist every layer's identities, exclusions and access record with the source
protocol. A source adjustment mismatch requires an explicit verified mapping or
NOT_ESTIMABLE. The recorded adapter is not a normalization implementation or
evidence that a professional source supports the historical campaign end to end.

This runbook describes available commands and safety boundaries, not a deployed
service's current state. Use only the explicitly authorized project/database/
user-job scope. Never stop an unknown process, substitute a restored writer, or
reopen a terminal failed Run. Repository maintenance does not authorize deployment.

## Historical data acquisition

`mra research prepare-history-data` accepts the same isolated database, build,
output and operator flags as `prepare-historical`. Its `mra-historical-acquisition-v1`
plan freezes `archive_code`, exact `template_archive_id` / `template_archive_sha256`,
`start_date`, `end_date` and sorted BaoStock `codes` already observed in that archive.
It declares a separate ProviderProduct with explicit raw and backward-adjusted
capabilities and starts the original MarketArchive owner. It does not download data.

The request roster is Calendar, one security master per name, then daily raw and
daily backward-adjusted history per name. It is capped at 66 names / 199 requests,
six years, 32 MiB per response and 512 MiB total, with a 1 GiB free-space reserve
by default. Dates must end before the actual UTC day. Current membership is never
rewritten as historical membership. BaoStock remains an auxiliary exploratory
source; paid-source permissions or PIT are not inferred.

The `historical_archive_inventory_v10` registered upgrade adds `MIXED_EXPLICIT`
only to retrospective archive inventories. Every Market bar and SourceGap retains
its own exact price basis; prospective archives and individual prices cannot use
this token. Raw Target labels and adjusted cross-day Feature dependencies can
therefore share an exact sealed capture roster without relabeling either.
Backward adjustment is BaoStock's documented percentage-change convention, not
a distribution-reinvestment or executable return contract; see the publisher's
[adjustment specification](https://www.baostock.com/helpdocs/pdf/BaoStock%E5%A4%8D%E6%9D%83%E5%9B%A0%E5%AD%90%E7%AE%80%E4%BB%8B.pdf).
Actual capture/known times and unknown availability/finality are preserved.

After the request roster reaches its intended terminal disposition, use
`mra archive seal --archive-id "$ARCHIVE_ID" --expected-database-name
"$RESEARCH_DATABASE_NAME" --actor-id "$RESEARCH_OPERATOR" --operation-key
"$STABLE_SEAL_KEY" --disposition COMPLETE`. The original Archive owner checks
the disposition; use `PARTIAL_WITH_GAPS` or `PARTIAL_WITH_RESOURCE_LIMIT` only
when that owner-recorded condition applies. Sealing does not assert bar quality.

`mra research history-inventory --archive-id "$ARCHIVE_ID" --seal-id "$SEAL_ID"
--expected-database-name "$RESEARCH_DATABASE_NAME" --expected-database-oid
"$RESEARCH_DATABASE_OID"` verifies the frozen roster and Capture bytes, then
reports Calendar coverage, each security × session × price basis denominator,
missing/conflicting identities, listing facts, status summaries and revision
roster hashes. Request-level Provider failures are attributed to every observed
session in their exact original request's security, price basis and inclusive
date range, preserving the original gap identity. This inventory scope is not
limited to the Feature kernel's 21 sessions; success and failure together remain
visible as conflicting evidence. Save stdout in persistent research storage. Missing security
master captures do not remove frozen names from the denominator. The v2 inventory
hashes sorted UUID bytes for immutable revision rosters; Capture and code/config
hashes retain source/normalization identity. A counted bar is not necessarily a
usable Feature, mature label or formal PIT observation.

The historical Feature family has ten version-1 formulas, all unitless ratios:

| Factor | Formula and complete-session dependency |
|---|---|
| intraday | Raw close / raw open − 1, current session |
| return_1 / return_5 / return_20 | Backward-adjusted close / close N sessions earlier − 1; all N+1 Calendar sessions must have prices |
| volatility_20 | Sample standard deviation of 20 adjusted daily returns, divisor 19; 21 closes |
| volume_5_20 / amount_5_20 | Mean last 5 / mean last 20 − 1; raw shares / CNY amounts respectively |
| peer_relative_5 / peer_relative_20 | Return minus equal-weight return of exact Dataset members with complete windows, at least two |
| cross_section_5 | (Average tie rank of return_5 − 1) / (complete member count − 1), at least two |

Peer arithmetic uses unrounded returns; final cells use Decimal precision 60,
half-even rounding to 12 decimal places. The peer benchmark is not CSI300 or a
tradable portfolio. Peer exclusions remain visible in the full Dataset. Windows
use Market Calendar; participating exchanges must have aligned dates/closes.
There is no weekday inference, raw-price fallback, zero-denominator replacement,
forward fill or label input. Warmup/missing data are MISSING, explicit conflicts
are CONFLICT, and failed Provider requests are UNKNOWN. Failed-request lineage
retains slice/Capture/request hashes and real knowledge times, with no invented
event time; it may explain unavailable cells but cannot support numeric values.

The shared pure kernel accepts the last 21 sessions or a bounded incremental
append. Backtest prepares exact population batches outside the owner transaction,
verifies bytes after releasing the read connection, and uses no cross-invocation
Authority cache. Dataset commit reloads full Calendar/bar/gap lineage. Existing
daily and intraday formulas retain their original adapters and identities.

Run the returned `archive-manifest.json` through `mra archive resume --manifest
"$FROZEN_ARCHIVE_MANIFEST" --expected-database-name "$RESEARCH_DATABASE_NAME"
--actor-id "$RESEARCH_OPERATOR" --operation-key "$STABLE_OPERATION_KEY"
--maximum-slices 8 --maximum-seconds 1200`. Bounded mode discovers pending DUE/OVERDUE
slices, admits no more than 200 slices / 7,200 seconds, spaces slices by at least
0.25 seconds, drains the current owner operation and returns full Archive
inspection with elapsed time. The Provider has a 30-second response deadline and
at most two transport attempts. New mixed inventories apply these defaults even without budget flags. Reuse
the frozen manifest and operation key on restart; captured/terminal slices are not downloaded again. Terminal gaps and
resource stops remain evidence and require a new declared archive for correction.
The existing seal, revision/gap report and replay owners remain authoritative.

## Daily reliability operations

Use the installed `mra` belonging to the exact approved profile. The existing
`archive prospective serve --daily-plan-template ...` wires daily prediction,
Outcome recovery and notification discovery into its one serial Runtime loop.
Daily and prospective work alternate first access to the unchanged tick time
budget. Daily Prediction/Outcome step budgets and per-phase elapsed times are
reported separately. Health query failures report HEALTH_QUERY_FAILED and do
not erase completed business results; guard failures stop further writes.

These read-only entries locate complete Runtime denominators, original plans,
cross-Use work and the first same-model evidence condition:

```bash
mra research daily backlog --kind outcome --page-size 64
mra research daily backlog --kind delivery --channel feishu --page-size 32
mra research daily delivery-status --plan "$ORIGINAL_PUBLISHED_PLAN" --channel feishu
mra research daily lineage --model-version-id "$FROZEN_MODEL_VERSION_ID"
mra research daily data-ready --plan "$FROZEN_DAILY_PLAN"
mra research daily report --plan "$ORIGINAL_PUBLISHED_PLAN"
mra research daily replay --plan "$ORIGINAL_PUBLISHED_PLAN"
mra research validity daily --protocol-version 3
```

Continue an Outcome cursor with all three returned fields:
`--after-priority`, `--after-requested-at`, `--after-run-id`. Delivery cursors
use only the latter two. Cursors are opaque scan positions; no saved cursor
grants permission or hides the complete counts. Delivery history includes old
SUCCEEDED Runs whose legacy local receipt may remain unverified. A separate
newest-work probe reserves an opportunity for a currently valid report.

Default daily health renders the most recent 128 publication/abstention roots
and their Outcome children. It always reports complete Runtime counts and marks
truncated scope details PARTIAL_DETAIL. Use the backlog cursor for recovery
and `observations` for an explicit full-history research export; a partial health
view is not the research denominator. Unattributable corrupt history is reported
separately and blocks a full-cohort validity claim.

The original calendar owner can refresh without running a prediction:

```bash
mra research daily refresh-calendar --plan "$FROZEN_DAILY_PLAN" --operation-config "$OPERATION_PROFILE"
mra research daily collect-outcome --plan "$ORIGINAL_PUBLISHED_PLAN" --operation-config "$OPERATION_PROFILE" --maximum-steps 16
mra research daily settle --plan "$ORIGINAL_PUBLISHED_PLAN" --operation-config "$OPERATION_PROFILE" --maximum-steps 16
mra research daily deliver --plan "$ORIGINAL_PUBLISHED_PLAN" --operation-config "$OPERATION_PROFILE" --channel feishu
```

Calendar refresh and collection perform Provider I/O and owner writes;
settlement writes through Outcome/Evaluation owners, and delivery sends an
external request. All require authorization for that actual operational scope.
Late Outcome collection retains its actual acquisition time. It cannot alter
the original Prediction, source revision, Use lifetime or protocol. The automatic
eight-hour Outcome collection grace remains unchanged; later collection uses the
explicit original-plan command. Terminal failures require an existing explicit
successor contract; UNKNOWN external effects are inspected without blind retry.

Notification content and request identity bind the exact published report.
New business expiry is the Prediction Target start, checked again immediately
before sending. Old frozen expiry bytes remain unchanged, but sending still
obeys the earlier Target boundary. Feishu webhook success means remote
ACCEPTED, with final delivery UNKNOWN and no remote message identity supplied
by the [documented webhook ACK](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot).
New v2 local evidence binds report/request/attempt/response
hashes and actual time; ACK Artifact, receipt, audit and completion share the
original transaction. A lost commit acknowledgement is recovered by reading
that completion. Old local-hash delivery claims remain
LEGACY_DELIVERY_CLAIM_UNVERIFIED. True delivery requires independent channel
evidence and cannot be inferred from Runtime SUCCEEDED.

To inspect operational reachability, supply measured scenario durations:

```bash
mra research validity daily --protocol-version 3 --collection-budget-seconds "$COLLECTION_SECONDS" --backup-budget-seconds "$BACKUP_SECONDS" --publication-budget-seconds "$PUBLICATION_SECONDS"
```

Each budget is a positive finite number of seconds; omission means
NOT_ESTIMABLE. The publication window starts after the captured previous close,
the observation time and the original Model-use's effective time; missing owner
time is NOT_ESTIMABLE. This read-only scenario excludes windows that cannot fit
the budget and applies the existing frozen sample floors and buffers to the
remaining capacity. READY is scenario feasibility, never promised future
observations. EXPECTED_INSUFFICIENT and NOT_ESTIMABLE remain distinct. A
successor must be a separately authorized future owner registration and protocol;
no command extends an existing Use or joins cohorts.

For an authorized restore drill, provision an empty disposable PostgreSQL 16
database separately. Bind its name/OID/cluster and a new Artifact root in private
configuration, then use the exact dump SHA from the source backup receipt:

```bash
mra evidence fresh-restore --disposable --bundle "$VERIFIED_BACKUP_BUNDLE" --expected-database-name "$DISPOSABLE_DATABASE_NAME" --expected-database-oid "$DISPOSABLE_DATABASE_OID" --expected-cluster-identity "$DISPOSABLE_CLUSTER_ID" --expected-backup-sha256 "$PINNED_BACKUP_SHA256"
mra evidence restore-check --bundle "$VERIFIED_BACKUP_BUNDLE"
```

Fresh restore rejects the source database/root, existing target relations or
custom namespaces, competing connections and wrong dump/scope identities. It
holds the existing exclusive writer reservation during actual
`pg_restore --single-transaction` and Artifact copy. Verification checks the
installed schema, exact table hashes, complete physical roster and owner report
replay, including published empty results. Pending/failed histories remain
preserved with completion replay NOT_RUN; integrity PASS is not completion.
Failures preserve the disposable target for diagnosis and never make it a writer.
The original backup refresh/drain/profile/restart flow below remains the
operational deployment entry; this drill does not activate or restart it.

## Preflight and inspection

Keep `MRA_DATABASE_URL`, `MRA_ARTIFACT_ROOT`, Provider credentials and the operation
profile in private local configuration. `bootstrap.TargetSettings` rejects
unknown MRA keys and requires the exact schema epoch. The profile binds database
name/OID/cluster, source, Target, Artifact root, code/config, backup receipt and
budgets. Do not paste secret-bearing environment or connection strings in logs.

Discover required flags from the installed frozen artifact:

```bash
uv run mra db verify
uv run mra archive prospective status --help
uv run mra archive prospective health --help
uv run mra archive prospective preflight --help
uv run mra evidence inventory
uv run mra evidence diagnose --help
uv run mra backtest progress --help
```

Status/diagnostics require explicit scope arguments. Inspect PostgreSQL time,
exact TradingSessions, generations, due/future/overdue slices, Attempts and
planning gaps. A Run marked RUNNING is not proof of a worker, and process
liveness is not a successful capture. `backtest progress` is a Runtime projection;
use inspect/replay to verify the complete owner graph.

## Authorized service lifecycle

Deployment uses a wheel installed with locked dependencies outside the checkout.
An editable install or a hand-edited source hash cannot activate the service.
Preserve the old wheel, profile, receipt and logs. From the new installed `mra`,
prepare a new profile without changing operational facts:

The previous service must first drain and release its reservation under explicit
operational authorization. Preparation does not stop it and refuses a competing
supervisor or active Attempt. Keep the former installation disabled after the
handoff; a failed preparation is not permission for a fallback writer.

```bash
mra runtime prepare-deployment --operation-config "$PREVIOUS_OPERATION_PROFILE" --wheel "$FROZEN_WHEEL" --source-checkout "$CLEAN_SOURCE_CHECKOUT" --expected-source-sha "$IMPLEMENTATION_SHA" --backup-directory "$VERIFIED_BACKUP_BUNDLE" --output "$NEW_OPERATION_PROFILE"
```

Preparation authenticates the complete installed package, metadata and dependency
rosters against the wheel and clean source/lock. It verifies the explicit original
DB, schema/catalog, Artifact bytes, Target/series, calendar and backup under the
existing reservation, refusing active Attempts. Output is exclusive private local
intent and a verification receipt, not business Authority or writer activation.
Version 1 profiles remain readable as migration intent; current service execution
requires the verified version 2 handoff. A restored database fails exact identity.

The handoff receipt also binds the authenticated PostgreSQL login name/OID.
Preparation and every action reject superuser, database/schema creation,
formal qualification or Model registration privileges, missing Runtime/Artifact
write permissions, the ProviderProduct reference-lock permission, and `SET ROLE` impersonation. Use a dedicated project login;
do not change a cluster-wide operator account used by other databases. Grant
only the owner tables required by the deployed research operations, without
DELETE, TRUNCATE or DDL. PostgreSQL row-lock reads need UPDATE privilege on
at least one column: grant only the identity column for immutable reference
tables and retain their append-only triggers. Verify the complete capture and
normalization path under that role in a disposable scope. Read-only diagnostics and backup credentials remain
separate. Restrict authentication for the exact operational database so old
login identities cannot bypass cooperative advisory admission. Record and test
the database-specific authentication rules, role grants and rollback procedure
before activation; OS/cluster administrators retain explicit maintenance power.
An old receipt without an authenticated principal requires a new preparation.

After separately authorized drain and handoff, configure only the owned supervisor
with the installed `mra` and generated profile. Preflight rechecks the receipt,
wheel and actual installation. Backup refresh may renew only the three backup
identity fields after verification; scope, budgets and implementation changes
require another verified deployment preparation.

The service verifies complete installed package, wheel and receipt content at
startup. Every owned Python bytecode cache must have a supported magic/header,
cache tag and optimization level, an exact current source file, and a code object
equivalent to compiling that verified source. Timestamp or source-hash headers
alone do not prove bytecode integrity. External bytecode-cache lookup is rejected.
The process disables bytecode writes before verification; later imports may read
only verified caches or compile the verified source without creating a cache.
Each action re-enumerates all owned source/resources and bytecode caches,
distribution metadata, wheel and receipt and compares OS file identity, size,
mode, owner, inode, mtime and ctime. A changed resource roster or identity rejects
the action, including any new or changed cache or a changed bytecode policy; a new
process must perform full verification again. This assumes the
existing trusted OS/interpreter boundary and does not cache mutable business
state, database permissions, leases or fences. Runtime login privileges and the
database scope remain live checks. A backup-only profile renewal starts a fresh
verified guard under the same supervisor reservation; it cannot reuse the old
guard's pinned configuration.

Preflight and tick JSON include `stage_timings`. `before_action_guard` is an
inclusive child of owner work and must not be added to its parent's elapsed time.
`PROSPECTIVE_STAGE_FAILURE` records the phase, elapsed time and exception type
before the ordinary failure path exits. It neither retries nor masks the error.
The tick hard stop remains 120 seconds. Operational observation targets are:

| Work class | Observation target | Boundary |
|---|---|---|
| Cold startup/preflight | Explain package, ACL, Artifact and backup verification separately | Outside tick; full verification required |
| Warm idle | p95 below 60 seconds; ordinary maximum below 90 | 120-second hard stop |
| Prediction | Framework overhead separately from actual Provider, normalization and owner work | 120-second hard stop; frozen work continues through Runtime |
| Outcome/Evaluation | Actual acquisition, normalization, settlement and report stages separately | 120-second hard stop; no terminal reopening |
| Backup/restart | Record drain, snapshot, verify, mirror, preflight and subsequent tick duration | One owned restart; failure requires reconciliation |

These targets are observations to verify, not timeout increases or claims of
long-term stability. Missing workload measurements remain `NOT_OBSERVED`.

Scheduled backup invokes the existing helper with `--scheduled`. Classification
requires the current owned backup LaunchAgent PID and an actual observation within
five minutes from 03:00 or 19:00 Asia/Shanghai. The evidence class is
`OWNED_JOB_AND_SCHEDULE_WINDOW`: an operator kick inside that window cannot be
distinguished from launchd's calendar fire by PID inspection. An out-of-window
kick cannot become a scheduled receipt. Old receipts lacking this provenance stay
unclassified; separate historical scheduled-fire evidence retains its meaning.

A process crash, QueryCanceled or resource stop fails closed. There is no automatic
process restart loop or Runtime retry. An explicit `--recover-stopped` invocation
records the prior stopped-service fact, reloads current Attempts and fences, and
requires owner reconciliation of every active, expired or unknown effect. It
preserves terminal failures and makes at most one restart request after five
seconds of backoff. This manual receipt cannot become a scheduled success.

Restart proof requires the physical subsequent-tick and restart-observation files,
their exact hashes, the refreshed profile and backup receipt identities, monotonic
observation times, and matching owned PID, UID, start time and command hash across
fresh process checks. The observed tick must remain within the unchanged
120-second budget. Missing or changed proof cannot count as a completed scheduled
backup. If proof fails, recovery drains only the process identity it actually
observed. A disabled service is never revived.

The existing health entry accepts the optional private receipt directory:

```bash
uv run mra research daily health --series-code "$MRA_SERIES_CODE" --replay --backup-receipts-directory "$MRA_BACKUP_RECEIPTS"
```

Its `SCHEDULED_BACKUP_RELIABILITY` retains every observed fire, failure reason,
duration, restart verification and explicit denominator. Same-host redundancy
does not provide offsite disaster recovery.

Calendar continuity is a bounded child of the existing service. It uses actual
Provider civil-date responses, immutable Capture bytes and Market normalization,
and refreshes after seven days or when the known horizon is too short. Requests
span at most 120 civil dates and are clipped to the current ModelUse expiry.
Civil dates bound a request; only explicit Provider open flags create sessions.
Missing response dates become typed SourceGap, never inferred holidays. Each
request has one frozen two-step Runtime with a single permitted Provider effect;
duplicate work replays, terminal work stays terminal, and unresolved work blocks
replacement across date boundaries.

Validity reports reload the exact protocol's ModelUse even when its cohort has
no completed observations. Capacity distinguishes known calendar limits from
ModelUse lifetime limits and shows both a possible upper bound and the frozen
downtime/missingness buffer scenario. A capacity PASS is not a promise of future
data. Old and new Use populations remain separate formal cohorts; operational
day counts may span their reconciled sessions. Same-window old frozen work is
preserved through rollover, and only an unrepresented new window uses the new
authorization. Protocol bytes, research minima and financial semantics do not
change in place.

```bash
uv run mra archive prospective preflight --operation-config "$MRA_OPERATION_CONFIG"
uv run mra archive prospective serve --help
```

Pass the validated profile and the frozen manifest/series/code arguments shown by
the installed `serve --help`. Serve is the sole guarded prospective write entry;
the parser's historical unguarded verbs deliberately reject execution.

The service re-enters the existing composition per wakeup, checks shared atomic
writer admission before owner actions, executes bounded work and emits structured
health. Provider timeout/response/call and disk/backup/connection budgets come
from the profile. Lost supervision, identity drift, exhausted budget or expired
backup stops new work. Signals request a graceful drain; they do not acquire a
non-reentrant wait lock or discard committed facts.

Only an explicitly owned supervisor may launch the frozen artifact. The
supervisor owns process lifecycle, not business due time. Keep automatic fault
restart bounded. Preserve the deployed artifact/profile identity while work is
in flight; never edit the source used by a running process.

When an already authorized current-user LaunchAgent is installed, exact-scope
commands are:

```bash
launchctl print "$MRA_USER_DOMAIN/$MRA_SERVICE_LABEL"
launchctl kill SIGTERM "$MRA_USER_DOMAIN/$MRA_SERVICE_LABEL"
launchctl bootout "$MRA_USER_DOMAIN" "$MRA_SERVICE_PLIST"
launchctl bootstrap "$MRA_USER_DOMAIN" "$MRA_SERVICE_PLIST"
```

These variables must come from the owned deployment record; do not guess a PID
or label. Install/restart requires its own authorization. A bounded
stop/restart drill is not sustained-service evidence.

## Daily research and recovery

```bash
uv run mra research daily --help
uv run mra research daily data-ready --help
uv run mra research daily freeze-plan --help
uv run mra research daily predict --help
uv run mra research daily settle --help
uv run mra research daily status --help
uv run mra research daily report --help
uv run mra research daily replay --help
uv run mra research daily revoke-model --help
```

The daily consumer runs sequentially under the same reservation. Use exact frozen
plan and Model-use identities. DataReady is a complete population/time check;
login or the newest bar is insufficient. Publication after cutoff abstains.
Future labels remain pending. Old Outcome Runs recover their own immutable
plan across Model-use changes, and unknown external delivery effects require
reconciliation rather than blind resend.

Missed windows retain explicit terminal/planning-gap facts. Recovery uses the
existing Runtime lease/fence contract; it does not backdate creation or timely
capture. `runtime recover` and daily/prospective status reveal blockers before
canonical resume. Terminal failure may need an explicitly declared successor;
never manually reset it.

## Backtest and evidence

Runtime recovery requires exact `--run-id` and `--actor-id`, never a whole-database
CLI sweep. During reservation use the owning daily/prospective recovery path;
Runtime validates the lease, fence and exact handoff. Retained account/governance
write connections participate in the same atomic admission. Explicit read-only
historical inspection remains available. Arbitrary SQL from external clients is
outside this cooperative contract and must be excluded by deployment permissions
and single-writer preflight.

Canonical commands without an Attempt also reserve their narrow write connection.
After supervisor connection loss, the abandoned service cannot issue further
commands, including completion. Runtime inspection remains database read-only;
already committed facts remain intact. Exit that session and reconcile the
original Attempt/fence or its expired-lease recovery before continuing. Never
infer that an external effect did not happen from the missing completion reply.

Pending Outcome work reloads its original plan across later Model-use changes.
An upgraded installation may settle that work or resume an already frozen
prediction; it cannot create new prediction work with a different code identity.
Revocation stops new inference without relabeling old publications. `daily report`
and `daily replay` reconcile Evaluation/report when the Outcome Runtime completes;
otherwise they expose the pending or blocked stage.
When settlement steps already completed, report recovery reuses their canonical
Outcome facts and verifies the complete owner roster; it does not reacquire
Market data or repeat completed Evaluation.

```bash
uv run mra backtest inspect --help
uv run mra backtest resume --help
uv run mra backtest report --help
uv run mra backtest publish-report --help
uv run mra backtest compare --help
uv run mra backtest replay --help
uv run mra evidence backup-plan --help
uv run mra evidence backup --help
uv run mra evidence restore-check --help
uv run mra db upgrade-plan --help
uv run mra db upgrade-apply --help
```

Resume completed reconciled actions through their existing receipts. Report and
compare consume reconciled Evaluation, exact formula/Target/cost/partition
semantics and complete rosters. They never repair history or recalculate labels.

Backup binds the exact database snapshot to referenced Artifact bytes and an
inventory receipt. Check disk, single writer, hash/size, dump readability and
physical Artifact integrity. Restore into an explicitly fresh copy and verify
schema, owner rosters, bytes and relevant replay/report identities.

The retained executable templates
[refresh_backup.py](templates/refresh_backup.py) and
[verify_prospective_artifacts.py](templates/verify_prospective_artifacts.py)
coordinate an existing private deployment. They are versioned executable code
with tests, not current database configuration. Inspect their required private
deployment contract before use. Backup refresh must produce a verified receipt,
update the bound profile and restart the exact frozen service safely; an expired
receipt cannot be kept valid by editing its date. Missing independent physical
backup storage must be stated, not disguised as a second directory.

For the exact existing private deployment, the refresh command drains the owned
service, holds its reservation through the exported snapshot, verifies the dump
and byte roster, refreshes integrity, renews only backup bindings and restarts:

```bash
uv run --no-project --python "$INSTALLED_PYTHON" python "$PROJECT_OPERATION_DIRECTORY/refresh_backup.py"
# Explicit recovery after a stopped service; never bypass intentional disable.
uv run --no-project --python "$INSTALLED_PYTHON" python "$PROJECT_OPERATION_DIRECTORY/refresh_backup.py" --recover-stopped
launchctl disable "$MRA_USER_DOMAIN/$MRA_SERVICE_LABEL"
launchctl kill SIGTERM "$MRA_USER_DOMAIN/$MRA_SERVICE_LABEL"
```

An intentionally disabled service is not restarted by scheduled backup refresh.
Keep the existing backup job bounded with `KeepAlive=false`; a failed refresh
leaves the writer stopped for inspection. Preserve original logs and profiles.
Record the exported snapshot's table/Artifact roster separately from later
integrity metadata updates. Restore verification compares that snapshot, not an
unqualified claim that a subsequently running database is unchanged. Database
roles, host authentication and private credentials are separate deployment
controls; a no-privilege restore does not clone them.

Integrity refresh includes daily bars and TradingSession source Artifacts
referenced by the current and original pending plans as well as prospective
archive inputs. It also includes the original Runtime configuration, plan
Artifacts and all Target/metric algorithm bindings: readable market prices alone
do not establish settlement readiness. It verifies physical bytes
through Artifact commands; it never changes Capture known/recorded time, chooses
new labels, or rewrites a frozen plan. Expired verification observations and
missing/corrupt bytes are distinct failures. Any unverified member blocks restart.

When a mature pending prediction has neither an exact target bar nor SourceGap,
the service does not fabricate a missing-price label. After its automatic
collection grace expires it reports `OUTCOME_DATA_UNOBSERVED` and continues
other eligible work. An explicitly authorized operator can request bounded late
collection through the same Market/Runtime owners:

```bash
uv run mra research daily collect-outcome --plan "$ORIGINAL_PUBLISHED_PLAN" --operation-config "$MRA_OPERATION_CONFIG" --maximum-steps 16
uv run mra research daily settle --plan "$ORIGINAL_PUBLISHED_PLAN" --operation-config "$MRA_OPERATION_CONFIG"
uv run mra research daily replay --plan "$ORIGINAL_PUBLISHED_PLAN"
```

A terminal population normalization failure has one explicit recovery path:
`uv run mra research daily retry-population --collection-plan "$FAILED_COLLECTION_PLAN" --operation-config "$MRA_OPERATION_CONFIG"`.
This requires the exact original Runtime plan, a committed Capture and the known
`NORMALIZATION_BINDING_REJECTED` terminal result. Refresh the physical integrity
of the whole classification's existing Instrument sources first; the Provider's
membership population can exceed the prediction sample. The command reconciles
the original Capture through Market and creates only the next bounded observation
round. Repeated recovery uses that same successor; the failed Run stays failed.
UNKNOWN effects, unrelated failures and already published predictions refuse.

Installed handoff reloads unfinished collection contracts and published plans from
their original Runtime Artifact. Model, Target, feature and configuration bindings
stay frozen, including their original code Artifact. Only an unpublished input
cutoff advances to the database clock; a new installation cannot rewrite a
publication or silently adopt another model.


Collection requires a reconciled original publication, a naturally mature Target,
and an unstarted nonterminal settlement. Repeated commands resume the original
bounded capture round; unknown or failed effects require reconciliation. Late
observations keep their actual Capture times and never establish on-time capture
or replace the publication. Once settlement has begun, the command refuses to
reacquire Market inputs. Completed reports and evaluations stay immutable.
An elapsed capture Run with a single known terminal normalization failure may
be reconciled read-only so subsequent generations can proceed. Its FAILED state
and error remain in health; it is never reopened. Earlier unknown effects still
refuse continuity until reconciled.

The v1 prediction report keeps its original denominator fields, including
`model_prediction`; Evaluation's `predicted` label is a projection of that count,
not an additional field inserted into previously published v1 report bytes.

Keep operational observations separate: due Attempt, successful Capture,
on-time capture rate, terminal coverage, backlog/planning gaps, restart
recovery, and sustained days/windows. Failed terminal coverage is not capture
success. Logs and diagnostic query timings cannot by themselves establish a
historical timeout's root cause.

## Retired entry points and historical inspection

New research uses only the `mra` commands above. The former standalone research,
state and shadow CLIs are no longer installed; there is no argument translator
or fallback to their repositories. A frozen deployment keeps its own code and
configuration until an explicitly authorized handoff; this source change does
not restart services or resume old Runs with new semantics.

For an explicitly identified historical database, use the uninstalled read-only
inspection surface:

```bash
uv run python -m market_regime_alpha.cli.inspect_historical_runtime --help
uv run python -m market_regime_alpha.cli.inspect_historical_runtime --database-url "$HISTORICAL_DATABASE_URL" --application-schema "$HISTORICAL_SCHEMA" runtime-replay --run-id "$HISTORICAL_RUN_ID"
```

Runtime/shadow inspection verifies the existing schema, never bootstraps it.
Missing schema/identity is a rejection, not a reason to select another database.
The inventory distinguishes this zero-write surface from durable lifecycle
verification APIs that create their own replay journal. `historical_tools/`
contains fixed-protocol reproduction tools, not current service launchers.
Account/manual Fill and formal governance administration remain separately
scoped; this is not authorization for full Runtime/CLI cutover.


### Runtime database privileges and terminal publications

The authenticated runtime login needs the current owner's reference row locks,
including empty retrospective-marker checks on a non-retrospective Dataset.
`inspect_runtime_principal` checks the reference tables in
`infrastructure/postgres/runtime_privileges.py` and the daily result writers. Grant UPDATE on
an identity column for `FOR SHARE`; immutable reference triggers remain enabled.
Decision qualification rosters record consumed references; granting their owner
writes must never grant writes to qualification decisions, ModelVersion
registration or schema migrations. The restricted-login PostgreSQL vertical
contract covers prediction, mature Outcome using disposable test time, Evaluation,
unknown-commit recovery and replay. Fixtures do not establish prospective proof.

A terminal prediction is exposed as `PREDICTION_RECOVERY_REQUIRED`, without new
input reads or reexecution. Pending Outcomes from other original frozen plans
continue independently. After repairing an operational cause, an operator may
freeze a distinct current-time prediction request through the existing daily
CLI before its Target cutoff. Record the failed and new identities explicitly;
this does not reopen, replace or reclassify the failed publication, and is never
an automatic selection of a replacement model.


### Scoped health and privilege drift

`mra research daily health --series-code SERIES --cutover-at UTC_INSTANT
--recent-sessions 5 --replay` emits a read-only ledger and three simultaneous
scopes. Supply the actual activation boundary from its immutable deployment
record; changing installations does not reset the lineage's observation start.
`ALL_HISTORY` remains visible. `POST_CURRENT_CUTOVER` selects expected windows by
window start and prediction requests by original request time; inherited pending
work remains in the complete ledger. Planning gaps use detection time. Recent
windows use exact scheduled TradingSession identities whose sessions have opened,
never weekday inference. No boundary supplied means NOT_ESTIMABLE for cutover.

Serve accepts `--health-cutover-at` for the same read-only cohort projection and
scoped alert deduplication. It still reconciles the entire series and all pending
work. Logs separately expose all-history health, scoped health, daily ledger,
tick duration, and backup/resource preflight; process uptime cannot establish
capture or Evaluation success. An unchecked replay is NOT_RUN, even when its
observed mismatch count is zero. `--replay` verifies the original owner reports
without completing or reexecuting any work. Finance statistics remain canonical
Evaluation projections, with single-day evidence descriptive only.

The authenticated login is checked at preflight and before owner actions against
an explicit INSERT/UPDATE table and identity-column lock envelope. Other table
or column writes, grant options, role memberships, CREATE/TEMP, sequence writes,
and unapproved callable routines fail closed. Reference identity-column UPDATE
is only needed for PostgreSQL row locks; released invariant triggers remain
active. GC candidates require only a content-hash column lock, not insertion or
whole-table update. Schema/Model/qualification/account mutation is outside the
runtime envelope. Approved schema publishers and the trusted cluster
administrator remain outside the untrusted-client threat model; this guard does
not replace database permissions or grant authority to change them.

A resource-budget exit is a stopped service, even if its parent research Run
remains RUNNING. Inspect the exact owned job and canonical Attempts before
recovery. Preserve the exit/log prefix, verify no unknown effect, then use the
qualified profile handoff or unchanged-installation restart procedure above.
Do not increase timeout from one slow tick or let a supervisor restart forever.
New permission probes and health projections have separate measured costs;
their successful timings cannot explain an earlier uninstrumented failure.

The daily `data_freshness.last_bar_recorded_at` projection is restricted to the
frozen plan's instruments and input/target sessions, as stated by `bar_scope`.
It cannot be refreshed by unrelated securities or historical campaigns.
Capture/SourceGap freshness remains Provider-product scoped. Neither timestamp
is a DataReady, complete-population or Provider-PIT qualification assertion.

Check actual backup-refresh event receipts for scheduled fire, drain, dump,
Artifact verification, mirror, profile refresh and restart. A configured calendar
alone proves none of these. Keep the original cutover cohort boundary across
refreshes. The service's fresh backup observation and last Artifact verification
are separate from Provider availability and publication/Outcome timeliness.

A changed grant envelope requires a qualified restricted-login vertical slice,
exact owned-service drain, current verified backup, and an administrator's scoped
role adjustment. Freeze/install the implementation and prepare a new deployment
receipt before activation. Preserve prior profiles, wheels and failed Runs. Keep
backup refresh bound to the new installed interpreter; its scheduled event log
must show drain, verified dump/Artifact roster, physical mirror, profile refresh,
preflight and restart. A second physical device on this host is not offsite.

### Mature observation closure and sustained evidence

The prospective BaoStock normalizer uses a separate v3 contract: missing bar
intervals must have ended before the actual Provider request started. A 14:40
empty response cannot establish a SourceGap for 15:00. Returned Provider bars
still pass the Market owner's temporal checks. The v2 historical/daily contract
and existing normalization receipts remain unchanged; failed Runs stay terminal.

After canonical Outcome/Evaluation completion, inspect the narrow research
projection without collecting prices or calculating new labels:

```bash
uv run mra research daily observations --target-session-date 2026-09-10 --model-version-id "$ORIGINAL_MODEL_VERSION" --target-definition-id "$ORIGINAL_DAILY_TARGET"
```

Filters use canonical Target session dates and exact ModelVersion/Target IDs.
The projection reconciles the original publication and completed Evaluation,
checks commitment/Partition/acquisition roster equality, and returns the complete
population, forecasts, acquired Outcome revisions/labels/sources, canonical
metrics and explicit unavailable work. It writes no research truth. Metrics
absent from the frozen protocol, including directional accuracy for the first
daily protocol, are not calculated in a report. Single-session comparisons remain
`DESCRIPTIVE / NOT_ALPHA_EVIDENCE` regardless of their direction.

Backup refresh records immutable `day-ledger.log` snapshots through existing
`daily health --replay`, with the original cutover boundary, exact calendar
sessions, full populations, failures and source log hashes. These are observations
at a cutoff, not new day facts. A stopped-service scheduled failure also preserves
its ledger and remains failed. Successful restart requires a subsequent tick from
the exact refreshed profile within the existing tick budget. An unverified restart
receives a graceful drain request; there is no unbounded restart loop.

Integrity refresh reloads all completed publication plans as well as current and
pending work. It verifies original static/input/Target/Runtime bytes so old daily
health and replay remain available after current sessions move forward. It never
changes Capture known times, labels or the original publication. Missing or
inconsistent frozen plans fail closed before physical verification commands.

Sustained proof requires at least three consecutive naturally observed successful
trading sessions, preferably five. Until those days actually occur and close,
report `BLOCKED_BY_ELAPSED_REAL_TIME`; never create synthetic day ledgers.

### Research Validity baseline

Use the same original database and Artifact root with read-only diagnostic
credentials. The isolated analysis wheel can run alongside the installed
operational service; it does not activate a new service profile.

```bash
uv run mra research daily observations --target-session-from 2026-09-10 --target-session-to 2026-09-14 --experimental-model-use-id "$ORIGINAL_MODEL_USE" --include-unavailable
uv run mra research validity daily
uv run mra research validity daily --protocol-version 2 --target-session-from 2026-09-10 --target-session-to 2026-09-10
uv run mra research validity daily --protocol-version 1
```

Observation filters also accept exact Dataset/Decision IDs and `--completed-only`.
The validity entry always reconciles the full bound Model/use/Target cohort.
Date arguments select a descriptive view; they cannot cherry-pick the cohort
used for sample adequacy. Unavailable/failed requests and planning gaps remain
visible. Complete history reads are explicit; the service's default health budget
is unchanged.

The current protocol is v3, first eligible Target Sep-15, with 20 real estimable
sessions and 500 common observations required. Rolling N is 20, K is 5, and
quantile tails each contain `floor(n/5)` observations ranked solely by frozen
forecasts with deterministic commitment-ID ties. Only ALL_POPULATION is declared.
v1 remains immutable and explicitly incomplete because its exact Candidate,
Eligibility and instrument roster binding was missing. Sep-11 belongs to that
descriptive predecessor; Sep-10 new statistics are post-hoc. No previous
Evaluation receives new metric rows. A new protocol requires a new version,
predecessor SHA, actual declaration time, reason and later future cohort.
v2 bytes remain immutable; its formal cohort ends exclusively at Sep-15.
Sep-14's already published Prediction remains bound to the original Use.
v3 binds the separately registered successor Use; date filters never combine
old and new Uses into its formal population. Planning gaps and temporal blockers
also respect each protocol's exclusive end boundary.

The report separates canonical stored metrics from versioned derived statistics,
temporal validity from Formal PIT, and sample adequacy from information gain.
IC dispersion uses session counts; a 31-stock cross-section is one session.
SE is descriptive, with no claimed confidence interval or independence proof.
Rank baskets have no trading, T+1, cost or account-P&L authority.

Walk-forward is a dry-run over actual captured sessions and exact canonical data:
252 training, 63 validation, 1 embargo and 21 OOS sessions, step 21. It checks
source knowledge and immutable Model binding before OOS; it never trains.
History advances with the observation cutoff. Missing history returns NO with
blockers. Existing daily DISCOVERY Partitions remain DISCOVERY. Formal Provider
PIT, additional regime slices and economic validity remain NOT_READY.

Do not enter Alpha iteration on a single session or merely because the baseline
infrastructure passes. Actual predeclared multi-day minima and repeatable
information gain are prerequisites; model changes still require explicit scope.

The Sep-11 Research Validity observation retained a 123.92-second resource stop
and a later QueryCanceled in the human-research-disposition health query. The
original service recovered after owner reconciliation with unchanged wheel,
profile and timeout. Two successful recovery ticks do not establish continuity.
The immutable baseline record binds stage profiles and the exact query plan;
any performance follow-up must preserve source-integrity and privilege drift
checks and use actual service measurements, not a Provider batching assumption.

### Controlled ExperimentalModelUse rollover

Owner maintenance requires explicit authorization for the exact original
database and local OS owner. First preserve the current stopped/running service
fact, drain if running, reconcile Attempts and unknown effects, create a fresh
PostgreSQL backup, verify all referenced Artifact bytes and mirror to a distinct
physical device. Verify actual disk topology: paths and filesystem identifiers
alone do not prove separate hardware. Same-host redundancy is not offsite
disaster recovery.

Freeze original HBA bytes, SHA, mode, owner and complete runtime privilege
projection. Temporary authentication permits only the exact database, local
Unix socket, exact OS owner and peer authentication; no TCP, trust or grants.
Reload, verify actual owner/session/database/OID/cluster/schema/socket, then use
the existing Artifact and Model commands to register the one reconciled
successor identity with future validity. Close owner sessions and immediately
restore original HBA bytes/mode/owner, reload, prove owner login rejected and
the full runtime ACL unchanged. Any restoration failure blocks declaration and
service activation. A partially completed command requires read-only receipt
reconciliation; never create another successor or reopen terminal work.

Only after restoration and canonical owner reload may a successor protocol be
declared. Verify actual captured-calendar capacity with unchanged 20/500 floors,
32 members, ten downtime sessions and 20% missing-observation buffer. Preserve
predecessor bytes and use a fresh DB declaration clock before the first eligible
Target. A source declaration grants no formal Model or Provider qualification.

For a same-wheel rollover, retain the verified installation and deployment
receipt. Change only the daily template's explicit Use identity; renew only the
existing three backup bindings after a fresh snapshot. Save old private files,
preflight the proposed profile/template, activate the owned service once and
verify complete ticks. Original published/failed/abstained work continues from
its frozen plan. Read-only Validity source changes use a separate analysis wheel.
Manual maintenance or recovery never becomes a scheduled-backup PASS.
