# Roadmap

> **Status:** ROADMAP
> **Code Evidence:** `src/market_regime_alpha`, `tests`, `scripts/check_docs_links.py`

This is the sole active plan. Evidence and historical results do not authorize
the next experiment or deployment. Repository hygiene is complete at the
implementation recorded in the archive index. Business feature development and
live configuration changes require their own explicit scope.

## Completed repository maintenance

Current entry points, owner call chains, schema facts and test contracts are
indexed and source-linked. Historical documents are isolated without byte
changes; dead private helpers and obsolete tests have explicit dispositions.
Default and external-history regressions, PostgreSQL, static/document guards,
build and installed-artifact checks have executed. The
[archive index](../archive/README.md) records exact revisions, failures and
results. These facts do not authorize deployment or a new experiment.

Keep the current documentation set small. For future changes regenerate the
inventory, run affected behavior and hygiene checks, and preserve historical
identities. The items below are investigations requiring concrete consumer and
invariant evidence; they are not permission for a broad refactor.

## Consumer convergence delivery

Consumer discovery, canonical entry convergence, dead wiring/package-data
removal, historical/account boundary checks and risk-directed verification are
complete at the implementation in [Current State](Current-State.md).
The consumer graph/dispositions are in the existing code inventory. New research
enters only `mra` and `infrastructure/postgres`; historical protocol tools are
non-current, and account/Fill/formal-governance exceptions remain explicit.

Scope excludes finance changes, live deployment, account claim conversion and
schema deletion. Targeted consumer, persistence, replay, architecture, static, docs and installed
artifact checks have passed with explicit revision/scope matching. The full
repository execution and live cutover were not run.

## Research Runtime cutover

The canonical research Runtime, installed artifact handoff, single-writer
admission and frozen daily recovery are delivered at the implementation in
[Current State](Current-State.md). Account claim conversion is
outside this scope; formal Model/PIT governance retains its admission floors.

| Work | Implementation / verification boundary |
|---|---|
| Retire remaining all-day research writer APIs | Remove tick/schedule runners and FreeData service wiring; retain account journal values and exact historical reads |
| Controlled installed profile | Compare frozen source, wheel, installed package/metadata/dependencies, exact DB/schema/Artifact/Target and backup; emit a new immutable profile/receipt |
| Writer exclusion | Cover non-Attempt canonical connections and retained account/governance writes without replacing their owner or transaction isolation |
| Pending continuity | Recover original Model-use/plan/code identities; new predictions require current deployment identity; report/replay verify completed Evaluation |
| Qualification | PASS: 1,893 scoped tests, preserved normal/missing/crash/restart contracts, independent restore/replay, static/build/install/docs evidence |

No operational database/service/profile is changed by this engineering delivery.
Operational data-loop proof requires separate authorization, exact installed
handoff, current backup and real observations. Future windows are not simulated
into prospective qualification.

## Operational data-loop proof

The one-time merged-main activation regression has completed, including the
PostgreSQL and locally available historical suites. Operational work now uses
the exact original database, a restricted project runtime login, verified
installed wheel/profile and the existing owned user service. Read-only
diagnostics and backup use separate credentials; restored databases remain
verification scopes. See [Current State](Current-State.md) and the
[Runtime Runbook](../operations/Runtime-Runbook.md) for observed scope and controls.

| Dependency | Acceptance boundary |
|---|---|
| Installed handoff | Exact identity, verified backup, old service drain, exclusive admission, bounded startup and graceful restart |
| Real input and prediction | Actual Capture/normalization, complete frozen population, publication before the exact Target window; preserve failed requests |
| Natural maturity | Original publication plan → canonical Outcome/Evaluation → immutable report/replay, without advancing time |
| Continued accumulation | Refresh backups and physical integrity, inspect pending/failed work and planning gaps; duration and success are separate metrics |
| Research validity | Begin only after the operational lineage is accumulating stable real observations; no new model, factor or tuning in activation |

A repaired permission or integrity prerequisite cannot reopen a terminal failed
Run. Explicit new requests retain their current times and distinct identities.
A passing restore or disposable-clock test cannot satisfy natural maturity or
sustained multi-day proof. Existing failed campaign and qualification limits stay
unchanged.

## Operational data-loop closure

### Active execution: real maturity and operational loop closure

The current real maturity and operational closure work is explicitly authorized
against main `97f5d331042a72fb322bc156e5dcbb31f6c19731` in an isolated worktree.
The execution order is:

- [ ] Freeze current DB, installed profile, principal, service, Attempts, backup,
  original publication and three health scopes into immutable observations.
- [ ] Continue only the original verified frozen prediction through actual late
  Provider observation, exact Outcome commitments and canonical Evaluation.
- [ ] Reconcile full populations, canonical diagnostics, immutable reports and
  repeated zero-write completed-cycle replay.
- [ ] Diagnose observed service/backup failures, apply only necessary correctness
  repairs with focused tests, and restore the authorized owned service safely.
- [ ] Close continuous day-ledger and read-only research observation gaps with
  canonical consumers, if the first real Evaluation succeeds.
- [ ] Record source-bound validation, operational cutoff and independent exit
  gates. Preserve scheduled failures, missing data and all historical terminals.

No model/Target change, terminal reopening, synthetic time, fallback Provider or
research qualification is authorized by this plan. Live code changes require
the installed handoff in the Runtime Runbook. Evidence-only work uses directed
checks rather than a full repository regression.

The runtime privilege envelope, scoped read-only health and frozen-work day
ledger are implemented, verified and installed in the original owned scope.
The actual scheduled backup, exact service recovery and independent restore
retain their receipts. Models, targets and prior results are unchanged.

The remaining dependency is the original timely prediction's natural Target
maturity, followed by actual collection, owner settlement, Evaluation and
zero-write report/replay. The service retains its original plan and keeps old
terminal failures closed. Three consecutive real trading days remain a separate
sustained-evidence gate, not a reason to wait or synthesize observations.
The later health QueryCanceled exposed a Provider-wide bar-freshness scan;
the corrected observer uses the exact plan roster and existing index. Continue
observing tick latency: the intermittent underlying I/O cause remains unproven
and budgets were not increased. See Current State for the frozen observation
cutoff. Do not begin Alpha iteration before real Evaluation.

## Remaining architectural debt

| Boundary | Executable evidence | Smallest next investigation |
|---|---|---|
| Two persistence families | `infrastructure/postgres/schema.py` and `persistence/postgres/migrator.py`; account/Model/PIT consumers retain old claim and schema contracts | Map canonical Runtime claim admission and observed-account UoW ownership before deleting that family |
| Research package overlap | `research`, `research_qualification`, `application/historical_corpus`, `platform`; historical tools plus account/formal-governance value contracts | Keep exact serializers; migrate one account/governance contract at a time when its replacement is authorized |
| Large orchestration modules | `bootstrap.py`, `interfaces/daily_research.py`, `interfaces/cli/main.py` | Extract only when an independently demonstrated correctness/change boundary requires it |
| SQL source-text architecture tests | Several retained tests inspect strings rather than AST/behavior | Replace only against an equivalent mutation-sensitive contract; names alone do not establish duplicates |
| Historical external evidence | Explicit history tests require an exact database and Artifact root | Keep opt-in and fail closed when prerequisites are absent; never copy successful rows into failed history |
| Operational and research qualification | Canonical status/health/replay commands and original immutable evidence | Observe the explicitly authorized scope; source tests do not prove current service, successful capture or Alpha |

No new abstraction, scheduler, generic registry, strategy experiment or model
qualification is authorized by this Roadmap.
