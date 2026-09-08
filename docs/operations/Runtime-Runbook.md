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
