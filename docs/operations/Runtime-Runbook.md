# Runtime Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Current executable operator procedures
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-07
> **Code Evidence:** `pyproject.toml`, `scripts/*.py`, `src/market_regime_alpha/cli`

## Install and verify environment

```bash
uv sync --frozen --extra dev --extra postgres
uv run continuous-research --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
uv run continuous-research portfolio-shadow-day --help
uv run continuous-research recovery-audit --help
uv run continuous-research qualification-protocol-record --help
uv run continuous-research qualification-forecast-record --help
uv run continuous-research qualification-evaluation-record --help
uv run continuous-research qualification-historical --help
uv run continuous-research qualification-oos --help
uv run continuous-research qualification-calibration --help
uv run continuous-research qualification-shadow --help
uv run continuous-research qualification-status --help
uv run model-governance --help
uv run pit-authority --help
```

## Target operational evidence recovery

The target `mra` commands use explicit `MRA_DATABASE_URL` and
`MRA_ARTIFACT_ROOT` settings. Keep connection credentials, machine-local hosts,
paths and inventory snapshots outside the shared repository. This operator
surface does not select a business Authority or alter evidence maturity.

First inspect the exact database name/OID/cluster, schema checksums, Artifact
root, archives/generations and active Runtime attempts. Record a fresh physical
integrity scan; old scan timestamps do not substitute for current bytes.

Check the Market consumers' 24-hour Artifact verification window before
freezing the backup. When it has expired, use the existing
`ArtifactApplication.verify` owner operation to observe actual hash/size/existence,
with a fresh caller-owned idempotency key per observation. Preserve every
Artifact identity/hash/size and every Capture known/recorded time; verification
metadata and its append-only verification/receipt/audit facts record the new
physical observation. Run the read-only evidence scan again, then take the
backup. If a drill crosses that freshness boundary, retain its negative result
and start a new verified backup/drill scope with new destinations.

```bash
uv run mra evidence inventory --role operational --records-directory "$EVIDENCE_RECORDS"
uv run mra evidence verify > "$EVIDENCE_RECORDS/integrity-scan-$SCAN_ID.json"
uv run mra evidence backup-plan --directory "$EVIDENCE_BUNDLE" \
  --expected-database-name "$EVIDENCE_DATABASE_NAME" \
  --expected-database-oid "$EVIDENCE_DATABASE_OID"
uv run mra evidence backup --directory "$EVIDENCE_BUNDLE" \
  --expected-database-name "$EVIDENCE_DATABASE_NAME" \
  --expected-database-oid "$EVIDENCE_DATABASE_OID"
```

Use fresh scan IDs and bundle destinations. Backup fails closed on wrong
identity, active attempts, inadequate disk or invalid referenced Artifact
bytes. It exports a PostgreSQL snapshot, copies only that snapshot's exact
Artifact roster and records dump/inventory/Artifact hashes and full dump
readability. Extra source files are reported, not silently adopted as Authority.
Do not recreate, drop or clean an operational evidence database.

For an independent restore drill, provision a fresh PostgreSQL 16 database and
fresh Artifact root, inspect their identities, restore `database.dump` and copy
the bundle's `artifacts` directory into the new root. Point the target settings
explicitly at that restored database/root before running:

```bash
uv run mra db verify
uv run mra evidence restore-check --bundle "$EVIDENCE_BUNDLE" \
  > "$EVIDENCE_BUNDLE/restore-check-$DRILL_ID.json"
uv run mra evidence verify
uv run mra backtest replay --run-id "$EVIDENCE_COMPLETED_BACKTEST_ID"
```

The drill must preserve all ordered table hashes, schema checksums and exact
Artifact bytes/references, reconcile archives, and replay the exact completed
historical/current campaign. A negative or incomplete campaign must keep its
status: integrity matching is distinct from completed replay. Restore-check
rejects the source database identity and source Artifact root. Keep its result
under the original bundle and refresh inventory against the original scope to
record the latest backup, integrity scan and successful restore drill.

When original Authority is unavailable, record the last provable old scope and
the new scope's actual start. Recovering immutable bytes into new canonical
captures/archives does not restore old IDs, known-times or prospective continuity.

Prospective continuation remains a bounded invocation of the sole existing
Runtime. The existing Application checks PostgreSQL time, reconciles prior
generations, records overdue terminals/planning gaps, resolves exact TradingSessions
and claims real due work. Public `continue`, `run-due`, `resume` and manual
prospective predeclare/write shortcuts fail closed and direct operators to
guarded `serve`. The old `continuous-research` prospective switches are also
closed; unrelated legacy work retains its existing behavior. Initial series
predeclaration requires an explicitly authorized canonical owner operation;
service does not infer or create an initial scope. CLI wiring alone is not evidence of an installed
continuously running service. No due window means `NOT_DUE`; never wait or
backdate to produce proof.

`mra archive prospective serve` provides a foreground process that wakes the
same continuation Application serially. It makes no business-time or due decisions,
holds no database transaction between wakeups, and creates no schedule outside
the existing Runtime. Keep machine-local database/Artifact settings and the
exact implementation SHA in the operator environment, outside the repository.
Before starting, complete the exact-name/OID, consistent backup, disk, active
attempt and single-writer preflight above.

Copy the [operation profile template](templates/prospective-operation.example.json)
to a private local file and replace every placeholder with owner-observed facts.
The template deliberately fails validation. Pin the exact database name/OID and
cluster system identifier, current schema/catalog, Artifact root binding,
installed source hash, immutable Target and series, dump hash and **receipt
hash**. The pinned receipt binds the same-read inventory bytes, snapshot time,
Artifact roster and dump. A freshly verified old snapshot is still old. The
source fingerprint is `implementation_source_sha256()` from the existing
`interfaces.prospective_operations` module; it hashes package Python/SQL bytes
and is independent of checkout versus wheel location. Keep this profile,
credentials and paths outside Git. Its public content hash identifies intent;
it is not business Authority or permission to adopt a different database.

```bash
uv run mra archive prospective status \
  --series-code "$MRA_PROSPECTIVE_SERIES" \
  --expected-database-name "$MRA_EXPECTED_DATABASE_NAME" \
  --expected-database-oid "$MRA_EXPECTED_DATABASE_OID" \
  --expected-cluster-identity "$MRA_EXPECTED_CLUSTER_ID"
uv run mra archive prospective preflight \
  --operation-config "$MRA_OPERATION_CONFIG" \
  --expected-database-name "$MRA_EXPECTED_DATABASE_NAME"
```

Status is a read-only database-clock projection, including old-schema scopes;
it does not admit them for execution. Preflight uses the current schema contract,
holds a session advisory supervision lock, verifies physical Artifact and backup
bytes, probes a private temporary file with fsync/rename/read, checks calendar
and Target lineage, and performs bounded exploratory Provider login/logout.
It creates no Capture or business fact. A healthy completed restore is not an
adopted operational writer. The v6 revision-gap correction changes a constraint
and its existing validator through an exact registered upgrade; original v5
databases fail current writer startup until separately authorized upgrade.
Prepare `mra db upgrade-plan` with exact name/OID, backup hash/size and code SHA;
only an explicitly authorized scope may execute its challenge with
`mra db upgrade-apply`. Never use bootstrap/recreate to repair an operational DB.

Read-only preflight reports strict health immediately. Service startup reports
OWNER_RECONCILIATION_PENDING until its first guarded continuation repairs any
interrupted capture-Run registration, then applies the same strict health
check. It never relaxes the expected Runtime roster to make recovery look complete.

```bash
uv run mra archive prospective serve \
  --operation-config "$MRA_OPERATION_CONFIG" \
  --series-code "$MRA_PROSPECTIVE_SERIES" \
  --code-sha "$MRA_IMPLEMENTATION_SHA" \
  --expected-database-name "$MRA_EXPECTED_DATABASE_NAME" \
  --actor-id "$MRA_OPERATOR_ID" --worker-id "$MRA_WORKER_ID" \
  --lease-seconds 120 --wakeup-seconds 30
```

The profile and CLI arguments must agree. Each wakeup emits database scope,
profile hash, canonical continuation, health summary and alert changes as JSON.
The supervision lock is checked again before owner actions and claims; a lost
connection/lock, changed source, old backup or exhausted disk stops further work.
The default template limits each wakeup to 16 actual claims and 120 seconds;
each BaoStock execute has one 10-second deadline including login/query/row
iteration, at most 100,000 rows and 32 MiB serialized response. SDK attempts are
one; there is no service retry of an unknown external effect. Database pool
capacity is at most four plus the one dedicated supervision connection. An
elapsed tick budget drains the current effect then exits 2; it is not a hard
cancellation of a business transaction. Tune budgets only as explicit local
operation intent backed by measurements, never as relaxed research thresholds.

`--maximum-wakeups 2` bounds a startup/restart drill. SIGINT/SIGTERM sets a
nonblocking stop flag and drains the current action, then prevents the next
claim. Foreground Ctrl-C or SIGTERM to the **verified owned process PID** is the
stop procedure; never kill an unknown worker. Preserve logs and inspect health
and Runtime after exit. On restart, the same continuation reloads Authority,
reconciles external effects and recovers expired leases before new work.
An EXTERNAL_EFFECT_UNKNOWN terminal is a reconciliation requirement, not
permission to repeat the Provider call. Do not run a second worker during drain.
No system service is installed by this command. A bounded process drill proves
lifecycle wiring only; sustained collection and a real due capture require
their own observed Runtime facts.

The optional [supervisor template](templates/prospective-supervisor.example.plist)
is an uninstalled lifecycle example. Its local launch script supplies the exact
environment/profile and uses `exec` for the foreground command above. Automatic
launch and restart are disabled deliberately: an error requires inspection and
reconciliation before restart. Installation or adoption needs separate explicit
authorization. No timer in the supervisor decides trading sessions or due work.

At day end, capture `prospective status`, `archive verify` for each reported
generation and `evidence verify`, then take a fresh consistent bundle using the
commands above. Health separately reports expected/opened/due/future, captured,
late, missed, failed, unknown effects, recovery backlog and planning gaps;
capture success, on-time completion and terminal coverage have separate
denominators. An empty opened roster yields typed NOT_ESTIMABLE rates.
Normal NOT_DUE causes no incident. Alerts emit OPENED/UPDATED/RESOLVED changes
within one process, avoiding repeat storms; restart emits a fresh observation.
Persist these JSON lines with their scope/hash and protect/rotate them locally.
They are auditable projections, not a second business journal. No external
notification is sent. Terminal completeness never means successful capture.

For original-database slow reads, `mra evidence diagnose --run-id ...` requires
the same exact name/OID/cluster flags as status. It records fixed parameterized
SQL, EXPLAIN JSON, lock/activity/I/O observations and bounded repeated timings in
read-only transactions. It does not increase timeouts, flush caches or change
server settings. An unreproduced historic QueryCanceled remains
ROOT_CAUSE=UNPROVEN even when present queries meet their budget. Keep the
original FAILED Run and completed recovery copy labelled by database identity.

Use `mra backtest diagnose --run-id ... --format json` (or `markdown`) for the
reconciled read-only funnel. The [research diagnosis](Research-Diagnostics.md)
records the existing campaign's denominator and sample limitations. This
projection cannot upgrade its frozen V1 economics, select a daily model or
relabel Validation as untouched OOS.

Include the last available exact TradingSession in the operational inventory
review. Continuation requires the decision, Outcome and later verification
sessions to exist in canonical Market evidence. Extend missing calendar evidence
through the Market capture/normalization owner; never infer weekdays or silently
omit an unavailable session. A finite calendar horizon is an operational input
boundary, not proof of indefinite continuity.

For Backtest recovery, an unexpired Attempt remains owned by its existing lease.
`mra backtest resume` can return `RUNNING` without additional completed actions.
Inspect the exact Runtime Run/Attempt; ordinary lease recovery uses PostgreSQL
time and does not steal the fence. Only completed zero-mismatch replay qualifies
as completed resume/replay evidence.

Use `mra backtest progress --run-id "$EVIDENCE_BACKTEST_ID"` for a bounded
read of the complete declared action roster and its exact Runtime bindings.
The response includes a PostgreSQL observation time, Runtime Run IDs, latest
Attempt states, leases and error codes. An absent binding remains absent.
`owner_reconciliation=NOT_PERFORMED` is deliberate: Runtime `SUCCEEDED` alone
does not prove Dataset, Decision, Outcome, Model or Evaluation completion.
Use `mra runtime inspect --run-id "$RUNTIME_RUN_ID"` for the bound step trace;
use Backtest `inspect` and `replay` for complete owner reconciliation.

For an existing frozen campaign, keep its executable checkout and environment
unchanged during resume. A newer read-only progress client can observe its
immutable specification without replacing the frozen worker. First verify
the database/OID/cluster and Artifact root, current backup bytes and disk,
absence of conflicting Attempts and workers, and the original code/bundle
identity. Record the CLI exit code and returned execution/research states;
an exit code or a running process alone does not establish campaign completion.

## Phase E Historical Corpus

This free-data path remains `EXPLORATORY / PIT_INCOMPLETE`. PostgreSQL is the
only business Authority; the Artifact Root stores immutable large bytes and is
never scanned to select an owner.

Freeze an effective-dated real historical constituent set before an Index run:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema market_regime_alpha \
  --principal-id "$MRA_PRINCIPAL_ID" \
  historical-universe-sync \
  --effective-date 2026-06-15 \
  --artifact-root /absolute/path/to/artifact-root
```

`historical-corpus-acquire` accepts an explicit `symbols` list, one or more
exact frozen Universe snapshots, or one exact longitudinal Universe Timeline.
Longitudinal acquisition requires `context_instruments` with distinct,
role-labelled `market_index_symbol` and `theme_etf_symbol`; the command records
and returns the immutable Context Instrument Set reference that must be bound
to the Historical Command. The Phase E frozen methodology accepts exactly
`000300.SH` as the market index and `510300.SH` as the theme ETF; changing those
roles requires a new frozen Experiment. Legacy single-snapshot acquisition may retain the
pre-E3 `context_symbols` input only for replay compatibility. Optional
`timeframe_ranges` freezes different Daily and 5-minute windows without an
implicit Reader shortcut. It performs BaoStock acquisition, deterministic
normalization, logical hashing, staging validation, atomic publish, PostgreSQL
registration and exact reload. Empty provider results, rejected rows and
missing fields remain in coverage.

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema market_regime_alpha \
  --principal-id "$MRA_PRINCIPAL_ID" \
  historical-corpus-acquire \
  --input phase-e-acquire.json \
  --artifact-root /absolute/path/to/artifact-root
```

Before execution, freeze one Free Research Universe owner and a WATCHLIST or
`INDEX` policy. An index constituent set must never be labelled `FULL_A`; the
materializer derives an exact membership snapshot from the historical
constituent owner.

Then freeze the
canonical exploratory Target Protocol, Governed Experiment owner and
`HistoricalResearchCommand`. The command binds the exact normalized Dataset,
security master, policy, target, experiment, calendar, code revision and
DecisionTime. Historical `retrieved_at` is never rewritten to the trading date.

For `FREE_RESEARCH_ARCHIVE`, run, resume and replay require the same explicit
Artifact Root:

```bash
uv run continuous-research ... historical-run \
  --input phase-e-run.json --artifact-root /absolute/path/to/artifact-root
uv run continuous-research ... historical-resume \
  --run-id historical-research-run-... \
  --artifact-root /absolute/path/to/artifact-root
uv run continuous-research ... historical-replay \
  --run-id historical-research-run-... \
  --artifact-root /absolute/path/to/artifact-root
```

`historical-run` input is exactly `command` plus nullable
`max_stage_commits`; a bounded value is the supported interruption test. Resume
reloads exact command/session/receipt/component owners. Feature through Forecast
can see only rows with `event_end <= DecisionTime`; next-session bars enter only
Outcome.

Daily feature history uses one predicate-pushed read whose first date is capped
at 180 calendar days before the Decision date and whose per-symbol result is
then capped at the frozen 61-session Canonical requirement. A sparse, newly
listed or suspended symbol therefore remains explicitly history-insufficient;
it cannot force a scan back to the beginning of a multi-year package.

After a terminal run, `historical-evidence --run-id ... --artifact-root ...`
persists Corpus Summary, cumulative Alpha Ablation, Strategy Economics,
Portfolio Performance and owner-resolved Exploratory Model evidence. Repeating
the command returns the same identities. Negative, inconclusive and
not-estimable findings remain durable. Costs, fillability, impact and capacity
are `ENGINEERING_ASSUMPTION` until calibrated; temporal validation is not Formal
OOS.

Never repair a failed run by scanning directories, choosing `latest`, silently
filling data, substituting a provider or resuming under a different computation
revision. Freeze a new Experiment and Command when code changes, and retain the
interrupted run for audit.

Commands frozen before the Phase E3 constituent timeline remain immutable.
Terminal pre-E3 runs use `IMMUTABLE_PRE_E3_RECEIPT_VERIFICATION`: PostgreSQL
reloads and content-validates their exact command, session and receipt chain,
without applying current E3 materialization semantics. An incomplete pre-E3
run requires its exact historical code revision and otherwise fails closed;
operators must not silently resume it with E3 semantics.

## PostgreSQL Authority Only

Bootstrap a dedicated local authority only with an administrator URL:

```bash
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL" \
  --dry-run
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL"
```

Apply or verify the packaged schema:

```bash
uv run python scripts/apply_postgres_migrations.py
uv run python scripts/apply_postgres_migrations.py --verify-only
```

Expected head: migration 106, `alpha_correctness_failure_revision`. Expected
schema catalog: 283 tables. Migrations 052–067 add Formal Protocol bindings and
owner-resolution receipts, Provider×Contract×Fact decisions,
Historical/Locked-OOS/Calibration owners, the durable underlying Locked-OOS
and frozen-family consumption ledgers, owner-computed Forecast receipts,
reusable Strategy Shadow Policy, C6/C7 stage decisions,
persisted blocked Production Admission and Controlled Execution readiness.
Migration 059 adds only the immutable exploratory training/model-parameter
journal consumed by the owner-resolved Forecast executor; all Formal/OOS,
Calibration and Production flags remain database-enforced false.
Migration 068 installs Historical Corpus Authority. Migration 069 adds the
exact-owner timeframe/date/symbol-bucket selective-read index. Migration 070
accepts the v2 effective-dated historical constituent owner while preserving
immutable v1 Research Universe rows.
Migrations 071–080 add effective/publication-dated Historical Security Facts,
unresolved corporate-action gaps, bounded component/Outcome projections, the
exact constituent timeline, v4 content-verifiable fact acquisition scope,
immutable labelled index/ETF context, owner-bound Outcome label dates and the
exploratory Experiment Definition reloaded before longitudinal Scope.
Corporate-action
absence is evidence only when symbol, interval and constituent lineage are all
inside that immutable scope.
Migrations 081–084 complete longitudinal Historical fact, feature and
configuration ownership. Migration 085 adds stable Strategy Contracts/Versions,
shared cycles/runs/gates/proposals, cross-strategy Portfolio decisions,
observed-Fill allocation, Path Outcomes and typed feedback. It also admits the
bounded `STRATEGY_RUNTIME` child to the existing Continuous Journal; it does not
create a scheduler, broker path, physical Position writer or Production
authorization.
Migration 086 adds one immutable fill-derived realized Strategy Outcome table.
Open Strategy sleeve state remains reconstructed from existing Proposal, Fill
allocation, exact PIT Trading Calendar and manual account observation owners;
no Position table, scheduler or execution Authority was added.
Migration 087 embeds exact accepted Portfolio/Proposal authorization in the
existing ManualTrade ledger and adds append-only realized Outcome revisions.
It adds no table: partial/corrected observed Fills still use `manual_fills`,
physical Position still comes only from the Fill projector, and Strategy sleeves
remain allocation projections.
Migration 088 extends those same rows with exact reconciliation and canonical
Market Bar/Dataset lineage plus the Proposal quantity ceiling. Account,
Proposal and Intent advisory locks serialize remaining-quantity, cash,
available-sell and projected-exposure reconstruction from existing
ManualTrade/Fill/Position facts. It adds indexes and constraints but no table,
reservation ledger, Price Authority, Position Authority or Broker path.
Unobserved BUY/SELL exposure uses signed effective-Fill quantity deltas marked
by existing decision/account owners; Fill allocation and Position/Outcome
recovery use the same account lock so correction cannot publish a torn head.
The Strategy cycle carries the complete existing Market Data Dataset owner
payload; execution reconstructs and hash-verifies that owner and exact Bar
membership rather than trusting the decision-price projection alone.
Migrations 060–062 add the Full-A Runtime Scope, restartable shared Historical
Session journal, owner-resolved Shadow observations and multi-period Shadow
performance evidence. They grant no trading or Formal research authority.
Migration 067 is a forward-only correction that adds exact Strategy/Portfolio
lineage bindings and temporal/owner constraints. It does not rewrite migrations
060–066 or infer typed lineage for legacy rows.
Migration 065 names the global Artifact-root locator contract for Controlled
packages. New rows must use it; old un-namespaced rows remain immutable and
fail closed instead of triggering filesystem discovery.
Migrations 089–092 admit Golden Loop V2 engineering evidence, Alpha Research
Phase II evidence kinds and Strategy Contract V2 under existing owners, then
enforce the Forecast semantic boundary without granting qualification.
Migration 093 persists the frozen `TEMPORAL_VALIDATION_V1` window. Migration
094 adds immutable, owner-derived pre-Strategy Risk State and Strategy
Opportunity facts. Migration 095 admits the immutable Daily Alpha snapshot.
Migration 096 adds the Controlled package locator and exact Prediction
Snapshot/Strategy diagnostic lineage for Prospective Outcome V2. Runtime and
Repository construction verify this schema and fail closed. Migration 097 binds
each new Daily Alpha snapshot to the adjacent target session under the exact
typed Trading Calendar owner. Migrations 098–104 add the label-blind frozen
Locked-OOS scope, exact historical fact indexes, typed Calendar binding,
externalized component payloads and bounded Outcome/Forecast indexes used by
the WP-ALPHA-PROOF-02 canonical campaign. Only this explicit operator surface
may apply migrations.
Migration 046 remains unchanged. Missing/unreachable PostgreSQL is a blocked
operation; there is no alternate persistent backend.

Migration 046 intentionally stops if an existing database contains reference-only qualified Validation or Historical Sample rows. Do not update or delete those append-only rows in place. Preserve/export the database, audit the owning evidence, and use a separately reviewed forward-repair migration before retrying 046.

## Canonical Runtime

Inspect required arguments before scheduling:

```bash
uv run continuous-research run-due --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
uv run continuous-research portfolio-shadow-day --help
uv run continuous-research portfolio-shadow-replay --help
uv run continuous-research research-universe-sync --help
uv run continuous-research recovery-audit --help
uv run continuous-research report-day --help
uv run continuous-research replay-day --help
uv run continuous-research inspect-run --help
uv run continuous-research inspect-strategy --help
uv run continuous-research replay --help
```

Every command requires an explicit database URL/schema and `--principal-id`.
Bootstrap and administer engineering Principals through `model-governance access-*`;
`continuous-research` checks the active Role/Permission before any
read or mutation. The Principal ID remains a caller assertion until a future
external authentication binding exists, so this is engineering RBAC rather
than production authentication. Every invocation is audited against a
content-addressed operation resource. Non-Admin Shadow and recovery mutations
also require `--approval-decision-id` for an exact independently approved
resource; the denial output reports the required resource ID/hash. Production
mode is rejected before any Runtime Journal mutation. `run-due` remains the
canonical tick operation. `run-day` invokes that same operation and, for a
completed `SHADOW` run, resolves its PostgreSQL Summary and freezes Research
Shadow. Before a due Research/Shadow decision it also attempts the bounded
BaoStock Historical Sample build. No samples remains a valid fail-closed
Forecast result. An already-available `UNQUALIFIED` Registry Dataset permits an
exploratory, uncalibrated Forecast. Production never receives that provider.

After a completed run, inspect the two families and the cross-strategy decision
through the read-only projection:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  --principal-id "$MARKET_REGIME_ALPHA_PRINCIPAL_ID" \
  inspect-strategy \
  --run-id CONTINUOUS_RUN_ID
```

The result must show exact cycle/run/version hashes, gate and proposal counts,
Portfolio status and any lineage-scoped Path Outcome/feedback artifacts. A
`DATA_INSUFFICIENT` run and a `NO_ACTION` Portfolio are valid available facts.
Inspection is read-only and cannot recompute or promote a decision.

For a stateful account-bound Shadow tick, pass the same account identity to the
canonical operation:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  --principal-id "$MARKET_REGIME_ALPHA_PRINCIPAL_ID" \
  run-due \
  --strategy-account-id "$MARKET_REGIME_ALPHA_STRATEGY_ACCOUNT_ID" \
  ...
```

This makes the Strategy child resolve sleeve state from PostgreSQL observed
Fill allocations and manual account observations before policy execution.
Omitting the option preserves stateless research compatibility; it must not be
used for claims about cross-session Position decisions. `inspect-strategy`
reports the frozen position states and any fill-derived realized Outcomes.

The free-data operational sequence is:

```text
continuous-research run-day ...
continuous-research settle-day \
  --trading-date YYYY-MM-DD --next-session-date YYYY-MM-DD \
  --artifact-root ARTIFACT_ROOT --at RFC3339
continuous-research strategy-day --observations OBSERVATION_JSON
continuous-research portfolio-shadow-day --observations PORTFOLIO_JSON
continuous-research report-day --trading-date YYYY-MM-DD --at RFC3339
continuous-research recovery-audit --checked-at RFC3339
continuous-research replay-day --trading-date YYYY-MM-DD
```

`settle-day` resolves the frozen Controlled package, Candidate, Dynamic Pool and
Research Shadow IDs from PostgreSQL and acquires BaoStock five-minute OHLC after
close for both current and missed sessions. It writes Outcome, Targeted Outcome,
Panel V2 and Factor Enrichment artifacts. The same step derives eighteen
multi-horizon/barrier calibration hypotheses from the frozen Forecast exposure
and factual Target labels. A hypothesis can fit only when the Forecast Target
identity equals the Outcome Target identity; the current multi-session Forecast
is therefore not reused as a T+1 forecast and remains `NOT_ESTIMABLE`. Positive
and negative hypotheses persist their complete lineage. It records a versioned engineering protocol (Platt
by default; the research harness also supports Isotonic and Binning) with
trading-date partitions and label-aware purge; insufficient
samples produce `NOT_ESTIMABLE`, and every artifact remains
`calibrated=false`. A forecast quantile is treated as a raw score, never as a
probability. Tencent last-price snapshots remain runtime context and are never
promoted to factual OHLC/barrier evidence. Once factual settlement exists,
retries reload its PostgreSQL-owned identities and immutable packages without
calling the Provider again.

`strategy-day` resolves the settled Research Shadow, Panel and Candidate from
PostgreSQL. When the tick has a Multi-Strategy cycle, its Entry creation also
requires and records the exact canonical Overnight ENTER Proposal; otherwise it
returns `NO_ACTION` instead of independently re-deciding Entry. Its observation
file must explicitly provide every quantity,
price, fillability, cost, holding/exit value and each value's provenance as
`OBSERVED_FACT`, `ENGINEERING_ASSUMPTION`, `CALIBRATED_PARAMETER` or
`OPERATOR_INPUT`; no result-affecting numeric default is supplied. It advances
only the isolated Strategy Shadow ledger.

`portfolio-shadow-day` resolves current Candidate scores, the settled Panel
and any previous Portfolio state from PostgreSQL. Its input supplies a stable
versioned Policy and explicit per-value provenance for prices, ADV, trading
status, price-limit state and session observations. Missing price, ADV,
trading-status, price-limit or session evidence becomes an unfilled Shadow
Intent. `portfolio-shadow-replay` verifies the immutable predecessor/CAS chain.
Shadow Fill/Position never become real Fill/Position.

All four day commands are duplicate-safe and resume partial owner journals on
reinvocation. Strategy Shadow reloads immutable Entry/Fill/Position owner rows
and can advance later Holding/Exit observations until Outcome settlement.
`resume --run-id` releases recoverable Continuous Runtime state;
`replay`, `strategy-replay` and `replay-day` verify owner histories without
creating real trading state. Provider failures leave earlier immutable
PostgreSQL evidence intact. Lease/fence or CAS conflicts fail closed and must be
retried through the same command and identifiers.

`recovery-audit` is read-only. It identifies expired Tick leases, retryable
Provider/Tick failures, partial or missed Research Shadow settlement, missing
Panel V2, partial Strategy Shadow and failed Portfolio replay. It reports the
owner command to use; it does not mutate or bypass a fence.

Free data may run only in `RESEARCH` or `SHADOW`. A Production request must fail with `FREE_DATA_PRODUCTION_AUTHORITY_DENIED`. Do not edit status rows, receipts or hashes to recover a run; resume through the owning journal.

## Phase C evidence resolution

Use `pit-authority assess-provider-fact` separately for every exact Provider,
Contract and Fact Kind. It reloads typed source qualifications/evidence and may
return `QUALIFIED`, `INCOMPLETE`, `REJECTED`, `SUSPENDED` or `REVOKED`; never
copy one Fact Kind's status to another. Current BaoStock/Tencent scopes resolve
`REJECTED` until independently validated formal evidence exists.
`pit-authority revoke-provider-fact` appends an explicit terminal revocation;
ordinary reassessment cannot silently reinstate that scope.

`qualification-protocol-record` accepts only the Formal Protocol reference
graph. PostgreSQL reloads the Target Protocol and Targets, Evaluation Protocol,
Trading Calendar, Universe, Dataset, Historical Sample, Feature, Factor, Model,
Threshold, OOS, Cost, Calibration, Strategy and Entry/Holding/Exit owners, then
stores an immutable owner-resolution receipt for every binding. The Calendar
payload snapshot is accepted only when it is anchored to the existing PIT
Artifact Authority resolution; it is not a second Calendar owner. Caller-supplied
component payloads are rejected. Model Governance also freezes current lifecycle,
Registry version and exact governance action revisions; terminal models are
rejected. Pre-057 Protocols are replay-compatible after migration backfill but
cannot enter a new Formal research path. `qualification-forecast-record` accepts only
Formal Protocol, Formal PIT, symbol/scope and idempotency references. PostgreSQL
derives DecisionTime from the PIT request, resolves exact Model/Configuration/
Code/Feature/Factor/Threshold/Dataset/Universe/Target lineage, invokes only its
installed executor catalog and assigns materialization time from its own clock.
Caller prediction values and backdated materialization times are not accepted;
unsupported exact executors persist `NOT_ESTIMABLE` receipts.
`qualification-evaluation-record` accepts only immutable Forecast, Target
Outcome Label and Panel slice/row bindings; PostgreSQL reconstructs score,
return, label interval and slices, freezes the complete result-affecting
lineage across the complete pre-registered Target family and all referenced PIT
requests. A raw subject/decision-session/outcome-session path is unlocked once;
only that already-frozen family may then consume its Target-specific labels.
The family ledger is bridged to the migration-056 legacy ledger, so neither path
can make previously read evidence pristine again. It never accepts caller-supplied
observation values or result timestamps. `qualification-historical` binds each
sample record to its exact DecisionTime PIT and owner-computed Forecast receipt.
`qualification-oos` requires the Locked-OOS record set to equal the qualified C3
record set inside the exact Locked-OOS windows for every frozen Target. It first
requires estimable Train and Validation floor metrics for every required
Target/fold/sensitivity, then replays Locked-OOS observations, Calendar and
family-level multiplicity before persisting C4. For every Formal operator JSON
command, `actor` must exactly equal the already-authorized `--principal-id`.
`qualification-calibration` accepts a frozen policy file but re-reads the
Formal Protocol, target/label/Forecast pair, calibration artifact, partition
bindings and Formal OOS decision. `qualification-shadow` counts only sessions
created and scheduled after its policy lock with `LIVE_TRUSTED` clock and
`LIVE_ACQUISITION` origin; it replays session events, SourceManifest,
attestation, complete T+1 factual Outcome, Strategy Outcome and Portfolio day. `qualification-status`
persists C6, C8 and C9 state. An optional `--entry-policy` records the exact C6
policy and owner bindings. These commands can persist negative, blocked,
not-estimable or accumulating results. They do not invoke a Broker, unlock
Canonical `ENTER`, or automatically promote a model.

## Authority administration

```bash
uv run state-system --help
uv run decision-system --help
uv run model-governance --help
uv run pit-authority --help
uv run research-shadow --help
uv run model-governance access-bootstrap-admin --help
uv run model-governance access-authorize --help
uv run model-governance access-request-approval --help
uv run model-governance access-decide-approval --help
```

`decision-system` is manual-account decision support. In addition to account and
decision commands, `create-strategy-intent --input`,
`update-strategy-intent --input`, `record-strategy-fill --input`,
`recover-strategy-execution` and `inspect-strategy-execution` form the bounded
operator path from an accepted Multi-Strategy Portfolio line to the existing
manual Fill/allocation owners. The intent input binds Portfolio, Proposal,
account and PIT Calendar; the service resolves the latest eligible, exact-time,
complete reconciled account fact and the Strategy cycle's canonical Market Bar
price after reconstructing its full Dataset owner and verifying Bar membership.
It does not accept a caller account-observation ID or reference price. A
quantity override may only reduce the recommendation and requires a reason.
`update-strategy-intent` records CANCELLED/REJECTED/UNKNOWN or reconciliation
states with CAS; unused reservations are released. Read-only inspection reports
authorized/reserved/filled/remaining quantity, active intents, account reserved
cash, projected exposure and all owner references. Recovery is safe after
a persisted Fill because it reconstructs missing allocations and Outcome heads
from immutable facts. These commands do not create a broker Order or grant
automatic execution authority.

Current PostgreSQL model selection is still required for the broader manual
decision workflow; Production qualification is currently forced closed. `research-shadow`
freezes research decisions and outcomes, not simulated fills. Strategy Shadow
is exposed only as subcommands of `continuous-research`; there is no duplicate
installed CLI.

Access Governance permits a one-time Admin bootstrap only while the Principal
table is empty, then uses append-only Role grant/revoke and two-person
engineering Approval. It intentionally has no Production Admission or Broker
permission. Principal IDs on a local CLI are not proof of authentication.

## Validation

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$TEST_DATABASE_URL" \
MRA_WP17P_HISTORICAL_DATABASE_URL="$HISTORICAL_DATABASE_URL" \
MRA_WP17P_HISTORICAL_ARTIFACT_ROOT="$HISTORICAL_ARTIFACT_ROOT" \
uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

Qualification requires both the disposable test database and the exact read-only
historical evidence scope. Missing evidence is `BLOCKED / NOT_RUN`; a skipped
test is not a qualification PASS. Never point bootstrap/recreate tests at an
operational or historical evidence database.
