# Roadmap

> **Status:** ROADMAP
> **Code Evidence:** `src/market_regime_alpha`, `tests`, `scripts/check_docs_links.py`

This is the sole active plan. Evidence and historical results do not authorize
the next experiment or deployment. Repository hygiene is complete at the
implementation recorded in the archive index. Business feature development and
live configuration changes require their own explicit scope.

## Engineering delivered: continuous research reliability

The continuous research reliability package starts from main
`76c19a60f5106dd184a20fdaf46d786629a9cd99`. Development and disposable verification
are authorized. Original database writes, service changes, installation activation,
external messages and trading require separate session authorization.

Reuse the existing composition, Runtime and owners. Preserve released SQL,
protocols, old model decoding and all failed/unknown historical work. Execute
these dependency-coherent checkpoints, with the following risk-directed gates:

| Work / risk | Implementation boundary | Necessary verification |
|---|---|---|
| Model serialization changes fitted mathematics | `deterministic_linear`, concrete trainer and Model publisher | Independent ordinary/constant/tiny-scale arithmetic; fit/load/predict round trip; invalid/overflow values; old bytes decode |
| Notification ACK overclaim, duplicate effects, stale signals | `notifications`, `daily_delivery`, daily discovery/service/CLI | Local HTTP protocol responses; real PostgreSQL attempts, UNKNOWN/restart, expiry, cross-day discovery; no real external messages |
| Fixed scan limits and work starvation | Daily query ports, `daily_service`, canonical CLI tick | Keyset pages across Uses, visible excluded/failed counts, prediction/outcome/prospective budget fairness, deadline abstention |
| Health exceptions obscure committed results; safety rejection swallowed | CLI stage boundaries, service and Pool as needed | PostgreSQL cancellation/rollback, original exception, guard refusal, drain; measured service stages at representative roster scale |
| Incomplete calendar/input readiness and unreachable cohorts | Existing Market/calendar owner and validity capacity consumer | Captured calendar gaps/duplicates/failure/restart, true readiness roster, use lifetime and publication/maturity/operating budgets |
| Recovery substitutes current configuration or repeats completed work | Daily original-plan recovery, owner reports and CLI | Crash after publication/partial Outcome/completed Evaluation, expired/revoked Use, old installation identity, zero-write replay |
| Backup copy mistaken for restore; broken Model lineage hidden | Existing evidence/backup/restore and model queries/CLI | Fresh PostgreSQL restore, schema/owner roster/Artifact hashes and report replay; corruption refusal; exact Model chain |

- [x] Confirm current call chains and reproduce gaps before corrections.
- [x] Implement numerical and delivery contracts with compatibility checks.
- [x] Wire bounded discovery, fairness, health isolation and operational commands.
- [x] Verify calendar/capacity, frozen recovery, backup/restore and Model lineage.
- [x] Run affected PostgreSQL/runtime regressions, static/docs/inventory checks,
  build and independent wheel CLI smoke; retain initial failures and reruns.
- [x] Record implementation and final revisions plus five separate gates:
  IMPLEMENTATION, TARGETED_ENGINEERING_VERIFICATION, ORIGINAL_SCOPE_DEPLOYMENT,
  SUSTAINED_REAL_SESSION_PROOF and RESEARCH_VALIDITY.

No synthetic future sessions establish continuity. Naturally elapsed sessions,
original-scope activation and research adequacy remain independent evidence gates.
The implementation and isolated verification at
`622a9f38ad9a3f074662ac7e6b0961181b29bc43` are recorded in
[Current State](Current-State.md). The final checkpoint adds verification
documentation only. Original activation, real remote delivery and sustained
natural-session proof remain unexecuted and require their stated prerequisites.

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

### Completed: real maturity and operational loop closure

The current real maturity and operational closure work is explicitly authorized
against main `97f5d331042a72fb322bc156e5dcbb31f6c19731` in an isolated worktree.
The recorded execution completed:

- [x] Freeze current DB, installed profile, principal, service, Attempts, backup,
  original publication and three health scopes into immutable observations.
- [x] Continue only the original verified frozen prediction through actual late
  Provider observation, exact Outcome commitments and canonical Evaluation.
- [x] Reconcile full populations, canonical diagnostics, immutable reports and
  repeated zero-write completed-cycle replay.
- [x] Diagnose observed service/backup failures, apply only necessary correctness
  repairs with focused tests, and restore the authorized owned service safely.
- [x] Close continuous day-ledger and read-only research observation gaps with
  canonical consumers, if the first real Evaluation succeeds.
- [x] Record source-bound validation, operational cutoff and independent exit
  gates. Preserve scheduled failures, missing data and all historical terminals.

No model/Target change, terminal reopening, synthetic time, fallback Provider or
research qualification is authorized by this plan. Live code changes require
the installed handoff in the Runtime Runbook. Evidence-only work uses directed
checks rather than a full repository regression.

The runtime privilege envelope, scoped read-only health and frozen-work day
ledger are implemented, verified and installed in the original owned scope.
The actual scheduled backup, exact service recovery and independent restore
retain their receipts. Models, targets and prior results are unchanged.

The original timely Prediction completed actual late Outcome capture, all 31
commitments, exact Partition/Evaluation, report and zero-write completed replay.
The new installation restored the original owned service; the separately recorded
manual backup/Artifact/mirror/profile/restart/subsequent-tick chain passed. The
actual 19:00 scheduled failure remains FAIL, and all historical failures remain
visible. See [Current State](Current-State.md) and the
[immutable closure record](../archive/Real-Maturity-Operational-Closure-2026-09-10.md).

Research Validity may now consume the canonical read-only `daily observations`
projection. It has no training, tuning, selection, Provider/PIT or Alpha authority.
A single real session is descriptive only. The next natural session's Prediction
is published and pending maturity; at least three consecutive real sessions,
preferably five, remain required for sustained proof. Do not synthesize days or
wait for them during an implementation session. Tick latency and future scheduled
fires need continuing observation; the 120-second budget is unchanged.

## Operational reliability and cohort lifecycle execution

### Authorized successor activation execution

The Model-use rollover and Validity v3 activation starts from exact main
`cc12b9e469b1e482595e6290a8d137d9cbaf6817`. The user explicitly authorized
one exact-database local peer owner-maintenance window. Root execution owns all
live changes; independent reviews cover the maintenance boundary and read-only
cohort reporting. Model, Feature, Target, baseline, population and 20/500 floors
remain frozen.

- [x] Isolate the checkout and reload current installation, original database,
  frozen Predictions, old Use, calendar, protocols, HBA and closed runtime ACL.
  Preserve the actual 19:00 backup restart Provider-access failure.
- [x] Preserve the stopped-service fact, take a fresh verified backup and
  second-device mirror, then register exactly the prepared successor through
  Model owner with future validity and unchanged semantics.
- [x] Restore exact HBA bytes/mode/owner, reload, prove owner login rejected and
  full runtime privilege projection unchanged before any v3 declaration.
- [x] Reload successor owner truth, verify possible and buffered calendar
  capacity, then freeze v3 with the real declaration clock and future-only cohort.
- [x] Prepare the same-wheel daily-template handoff, preserve all existing old
  publications, activate once and inspect complete ticks plus original replay.
- [x] Run directed ownership/cohort/guard/CLI tests, static/build/install and
  documentation checks; publish source-bound evidence with independent gates.

Sep-11 already completed under its old frozen Use at entry. Sep-14 is already
published under that Use and remains its pending work. Successor v3 cannot
reclassify either session. Two completed days are still below sustained proof
and validity sample floors; no Alpha iteration is authorized.

The activation gate is YES at the bounded Sep-11 22:39+08 cutoff. Successor
`3a426d5f-702f-56fb-9563-0bc6256b558c`, restored HBA/runtime ACL, future-only v3,
72-session possible capacity and 62-session buffered capacity are verified.
Five real post-activation ticks and unchanged Sep-10/Sep-11 replay pass. Continue
natural v3 accumulation from Sep-15. The actual 19:00 scheduled restart failure
and late-entered 60-second window remain independent reliability follow-ups;
neither is upgraded by the manual activation PASS. See the
[activation evidence](../archive/Model-Use-Rollover-Validity-V3-Activation-2026-09-11.md).

### Previous reliability package cutoff

The authorized baseline is main `09917b6e7072dfc66f172bde3ef504cff511ae2c`.
The original database, restricted service, published Predictions and immutable
v1/v2 protocols retain their identities. No Model/Feature/Target/Candidate/baseline
or financial formula change is in scope.

- [x] Fetch/fix main, isolate the worktree and record fresh service, Attempts,
  deployment, backup, ModelUse and captured-calendar facts. Preserve actual stops.
- [x] Measure the current installed guard, source hashing and actual health query
  plans. Verify source/wheel/package fully at startup; reject file identity,
  profile/receipt or ACL changes before actions without repeated full-byte reads.
- [x] Bound the research-disposition receipt query with existing indexes while
  retaining complete daily populations, failed history and explicit denominators.
- [x] Extend the existing calendar Capture/normalization path and collection
  admission with an exact bounded calendar request, duplicates and SourceGap
  handling. Never infer open days from weekdays. Preserve old pending plans.
- [x] Prove v2 capacity failure from actual Provider calendar and exact Use
  lifetime: 12 eligible sessions / at most 384 observations against 20/500.
- [x] Subsequently completed by the ModelUse rollover recorded in Current State:
  register an explicitly authorized successor
  experimental use through its owner, with the same Model/Feature/Target/baseline,
  a future valid_from and a bounded lifetime. Only after actual calendar capacity
  is known, freeze v3 with unchanged 20-session/500-observation floors and explicit
  ten-session downtime and 20-percent missing-observation planning buffers.
- [x] Implement generic lifecycle/calendar/observation feasibility and strict
  old/new cohort reporting; frozen v1/v2 bytes and old Evaluation metrics stay
  unchanged. Future calendar refresh is bounded within the existing service.
- [x] Complete controlled backup/restart receipts and subsequent-tick proof;
  classify scheduled versus manual recovery without rewriting failed fires.
- [x] Run affected contracts (including admission regression if extended), static,
  build, isolated install and source-bound evidence checks. Fresh backup, prepare,
  drain, preflight and activate only the frozen tested wheel; observe multiple
  actual ticks with the unchanged 120-second stop and preserve old installations.

The [immutable installed observation](../archive/Operational-Reliability-Cohort-Closure-2026-09-11.md)
records the reliability correction, 37 completed bounded ticks, one graceful
partial tick and a complete actual manual backup/restart. A later observed
16-attempt cap starvation was corrected through a same-wheel 32-step profile
handoff; the old terminal failure remains and a complete future one-minute window
is not yet observed. Original HBA deliberately denies Model owner login;
a narrowly prepared owner maintenance request remains pending approval. No
successor is registered, v3 is not declared, and the overall cohort-closure gate
is NO. The service remains running with old frozen work and the original Use.

Stage evidence distinguishes cold preflight, warm idle, Prediction, Outcome,
Evaluation and backup/restart. Warm idle targets are p95 below 60 seconds and
ordinary maximum below 90 seconds; unavailable real stages remain unobserved.
No timeout increase, Provider batching, schema/index without measured necessity,
automatic infinite restart, model promotion or Alpha iteration is authorized.

## Completed Research Validity baseline execution

The authorized baseline is main `c61a133995c015530a992a87421e750e64f4d5ef`.
The isolated execution preserves the operational package/profile and all frozen
research identities. Sep-10 remains descriptive; new diagnostics on that session are
post-hoc and cannot enter the predeclared future cohort.

- [x] Record current service, canonical completed/pending work and backup.
- [x] Freeze an append-only, source-pinned protocol before the future cohort's
  Outcomes, including full population, formula versions, sample floors and
  unavailable slice/economic assumptions. Do not write to the old Evaluation.
- [x] Extend exact canonical observations, acquired revision/source lineage and
  temporal validation; fail closed on roster or replay mismatch.
- [x] Implement Evaluation-owned Decimal statistics, exact common populations,
  multi-session/rolling aggregation and a read-only validity CLI.
- [x] Validate walk-forward calendar/data boundaries and audit existing slice,
  economic and formal PIT readiness without training or promotion.
- [x] Run focused contracts, static/build/installed checks and documentation
  guards; retain source-bound evidence and a fresh final operational observation.

Protocol declaration uses a packaged immutable source resource and exact SHA,
with the original database clock/cohort observation retained as declaration
evidence. It does not impersonate a registered PostgreSQL Artifact: registering
new Artifact metadata through the existing owner would require the running
service's exclusive writer admission. This read-only package does not stop that
service, add a writer bypass or create a second research persistence family.

The [immutable baseline evidence](../archive/Research-Validity-Baseline-2026-09-11.md)
records the completed infrastructure and remaining real-data gates. A new actual
resource stop and QueryCanceled were reconciled; the original service recovered
without a code/profile change. A subsequent performance package has a concrete
boundary: repeated installation hashing and human-research-disposition health
receipt scans under the long-lived LaunchAgent. Do not infer a fix from the
faster interactive profile or introduce Provider batching without new evidence.

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
