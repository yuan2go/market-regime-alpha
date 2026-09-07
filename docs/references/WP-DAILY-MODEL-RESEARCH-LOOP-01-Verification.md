# WP-DAILY-MODEL-RESEARCH-LOOP-01 Verification

> **Status:** CURRENT_STATUS
> **Verification State:** IMMUTABLE_BOUNDED_RUNTIME_EVIDENCE_WITH_PENDING_FUTURE_MATURITY
> **Authority:** Bounded implementation and observed research evidence; no qualification promotion
> **Owner:** Market Regime Alpha maintainers
> **Evidence Date:** 2026-09-08

## Revision and isolation

Execution-time fetched main: `129d8bee09401277f0857eb2dd359ac428d2efca`,
tree `65cfbfd5a8dc4dc3eeb652b2462df126d335f78c`.
The original workspace remains at `10689a4db772be5a546a64448fcc6f39f6988412`
on its unrelated portfolio branch. Its modified `.idea/modules.xml` was neither
edited nor staged. Work is on `agent/daily-model-research-loop-20260907`;
no push, PR, merge, reset, clean, stash or history rewrite occurred.

Frozen implementation: `00f9da049023b04b18ccc6d76297193584e6c813`.

| Binding | Exact identity |
| --- | --- |
| Commit tree | `d066f37921502146ceb47860ec7f4ff525bce5d6` |
| Source tree | `c4026eec02d9f2ef68052d5f6a4cdd4f2e637cf3` |
| Tests tree | `3939d97ba957cac5c104341db2a57ba2b69783cf` |
| Installed source fingerprint | `933bd42c606217d38f720480acb0ba21b2d51d001d4cfb1e3c7aea8eab8a651e` |
| uv.lock SHA256 | `5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d` |
| Wheel SHA256 / bytes | `c4729baf0a8025b86ba4c848900318a27b5d3c0e4f408ae09de81b3ad3707f06` / 3816207 |
| Sdist SHA256 / bytes | `37e1d6a70c14316c804987586b0a66b5190088079bee8471a86b7afd3cc3bb40` / 3056979 |

Build and installation use a separate clean detached implementation worktree,
Python 3.12.13, uv 0.11.7, locked runtime requirements and setuptools 84.0.0.
Subsequent status/Verification edits do not change this source/tests identity.
Executable deployment templates are included in the implementation checkpoint.

## Protocol and canonical path

The [frozen protocol](WP-DAILY-MODEL-RESEARCH-LOOP-01-Protocol.md) predicts
next-session raw CLOSE/OPEN return. Prior closed-session CLOSE/OPEN is the shared
Feature; it has separate sealed-historical and actual-visible input adapters.
Actual membership, security status, exact daily bar revision, Capture/Artifact,
recorded/known time and input cutoff remain owner-verified. Future prices are
Outcome inputs, never a publication prerequisite. No overnight executable PnL,
account NAV, Sharpe, broker Fill or qualified model is claimed.

FIT learns one feature's mean/scale, frozen with the deterministic Ridge
artifact. An explicit, revocable experimental use selects an exact completed
ModelVersion. Actual-time ModelForecast uses a non-retrospective Decision and
complete eligible population. Report is a reconciled projection. Pending future
Outcomes are registered on the existing Runtime, followed by canonical Outcome,
Evaluation and report actions when mature. There is no second scheduler.

## Original database and registered upgrade

Original DB `mra_wp18q_r2_operational_20260905`, OID `287543`, cluster
`7681924516459622681`, PostgreSQL 16.15. Artifact bytes remain bound to this scope;
no recovery-copy writer was adopted. Registered `daily_model_research_v7` applied
at 2026-09-07 19:32:53.774296 UTC, receipt
`36517db7-ee70-5d66-ab90-98cbb66665e3`.

- Epoch: `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`; 194 tables.
- Baseline: `f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27`.
- Catalog: `2730fe8535261a7174dd38b87ea57037c7503a411b79a08faa88268d61951320`.
- Registered v7 bytes: `44d27a9f13d4045402b86a27f7c47150dfc67421a8fc071d8a691f0405480400`.
- Exact pre-column projection hashes for 174 historical tables unchanged:
  `0dbab61f70da510562861de847fab27a2b38f292f50d1795b9424fb5bb96a990`.

Fresh/historical schema tests preceded the guarded original upgrade. Existing v6
and registered v7 bytes were not changed after registration. The old large Run
`6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` remains FAILED in the original scope.

## Actual new baseline

Generic Run `7ef9337b-9efd-5573-8d67-f29b0a6a92e0`, specification SHA256
`a246755d1ff06bafde536e73e0a3bc526da7ac8f99cf049e53f08ee9821a471b`,
uses frozen `ec43f8aacd72b821f3da53902eeb70d25a3fe36b`, sealed archive
`fc699eea-1283-5192-b3ac-c9cbddc0da5e`, seal
`6916653e-0825-48f2-b86f-83b83b2adbc7`. Thirty actual FIT/VALIDATION sessions
(20/10), 32 deterministic members, one purge and one embargo session, rule and
Ridge alpha=1 were frozen before execution. No tuning followed the results.

All 187 actions completed at 2026-09-07 21:02:59.017591 UTC. Initial read-only
reconciliation timed out after 186 committed actions; canonical resume completed
the remainder with unchanged code, specification and timeout. Repeat inspect,
resume, report publication and replay match, with no count changes in the 19
explicitly compared tables. Six Evaluation roots and all 30 declared metric
results are estimable; this does not imply every member has an estimable Outcome.

| Output | Identity |
| --- | --- |
| ModelTrainingRun | `7ec88709-d5e9-5238-9190-85c9862cfd26` |
| ModelVersion | `fe47f296-17dc-5654-a9eb-cf149f5b01c9` |
| Fitted Artifact SHA256 | `5adb43bafae4180e351706d5407b2446410a65f618e97bf84e0efd7b59e36a53` |
| Report binding | `7106b92d-571f-58fb-90dd-c88570925113` |
| JSON Artifact | `45721d6f-7461-4b7f-8da8-da3c301a96e0` |
| JSON SHA256 | `90318517a9ff82bfa36da4f9c23b5e57ae6c742e398cb1c585dbb9398de3c581` |
| Markdown Artifact | `f55a76f5-0069-49ef-b094-1951508bcfc0` |
| Markdown SHA256 | `8a9de10ad4cae5f42e93f9ccc627ec223a0ebb277023642d9023ce410c8fea66` |

Validation per arm: 320 sampled, 319 predictions, 318 estimable Outcomes.
One canonical suspension and its prior prediction's sealed `INVALID_OHLC`
Outcome gap remain visible. Unexplained population loss is zero. Exact paired
coverage differences are zero. Rule/Ridge MAE = 0.0157121496869764 /
0.0139955173321822; RMSE = 0.0231515179329363 / 0.0210963563020224;
mean daily RankIC = -0.173538973950397 / +0.173538973950397.

The new one-feature coefficient is negative: 319 common predictions and 4929
pair/tie checks have zero reverse-order mismatches. This reverses the rule
ordering; it adds no independent ranking information. Separately, old R2's
positive one-feature coefficients preserve order (428 pair checks, zero
mismatches). The [diagnosis](../operations/Research-Diagnostics.md) retains
negative/gap members and does not call either result Alpha or untouched OOS.

## Actual-time failure and correction

Consumer `45063a0d` made 32 real daily Captures and 32 normalizations. Its
membership evidence was historical and no longer effective at DecisionTime.
Selection kept 32 UNKNOWN members; empty ModelForecast then failed before
publication. Prediction `acfa974b-9ee8-5f52-ba83-43408b2a9eac`, Runtime
`5d745e1e-088d-5099-add4-49fec094cc93`, its code/configuration and facts remain.
Canonical expired local-Attempt recovery and a new fenced failure commit
terminalized the known defect. Use `92cbd062-b3d2-55ce-add2-c4ca944b011f` was
revoked, receipt `4c68e858-a84a-4273-bee1-10b0fbbc1faa`.

The correction adds actual-date CSI300 Capture/Normalize before freezing the
new population and explicit empty-population termination without invoking a
model or creating estimates. It does not backdate membership into the old
Decision. New consumer use `60902ae3-5776-5460-91b1-90ed3bc03525` binds the same
completed ModelVersion and source `00f9da04`.

## Actual future publication and pending maturity

Prediction `e208e9d4-7d12-5929-9867-bdce54a2a874`, Runtime
`be904f26-9099-5774-aed1-36c5e4005d65`, Dataset
`dc88144f-227a-5253-bc98-7e676f229851` completed all nine publication actions.
Input cutoff/DecisionTime: 2026-09-07 21:56:40.680701 UTC; actual publication:
21:57:39.602585 UTC. Target is 2026-09-08 01:30–07:00 UTC (09:30–15:00 China).
Model registration and training knowledge cutoff both precede this Decision.
No target-window price was required or accessed to produce the prediction.

Full population: 32 sampled, 31 eligible/feature-ready/model/rule/common
predictions. `601808.XSHG` remains membership UNKNOWN / MARKET_EVIDENCE_MISSING,
although its eligibility criteria pass; it is not relabeled as known excluded.
The full 32-member JSON/CSV symbol projection preserves this member and reason.
All 31 published model values equal an independent Decimal scalar reference
using the frozen fitted coefficients/mean/scale and exact input Feature values.

| Published output | Identity / SHA256 |
| --- | --- |
| JSON Artifact | `82a05313-f033-449c-abbc-d8c7b6b2092d` |
| JSON SHA256 / bytes | `17cf11ca5d4a580b1fd0089195e204b8a9c6f93a3a6c95abd09d97e425eff9ac` / 39865 |
| Markdown Artifact | `9317f978-117b-461e-94cb-9f6143cff747` |
| Markdown SHA256 / bytes | `3b22f1d5129a55870be3b22ebed8f5e840a827333272492e191dcdda0ff96b55` / 4080 |
| Future Outcome/Evaluation Run | `7d31a1d1-410c-5246-8e04-7ed3efb11ae3` |

Repeat predict, report publication, pending settlement and replay leave counts
unchanged in all 18 named tables, including Receipt/Audit/Runtime. Completed
actions are not reexecuted. Report identities and physical bytes match;
`matched=true`, `mismatch_count=0`. The future Run has 38 planned steps and is
QUEUED/PENDING until target close. Its real mature Evaluation is NOT_OBSERVED;
the completed historical Generic baseline is separate real mature-path evidence.

Actual Capture lineage verifies 33 responses (32 exact normalized daily bars
plus one CSI300 membership response), original DB identity, Artifact hash/size,
Capture known/recorded times and frozen input references. Current canonical
calendar ends 2026-09-17. Further operation requires extending the calendar
through its canonical owner before coverage exhaustion; no weekday inference
or guessed future sessions are used.

## Targeted checks and retained failures

Tests use only disposable `mra_daily_model_loop_tests_20260908` on independent
cluster `7682058034626392615`; destructive fixtures never point at the original
DB. Locked sync, installed CLI/import, changed-file Ruff and mypy (638 source
files) pass. Build uses `uv run --with setuptools==84.0.0 python -m build
--no-isolation`. No bare Python/pytest/ruff commands are used.

The earlier 129-case focused set covers time/lineage, explicit Model use,
schema, owner integration and idempotency. Later changes have their affected
checks: FIT-only independent hand calculations, frozen requests, expired
admission, collection/evaluation Schedule separation, revocation preserving
replay, downtime abstentions and backup static-Artifact refresh. Final population
checks cover both positive 32-member inference and zero-member closure, actual
membership normalization, no retroactive visibility, no repeated Provider calls,
and 12 admission/concurrency tests. Full regression is NOT_RUN by the explicit
risk-directed execution scope; no full engineering qualification is inferred.

Retained failures include import-cycle/build packaging, schema hash contracts,
first field empty population, and real read timeouts. A test orchestration error
ran two destructive suites on one disposable DB, producing missing-table errors;
exclusive sequential rerun passes. Assertions were not relaxed. Logs and exact
incremental hashes are retained externally, including the failed commands.

The captured Evaluation access query uses `EXPLAIN (ANALYZE, BUFFERS, FORMAT
JSON)`: 4933.607 ms execution, 748.921 ms planning, 640 access members, no Cartesian
expansion. Another repeat full-activity inspection timed out during Outcome
observation. Current host I/O waits are observed; a causal explanation for old
timeouts remains UNPROVEN. No timeout increase, integrity bypass or speculative
index was introduced. Registering a new use reuses exact completed baseline
evidence and still calls the Model owner's precise validations.

## Backup refresh and observed service lifecycle

The original-scope post-publication snapshot contains 194 table projections and
2,888 referenced Artifacts, including the new completed baseline, failed first
consumer, actual Capture facts, Model use, published prediction and pending
Outcome Run. Its exported-snapshot contract binds database and Artifact roster.

- Dump: 207228289 bytes, SHA256
  `0c6e3d1243d33203c53e45af4de0898cf7a05c94b0b82f2aeff67787a68d0541`.
- Receipt SHA256: `af21c7f93f837b69527496c0858364840f0b9522eb205caa6d3b756239ca1df4`.
- Artifact roster SHA256: `8b778d0ea36fc2dd26b1e329c0bc3f32fa4942ceca8bcee0e2a259aadda33cac`.
- Inventory SHA256: `aff68566167c2661df535970350f4eead7bf0bd982fae0f50afb51218268676b`.
- Backup verification: 2026-09-07 22:12:25.050125 UTC; pg_restore readability and
  exact referenced physical-byte verification pass. No unreferenced objects.

The existing refresh procedure copies and verifies the new bundle onto the
second local physical disk; this is not offsite protection. It records subsequent
Artifact integrity observations separately from the snapshot and does not change
Capture known times. The operation profile advances atomically to content SHA256
`a78187791f50fb2c88d7f17d18b99376bd8fcafade2d110bf7b2ad55b3ade620`.
Guarded preflight and restart complete at 22:14:32 UTC. A new independent restore
of this final backup is NOT_RUN; earlier schema/restore evidence is not relabeled
as a drill on these new bytes.

Current-user service `local.mra.prospective.r2-xshg32` uses the installed wheel,
original DB and explicit daily use. Its owned first corrected process records
three ticks (30.963 / 92.639 / 17.752 seconds), actual membership capture,
publication and repeated completed progress. SIGTERM drains with exit 0; repeat
and backup checks execute while stopped, then the same label restarts as PID
77721. Three observed restarted ticks through 22:16:57 UTC take
20.634 / 17.505 / 18.785 seconds, retain the same completed prediction and pending
future Outcome, and have empty error output. Post-backup replay and published
bytes still match. The backup-refresh job retains its existing two daily wakeups.
KeepAlive is false; errors cannot create an infinite restart loop. The profile
has a 24-hour verified-backup limit, 120-second tick budget, 16 actions/tick,
30-second wakeup, 2-GiB disk reserve, four pooled DB connections plus supervisor,
and one bounded Provider attempt. Normal NOT_DUE never means successful capture.

Canonical calendar coverage ends 2026-09-17; explicit experimental use expires
30 days after registration. The [Runbook](../operations/Runtime-Runbook.md)
provides stop, status, exact-request recovery, revoke and backup-refresh commands.
Future target maturity, multiple live windows and sustained multi-day operation
remain observations to collect, not passed gates inferred from this restart.

## Executed command and log ledger

Commands use the frozen/installed environment described above. `$TEST_DB` names
only the disposable test scope, `$SCOPE` the exact private deployment, and `$EV`
this work package's external evidence directory. Python invocations use `uv run`.
Logs retain earlier failures; the table does not claim a full repository gate.

| Executed command / bounded operation | Result / exit | Evidence basename |
| --- | --- | --- |
| `uv sync --frozen --extra dev --extra postgres` at clean `00f9da04` | PASS / 0 | `mra-daily-sync-00f9da04.log` |
| `uv run pytest -q tests/refoundation/research_qualification/test_daily_prediction.py tests/refoundation/research_qualification/test_daily_collection_postgres.py tests/refoundation/research_qualification/test_daily_downtime.py` with `$TEST_DB` | 9 PASS / 0 | `mra-daily-population-final-check.log` |
| `uv run pytest -q tests/refoundation/research_qualification/test_daily_runtime_handoff.py tests/refoundation/market/test_prospective_operation_guard_postgres.py` with exclusive `$TEST_DB` | 12 PASS / 0 | `mra-daily-population-handoff-isolated.log` |
| `uv run pytest -q tests/scripts/test_check_docs_links.py tests/scripts/test_daily_artifact_refresh.py tests/scripts/test_refresh_backup_disabled.py` | 10 PASS / 0 | `mra-daily-final-docs-deployment-tests.log` |
| `uv run mypy`; `uv run ruff check` on the eight changed source/test files | PASS / 0 | `mra-daily-final-frozen-mypy.log`, `mra-daily-final-frozen-ruff.log` |
| `uv run --with setuptools==84.0.0 python -m build --no-isolation --outdir $EV/build-00f9da04`; locked separate installation; installed `mra research daily --help` | PASS / 0 | build/install/smoke `00f9da04` logs |
| `uv run python scripts/check_docs_links.py`; `git diff --check` | PASS / 0 | final documentation log and commit scope inspection |
| Installed Generic `backtest run`, followed by exact `backtest resume` | initial read timeout / 2; completed resume / 0 | `mra-daily-real-baseline-run.log`, `mra-daily-real-baseline-canonical-resume.log` |
| Installed canonical report/resume/replay closure | PASS / 0 | `mra-daily-baseline-report-replay-closure.log` and immutable report bindings |
| Installed original v7 registered upgrade-plan/apply/verify | PASS / 0 | `v7-upgrade-plan.log`, `v7-upgrade-apply.log`, `v7-schema-verify.log` |
| `$SCOPE/mra.sh archive prospective preflight` with exact profile and daily template | PASS / 0 | `mra-daily-successor-preflight.log` |
| Owned launchd guarded service; canonical membership capture and daily publication | PASS / bounded observed scope | `service-20260907T215318Z-74755.jsonl` snapshot |
| Installed exact daily repeat/report/settle/replay and independent scalar reference | PASS / 0 | `mra-daily-publication-repeat-and-scalar-second.log` |
| `$SCOPE/refresh.sh --recover-stopped` | PASS / 0 | `mra-daily-post-publication-backup-refresh.log`, refresh receipt directory |
| Read-only installed replay after backup/restart | PASS / 0 | `mra-daily-post-backup-replay.log` |
| Full repository pytest / old 936-action replay / new final-backup restore DB | NOT_RUN | Explicit limited verification scope; not inherited PASS |

Earlier red/green logs preserve schema/hash, empty population, immutable roster,
provider-failure, expiry/restart and complete positive PostgreSQL prediction
counterexamples. A failed combined population test used an unsupported fixture
classification; the collection fixture was corrected to its declared CSI300
product and rerun successfully. Evidence helper SQL/serialization errors were
read-only and retained alongside their corrected final outputs.

## Recoverable incremental evidence

External bundle logical name: `daily-model-research-loop-20260907`. Its
`final-incremental-index.json` SHA256 is
`fc366ca26fcc6edcd8c7bd5eb7ab654a5adf3ceb1c910dc946fd295ed3255043`.
It names 457 files / 49551021 bytes by relative path, size and SHA256, covering
this package's inputs/protocols, installed artifacts, retained failed logs,
original upgrade receipts, complete baseline reports, daily prediction/report
bytes, scalar/roster checks, capture lineage, configuration/deployment identities,
service-log snapshots and final-backup receipts. Copies on two local physical
disks match; no credential/environment-secret file is included. This is a
regenerable operational index, not a new business Authority. Old large evidence
bundles were not repackaged. The two database backup copies remain separate from
this smaller incremental evidence bundle.

The final remote fetch still resolves main to `129d8bee…`; original-workspace
HEAD and the unrelated `.idea/modules.xml` SHA256
`1f4d49d435a7355fdfe18d629e177c419c2464d56446a5200dbed317dba6b040`
are unchanged. The containing documentation commit is additional to the frozen
implementation and does not claim to be its own verification subject.

## Evidence boundaries

Historical baseline = EXPLORATORY_RETROSPECTIVE. Daily publication =
EXPERIMENTAL_SHADOW, unqualified. V2 episode qualification does not reclassify
old V1 economics. Formal Provider/PIT remain blocked; formal OOS is NOT_RUN.
ALPHA_PROVEN = NO; PRODUCTION_ADMISSION = NO; full Runtime cutover is unauthorized.
WP18Q's original true-due gate is independent of the new post-close collection.
