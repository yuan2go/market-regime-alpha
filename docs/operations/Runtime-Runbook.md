# Runtime operations

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `src/market_regime_alpha/interfaces/cli`, `src/market_regime_alpha/interfaces/prospective_service.py`, `src/market_regime_alpha/interfaces/prospective_operation_guard.py`, `src/market_regime_alpha/interfaces/daily_service.py`, `docs/operations/templates`

This runbook describes available commands and safety boundaries, not a deployed
service's current state. Use only the explicitly authorized project/database/
user-job scope. Never stop an unknown process, substitute a restored writer, or
reopen a terminal failed Run. Repository maintenance does not authorize deployment.

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

Integrity refresh includes daily bars and TradingSession source Artifacts
referenced by the current and original pending plans as well as prospective archive inputs. It verifies physical bytes
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
