# WP-18Q-R2 Operational Recovery and Generic Runtime Verification

> **Status:** CURRENT_STATUS
> **Verification State:** IMMUTABLE_EXACT_SCOPE_LOCAL_EVIDENCE
> **Authority:** Exact-scope local engineering and recovery evidence; no research or Production admission
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-06 UTC (2026-09-06/07 Asia/Shanghai)
> **Baseline main SHA / tree:** `6dc989331d357a802ae5840b5ae5ef76f32a29cf` / `27a14ed7cadcef7d320c3751e4dea171740d5257`
> **Implementation SHA / tree:** `09561b25d7f6bf4168abcb4c75d1654587a680a8` / `b6a7f1406d9c4ea11e0f9d5397f9a66f8bb0137d`
> **Source / tests tree:** `b888df8eef0bf026fed32dbdf02fa467ec233063` / `2fb2815cf249164757dc253e311c14f029a4e1bb`
> **Code Evidence:** `src/market_regime_alpha/interfaces/backtest_actions.py`, `src/market_regime_alpha/interfaces/prospective_service.py`, `src/market_regime_alpha/infrastructure/postgres/queries/backtest_execution.py`, `tests/architecture/test_wp_specific_execution_retirement.py`
> **Containing documentation commit:** Reported in delivery; documentation-only changes do not claim to contain their own SHA.

## Decision and scope

This is the single R2 continuation record under the existing
[Design](WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Design.md)
and [Implementation Plan](WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Implementation-Plan.md).
The [evidence index](WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Evidence.json) binds
recoverable external originals, commands, exits, database scopes and content
hashes. All 367 indexed original files were physically rehashed after index
creation. Index SHA256 is
`3202a12434efe7b60aeda763afd9b866b05add97cc819b875bcffdfe2efc36f5`.
It is an index, not a business Authority. Earlier immutable Verification
and failed results are preserved.

Post-retirement implementation 09561b25 passes all local engineering gates,
including 4,058 full-repository JUnit cases with no failures, errors or skips;
independent installed-wheel smoke and final exact recovery replay also pass.
The Backtest platform is engineering qualified in the explicitly completed
recovery scope. This does not relabel the original operational Run as completed.
The frozen total exit still requires an actual due Runtime Attempt; the observed
window is NOT_DUE. Bounded start/stop/restart does not prove sustained collection.
Recovery-copy completion never rewrites the original database's terminal failure.

## Restored workspace and implementation chain

The original user worktree remains on `agent/wp-portfolio-execution-authority-01`,
HEAD `10689a4db772be5a546a64448fcc6f39f6988412`, with its unrelated
`.idea/modules.xml` modification untouched and unstaged. Local refs, worktrees,
uncommitted work, processes and external originals were inspected before fetch.
The previous R2 and economics worktrees remain intact. No reset, clean, stash,
push, PR creation, merge, broker operation, operational migration or service
installation occurred.

One branch, `agent/wp18q-r2-runtime-closure-20260906`, starts at the fetched
baseline. Its logical commits are:

| Commit | Change |
|---|---|
| `3abdd5e2` | Generic Runtime progress projection with explicit non-admission boundary |
| `5668cde3` | Reject missing/damaged Runtime bindings; preserve last Attempt diagnostics |
| `e322926f` | Foreground lifecycle for the existing prospective continuation owner |
| `1e48ed4d` | Drain shutdown without signal-handler lock reentry |
| `b69a1e28` | Exact finite Decimal CLI comparison serialization |
| `09561b25` | Gated WP-specific execution retirement and retained historical fixtures |

The frozen campaign writer remains separately at
`f247ca5de6d5be91c3c89036f20e77242eb15b53`, source tree
`1efd732569958793f1ac9d70c25046cbd23fca7f`. Its clean worktree was not changed.
Its 3,740,800-byte wheel has SHA256
`89220982b4120ac6a676fbbf6c33b39214075bf57b0b5f314f8e6ff84545274b`;
1,055 packaged Python members match that source. Resumes use that frozen writer,
not silently substituted current code. Its environment fingerprint is
`6bae230137fa1d3b8a840f646e28b85bad6eb3b095847102619cd36342d0bf58`.

Current economics V2 remains the completed, independently funded and fully
liquidated hypothetical episode model from its
[own Verification](WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Verification.md).
No financial algorithm, formula version, strategy threshold or frozen campaign
parameter changes in this continuation. Frozen R2 V1 results retain their old
meaning and are excluded from V2 correctness evidence. Target horizon is not a
trade holding period; neither version proves actual A-share executability.

## Database and Artifact identities

All observed servers are PostgreSQL 16.15 with durable fsync and synchronous
commit. Machine-local connections and Artifact-root paths live only in the
external inventory, without credentials in shared configuration.

| Logical scope | Exact database | OID | Cluster identity |
|---|---|---|---|
| Original current R2 research scope | `mra_wp18q_r2_operational_20260905` | `287543` | `7681924516459622681` |
| Faithful pre-failure recovery, subsequently completed | `mra_wp18q_r2_continuation_restore_20260906` | `117559774` | `7682058034626392615` |
| Independent post-completion restore | `mra_wp18q_r2_completed_restore_20260906` | `118013570` | `7682058034626392615` |
| Isolated performance restore | `mra_wp18q_r2_performance_restore_20260906` | `120273500` | `7682058034626392615` |
| Exact read-only WP-17P history | `mra_economics_correctness_v5copy` | `98520357` | `7682058034626392615` |
| Pre-retirement disposable tests | `mra_wp18q_r2_continuation_tests_20260906` | `117399107` | `7682058034626392615` |
| Final disposable tests | `mra_wp18q_r2_hard_cut_tests_20260907` | `134217859` | `7682058034626392615` |
| Installed-wheel fresh schema smoke | `mra_wp18q_r2_installed_wheel_20260907` | `124884712` | `7682058034626392615` |

The unavailable pre-R2 operational scope remains
`OPERATIONAL_EVIDENCE_DISCONTINUITY`. Recovered immutable history, new capture
times, new Archive identity and prospective start do not recreate continuous old
history. This continuation performs no operational upgrade; earlier controlled
upgrade records remain exact historical evidence, not a new original-DB upgrade
claim.

The target epoch remains `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`, baseline 1:
192 tables, four views, 1,365 indexes, 1,834 constraints, 147 functions and 386
non-internal triggers, totaling 3,929 catalog objects.

| Checksum | SHA256 |
|---|---|
| Baseline | `f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27` |
| Catalog | `d14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1` |
| Seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| Reference vocabulary | `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b` |

Target migrations, registered operational upgrades, seeds, legacy migrations,
`pyproject.toml` and `uv.lock` are unchanged from the baseline. No migration was
invented for retirement. Dependency lock SHA256 is
`5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d`.

## Real frozen campaign and retained original failure

Run `6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` uses sealed canonical Archive
`fc699eea-1283-5192-b3ac-c9cbddc0da5e`: 534 captures, 116 actual sessions and
32 deterministic instruments, including daily/intraday/calendar/membership
Authority. Physical bytes, SHA/size, lineage and Archive reconciliation are
verified; raw files alone do not confer Authority.

Specification SHA256:
`4f98cb6949da19c3cf7517cc14846ce6f4aed61f89ed0f06640f561cfa1f968f`.
Definition SHA256:
`05d0db442105251914d41ef075fd0b287d974908ed180102119b379b45635701`.
The frozen 936-action roster SHA256 is
`647ba0ba996a483371fa4127c1880b01b57bf266f42529b5d9cd244343a78bfe`.

| Fold | Purpose and actual frozen roster | Dependency |
|---|---|---|
| `a368b04a-8803-5469-9a5a-84b032d7b8be` | FIT: 20 sessions, January 5–30 | Supplies fold 2 |
| `4b5ad908-8828-5ea9-83ec-282acf6e6c6b` | Validation: 10 evaluated sessions plus one purge and one embargo, February 2–25 | Completed fold 1 FIT |
| `1d84cbbf-9b86-5e38-90a7-29b2625d2256` | FIT: 34 sessions, January 5–February 27 | Supplies fold 4 |
| `f6c284f3-7571-5a16-9dce-a844d810c227` | Validation: 10 evaluated sessions plus one purge and one embargo, March 2–17 | Completed fold 3 FIT |

The union has 44 actual FIT/VALIDATION trading sessions, not a sum that duplicates
overlapping FIT history. The four frozen arms are `rule_current_context`,
`ridge_current_context`, `rule_context_observational` and
`ridge_context_observational`; comparison-compatible Portfolio/Risk/Cost and all
parameters remain unchanged. No post-access tuning, member removal or OOS
relabeling occurred.

After exact identity, backup, disk, active-attempt and single-writer preflight,
canonical resume on original OID 287543 terminates a Fold Evaluation action
`59f66bd4-0e2e-57e5-b9fd-384cb4827202` after PostgreSQL `QueryCanceled`.
Runtime Run `77e28784-8b37-5dc3-8f61-964891ff8a26`, Attempt
`1a0dd2a1-8f1c-46b0-a614-9060c9cafecd`, remain `FAILED_TERMINAL` with
`BACKTEST_ACTION_FAILED`. Five preceding steps committed; EVALUATE failed and
bind-evaluation remains pending. Progress observes 808 succeeded actions, one
failed and 127 unregistered. It does not infer success from a process or log.

The authorized attempt changed 16 explicitly indexed tables; 176 whole-table
ordered hashes and the complete 2,770-Artifact roster stayed unchanged between
the two original-DB backups. This was not a zero-write resume. Failed earlier
Runs, OPEN Evaluations, receipts, audit and actual times remain negative evidence.
No terminal Runtime row was manually reopened or transplanted from a copy.

A faithful pre-failure restore under separate OID 117559774 uses the same frozen
writer and completes all 936 actions at 2026-09-06 15:39:52.248466 UTC:
296 Datasets, 296 Decisions, 9,436 Outcome revisions, four ModelVersions and 44
Evaluations. Its post-completion backup independently restores to OID 118013570
and replays the completed Run. This is real exploratory execution in a recovery
scope, not original-DB completion and not a new parameter search.

| ModelTrainingRun | ModelVersion | FIT samples |
|---|---|---|
| `299c08be-8bb8-5971-ba1b-085758a5e66f` | `d1472b14-3f9e-5cdb-88ab-dce3297c27a0` | 1,085 |
| `c78e71b7-30ff-533f-9654-dedf4cd8c41e` | `ff9d7927-2f89-577a-a7d5-cf0755731242` | 1,085 |
| `d64deb4c-5b11-53ff-8ee9-46261449048e` | `62cfcddd-2baa-55dc-935c-177d74be0aca` | 640 |
| `de4db090-fbd4-521e-a61d-8f807530e3d9` | `3d4d4204-6b38-542f-9df4-450e0b16e023` | 640 |

Canonical reload verifies completed FIT, training knowledge cutoff, Outcome
known-time, Model registration before strictly later Validation Decision/Forecast
generation, both purge/embargo dependencies, Feature/Target lineage and the
frozen environment fingerprint. Full source and Evaluation ID rosters remain in
the indexed canonical proof, not replaced by these counts.

## Standard report, comparison and exact replay

The canonical 37-metric declaration produces 608 metric entries: 511 estimable
and 97 typed NOT_ESTIMABLE. Eighty-eight preserve `EXPECTED_ROSTER_MISMATCH`;
nine Context slices preserve `INSUFFICIENT_OBSERVATIONS`. Examples retain
declared/actual 320/319, 1,088/1,085, 320/315 and aggregate 640/634.
No denominator, missing observation or failed member is rewritten to obtain PASS.

Data coverage/missingness/SourceGap/unavailable, Candidate IC/ranking/selection,
Context, Signal/Forecast, Portfolio/Risk, costs/economics and fold/time/available
Context slices are present with their declared formula identities and reasons.
Report consumes reconciled Authority/Evaluation and does not read raw bars or
create another financial calculation. Canonical Alpha funnel attribution is
`NOT_DETERMINED / NO_CANONICAL_BOTTLENECK_ATTRIBUTION`.

Report binding `66b20bc7-f8c9-51af-bb68-9cbea75d9322` uses schema
`mra-backtest-report-v1`, renderer 1, Evaluation roster SHA256
`e2bc7bf98fcdcfe409b7555135b2a22fdf6936f31be331c394a51aa0a459e52c`
and projection SHA256
`5787bef4955f72eb7ab80ad1c252a672babe2f9f09de51ff78176f92e35c0d7d`.

| Artifact | Identity | Bytes | SHA256 |
|---|---|---|---|
| JSON | `08ee8620-0a6e-4728-8aa5-db7a151e2abd` | 517,803 | `c6ee9f51216693ece843a3e1578ac76e4a69e69ec6a19bf556e36c92eb406a88` |
| Markdown | `cda9c72c-c3bf-4434-a0d7-368f076b8568` | 517,800 | `6d2fcf61b5c999a5e4161d2a2e292e1ad1ec3ac1d0e5ff074cd2c30133a664f9` |

Repeated publication, inspect, resume, replay and self-comparison are bracketed
by all 192 table hashes and complete Artifact identity/physical snapshots.
Completed actions do not execute again. Run/Dataset/Decision/Outcome/Model/
Evaluation identities and report bytes remain unchanged, with matched=true and
zero mismatches in the completed recovery scope.

Independent completed small Runs `99227101-fabe-5244-a9ab-e2ebe492b22d` and
`b8c2fadc-5ac1-5585-bc7c-e131eede53a3` compare LIKE_FOR_LIKE: 178 entries,
154 estimable zero deltas and 24 typed non-estimable comparisons, separate Model
identities and no selected winner. Comparing incompatible large/small frozen
scopes is rejected for dependency/cost/risk/formula identity differences.

Actual CLI comparison exposed a Decimal JSON TypeError (exit 1); the independent
34-digit regression and three non-finite refusals precede the repair. Finite
Decimal values now serialize as exact strings. No float conversion, rounding,
formula change or metric recomputation was introduced.

## Prospective continuity and operational lifecycle

The existing owner chain remains CONTINUOUS_RESEARCH → PostgreSQL clock →
previous-generation reconciliation/overdue terminalization/planning gaps → exact
TradingSession → immutable generation/slices → Runtime Run/Step/Attempt/lease/
fence → Market/Artifact effects → terminal/revision/health. Outcome path and
point checkpoint windows remain distinct. Unknown Provider effects are reconciled
rather than blindly retried. No second scheduler or business clock was added.

Foreground `mra archive prospective serve` serially invokes that same continuation
owner, closes composition between wakeups and drains SIGINT/SIGTERM. Its wakeup
interval and monotonic stop responsiveness are process lifecycle only. Independent
signal-in-lock subprocess counterexamples first time out; a boolean-only signal
handler fixes lock reentry without interrupting an active owner effect.

After original-DB backup, 851,366,215,680 free bytes, exact OID/cluster/owner,
matching physical Artifact roster, zero active Attempts and an operator advisory
lock, a real original-DB service invocation drains SIGTERM with exit 0, then
restarts for one bounded wakeup with exit 0. PostgreSQL observations at
2026-09-06 17:06:02.075905 and 17:06:03.726486 UTC show due=0, no new generation,
no planning gap and no recovered Attempt. Independent recovery-scope lifecycle
proof at 16:54:19/20 UTC also exits 0.

Series `r2_xshg32`, generation `1303080a-8a96-51dc-9021-31a9250c85d9`, has
288 NOT_DUE slices, zero captured/missed/overdue observations. First due is
2026-09-07 06:40 UTC; no future wait was performed. The Outcome path starts
September 8 at 01:30 UTC and ends at 02:30; its checkpoint window is 02:30–02:31,
not an interchangeable timestamp. No system service was installed. Bounded
lifecycle proof is not sustained collection or real due capture. Design §13's
actual-Attempt requirement therefore still blocks total exit.

## Consistent backups, restore and inventory

Seven prior dump/inventory bundles and their physical Artifact copies were
reverified against actual bytes, hash and size. The following new bundles use
an exported PostgreSQL snapshot plus the exact referenced Artifact roster;
all 192 tables use full-row JSON text ordered under C collation. Unreferenced
objects are explicitly excluded and reported, not silently equated with references.

| Bundle | Source OID | Dump bytes | Dump SHA256 | Artifacts |
|---|---|---|---|---|
| Pre-resume | 287543 | 192,112,599 | `2575fdb47176bb90f2a8f4fc7656afea8b761db5410c32213a38e44951e83c7b` | 2,770 |
| Completed recovery | 117559774 | 309,994,856 | `588f09b6fdd34e1d30ca93285eabba47c2712da70ef30d723096c223aaec947f` | 2,780 |
| Original pre-service, preserving failed resume | 287543 | 192,587,834 | `013f366faaad245d695eb7843b2b9a235f4db4e8280cfa81e875a5e6ee93b2d1` | 2,770 |

`pg_restore --list`, complete archive decode, physical Artifact count/hash/size
and missing/extra checks pass. A fresh pre-resume restore matches its baseline
before continuation; a different fresh completed restore matches all 192 tables,
2,780 Artifacts, five Archives and 16 Backtest reconciliations. Completed WP17P
and new large campaign replay both match. Failed other Runs remain failed; an
integrity match is not falsely called completed replay.

At final 09561b25, the original R2 `evidence verify` first exits 2 with
PostgreSQL QueryCanceled. A read-only diagnostic rerun through the same canonical
Application, with unchanged source and timeout policy, completes in 577.75
seconds: 2,770 referenced Artifacts, no missing/extra bytes, five Archives and
16 Backtests have zero integrity mismatches. Original large-Run execution remains
FAILED and completion replay remains false with `EXECUTION:FAILED`. The initial
timeout is retained; its physical slowdown cause is NOT_DETERMINED. The original
inventory now binds the successful physical/owner scan and pre-service backup.
The initial CLI failure log did not record its command revision; the final
instrumented rerun explicitly runs clean 09561b25.

The final completed-copy restore-check at 2026-09-06 17:32:38.580312 UTC again
returns matched=true / mismatch_count=0 and is indexed as the latest restore
drill for backup 588f09b6. No source operational database is overwritten.

Inventory is regenerated from canonical facts and verified local backup,
integrity and restore records. Database logical roles, exact identity, epoch,
catalog checksums, Artifact-root binding, Archives/generations and timestamps
remain machine-local read-only observations. There is no business FK or evidence
maturity mutation. Backup originals and report originals are content-indexed
outside Git; source, recovery copies, new scope and disposable tests stay distinct.

## Real-scale performance and retained failures

Fifteen actual EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) plans cover Backtest action
observation/batched Runtime lookup, Dataset, Candidate, Outcome settlement and
batch verification, 1,085-row Model/Evaluation inputs, report projections,
calendar horizon and prospective due lookup. Queries preserve bounded identity
rosters; no Cartesian amplification or missing index justified another redesign.

The frozen recovery completes its remaining 128 actions in 398.70 seconds,
419,506 Cursor.execute calls, 5,964 committed UoWs and 241,631,232-byte peak RSS.
Global UoW p95 is 0.06194 seconds; one Evaluation write takes 13.68 seconds,
exceeding the predeclared 10-second cap. That budget failure remains recorded.
Disk delta is a shared-environment observation, not exact isolated DB growth.

The already implemented current Evaluation owner computes outside its final
write transaction. In the isolated performance copy, new component Evaluation
`9f089d7e-333b-58d0-b518-8c3643de9a51` reproduces all 15 canonical values/states/
counts/reasons of reference `123952d2-bc83-5d29-bba2-0c7d75f5c5c9` for 1,085
members: 116 Cursor.execute calls, 9.58 seconds total and 7.54 seconds final write,
meeting the same 10-second cap. This is a separately identified owner component
drill, not replacement Backtest execution or repair of the original failed Run.
The indexed source-tree comparison defines reuse on the final retirement source.

Model preparation independently loads each of 34 Dataset definitions once,
reproduces all 1,085 frozen samples/linear rows and reloads registered training
input without Dataset rematerialization. Original reads previously timed out and
later indexed plans return sub-millisecond rows; exact cache equivalence and the
physical slowdown cause are NOT_DETERMINED. The original backup's long external
sort/read duration remains an observed operational limitation, not hidden success
latency or proof of an index repair.

## Gated retirement and historical compatibility

Deletion begins only after `hard-cut-preconditions-pass.json`: clean b69 full
4,066-case regression, focused 51, static/type/architecture/docs/build,
wheel/sdist source bytes and independent installed replay/report/compare/schema
smoke; exact historical equivalence; real completed 936-action recovery campaign;
standard report/replay; verified post-completion backup/independent restore; and
prospective lifecycle proof with no current due window. Original failure is
preserved but is not an additional Design §12 veto. Design §13 still blocks total
exit; no blanket future-window requirement is silently used to stop other work.

Ten public WP-specific execution/catalog/planning modules are removed. The
Generic executor, Model/Evaluation/Report owners and Prospective Application remain
the execution path. No generation dispatch, delegating facade or availability
fallback is retained. Immutable reason/identity strings and schema names are not
new executable routes; Legacy/schema/full Runtime cutover is outside this change.

The pure historical catalog moves byte-for-byte into a private test fixture.
Archive seed/helper function bodies and historical catalog assertions remain
unchanged. Passing dedicated WP-executor tests are retired with their bypass;
Generic canonical, owner, historical and economics tests remain. The Decimal
literal-zero boundary is explicitly moved to Generic materialization. An omitted
fixture module-alias import causes two retained PG collection errors; that failure
is preserved, the import is repaired, and 42 canonical focused plus 24 pure/
retirement cases pass before freezing 09561b25. Import guards cover absolute,
relative and aliased imports as well as installed module absence.

WP17P exact completed Run `8f7b6def-9c63-533e-9777-a5a6c57866e0` and 398
Artifacts pass private-decoder → FrozenBacktestRun → Generic reconciliation-only
verification, without writes. WP18 proves only exact definition/specification
equivalence. Unknown legacy-shaped IDs, missing specifications and changed hashes
fail closed. Old result/Artifact/report identities and bytes are preserved.

## Final engineering commands and evidence reuse

All Python commands use uv. Qualification runs in a clean detached 09561b25
worktree with the new disposable durable database above and the explicitly bound
read-only historical database. No skips/xfails, lowered assertions or research
threshold changes obtain PASS.

The indexed command ledger records full argv, exit code, time, JUnit counts and
log hashes for locked sync; focused and full pytest (including PostgreSQL,
refoundation, platform, concurrency/fence/unknown-commit/recovery and fresh/schema
compatibility); Ruff; mypy; architecture/import/docs/navigation; build; installed
distribution smoke; query plans; report/replay; and git diff --check.

The earlier 1e48 separate runs passed 647 focused, 1,010 refoundation, 33 platform
and 288 PostgreSQL cases. Its full run was explicitly interrupted (exit 2) when
actual CLI comparison exposed the Decimal defect; 482 completed cases do not
constitute a full PASS. b69's complete 4,066-case run is a deletion prerequisite,
not inherited as final retirement qualification. Initial missing-history skips,
RED tests, collection mistakes, timeouts and performance-cap failures remain in
the index with their exact repair/rerun boundaries.

Final 09561b25 qualification records these actual commands and exits:

| Command / scope | Result | Exit |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | Python 3.12.2, 61 locked packages | 0 |
| `uv run pytest -q` with the indexed focused roster | 78 cases, zero failures/errors/skips | 0 |
| `uv run pytest -q` (full repository) | 4,058 JUnit cases, zero failures/errors/skips; 1,967.38 seconds | 0 |
| `uv run pytest -q tests/architecture tests/scripts/test_check_docs_links.py` | 41 cases | 0 |
| `uv run ruff check .` | PASS | 0 |
| `uv run mypy` | PASS, 624 source files | 0 |
| `uv run python scripts/check_docs_links.py` | PASS | 0 |
| `uv run python -m build --outdir …` | wheel and sdist | 0 |
| `git diff --check` | PASS | 0 |
| Independent wheel install, canonical smoke and actual CLI compare | PASS, 936 actions, stable reports and 178 comparable entries | 0 |
| Final recovery `evidence restore-check`, report/publish/resume/replay | matched=true, mismatch_count=0 | 0 |

The full run includes 993 refoundation, 33 platform, 288 PostgreSQL-persistence
and 34 architecture cases. The change from b69's 4,066 to 4,058 is accounted for
by exact removed/renamed WP-executor and added retirement/Generic case identities
in the index; passing bypass tests retire with their executable modules.
No failing canonical assertion is deleted.

Wheel SHA256 `99d23c772fc21c9ed6f43637eaaad79fd3e7fd0a728a5319a283274be1b6068f`
(3,726,838 bytes) and sdist SHA256
`585a948f534df6038834882bb6c2490c4e5b7d65be016ed71a76aa48e8f3f04e`
(2,983,658 bytes) each match all 1,166 tracked Python/SQL package members.
Independent installation outside the checkout proves all ten retired modules
absent, the separate V2 hand case, fresh schema, exact large replay and report
hashes. Actual installed CLI comparison returns 154 exact zero Decimal deltas
and 24 typed non-estimable entries; no winner is inferred.

The containing documentation-only commit changes none of the verified source,
tests, schema, dependencies or runtime configuration. Its links/navigation and
scope are checked again; it does not claim that the wheel contains later prose.
Remote Actions returns enabled=false:
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, never PASS.

## Remaining operational and research boundary

Original Run 6318 remains failed. A future operational continuation must preserve
that terminal identity and use an explicitly controlled supported successor or
recovery-scope adoption; no SQL reopening, row transplant or semantic replacement
is implied by this delivery. Original physical read latency requires further
operational diagnosis before assuming the recovery copy's timing applies there.

No actual due prospective Attempt occurred, no sustained service history was
observed, and no future window was awaited. These limits remain explicit even
when all local engineering and retirement checks pass.

```text
RETROSPECTIVE = EXPLORATORY_RETROSPECTIVE
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
FULL_RUNTIME_CUTOVER = NOT_AUTHORIZED
PRODUCTION_ADMISSION = NO
```

## Exit disposition

```text
GENERIC_CAMPAIGN = PASS_IN_COMPLETED_RECOVERY_SCOPE
REPORT_COMPARE_REPLAY = PASS
PROSPECTIVE_CONTINUITY_ENGINEERING = PASS
REAL_DUE_ATTEMPT = NOT_DUE / BLOCKED_BY_TEMPORAL_WINDOW
CONTINUOUS_SERVICE_PROOF = BOUNDED_STOP_RESTART_ONLY
BACKUP_RESTORE_RECOVERY = PASS_EXACT_RECORDED_SCOPES
HISTORICAL_COMPATIBILITY = PASS_EXACT_SCOPE
WP_SPECIFIC_HARD_CUT = PASS
FINAL_REVISION_ENGINEERING_VERIFICATION = PASS_LOCAL_AT_09561b25
BACKTEST_PLATFORM = ENGINEERING_QUALIFIED_IN_COMPLETED_RECOVERY_SCOPE
WP18Q_EXIT_GATE = BLOCKED_BY_TEMPORAL_WINDOW
RESEARCH_EVIDENCE_CEILING = EXPLORATORY_RETROSPECTIVE
FULL_RUNTIME_CUTOVER = NOT_AUTHORIZED
PRODUCTION_ADMISSION = NO
```

Minimum remaining frozen-exit evidence is a real PostgreSQL-due,
Runtime-claimed prospective Attempt at an available window. No such window was
available in this execution; no future wait or proof substitution is authorized.
Long-lived service installation and original failed-Run successor/adoption are
separate operational decisions, not silently performed by this delivery.


## 2026-09-07 research operations activation — exact revision addendum

This append-only section continues the existing R2 evidence chain. The preceding
record is preserved byte-for-byte and remains scoped to 09561b25; its original
index SHA refers to that Git revision. It is not inherited by changed source.
The new logical bundle is `wp-research-operations-activation-01-20260907`.
Its per-file index, portable backup and verification receipt identify external
originals; no credentials or machine-local paths are stored here.

### Restored scene, scope and frozen implementation

The original worktree remains on `agent/wp-portfolio-execution-authority-01`,
HEAD `10689a4db772be5a546a64448fcc6f39f6988412`, with the unrelated
`.idea/modules.xml` bytes and staging state preserved. Its SHA256 is
`1f4d49d435a7355fdfe18d629e177c419c2464d56446a5200dbed317dba6b040`.
Prior R2/economics worktrees and the frozen f247ca5d writer are preserved.
Inspection preceded the authorized fetch. Latest fetched starting main is
`85d0080ab3bf14fade5b91e8ef98aa9a16e0c2b2`, tree
`533a1ed09b6bc2e1a805ce6e1864b20d670b0bac`; its source/tests equal 09561b25.
The unrelated local portfolio commits were neither overwritten nor mixed into
this correction.

The single branch `agent/research-operations-activation-01-20260907` contains:
`d090ae37` scoped read-only database/research diagnostics;
`59c8b04d` whole-call Provider resource bounds; and
`f55af294` guarded lifecycle, gap-aware schema and canonical recovery; and
`4c764b3d` repairs the SQL adapter boundary and exact registered migration
roster after the first complete regression exposed three failures.
No push, PR, merge, broker action, system-service installation, original-database
migration, writer replacement, successful-row copying or historical rewrite occurred.

Final frozen implementation:

- commit `4c764b3d01c08b1cb2de9949cb3a6aa7f534bc72`;
- tree `8b9e78a7672d12080fb35691b528a01cc541f347`;
- source `968ab39e340adf16b58aaa030dfe6e420d5760b8`;
- tests `24fa73a27213407c8749769112cba7da694c0d49`;
- scripts `b176ebab0ad776efad4c768b4c0b50dd72a13dc7`;
- uv.lock SHA256 `5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d`;
- package Python/SQL fingerprint `2a17efbe1b778659ef362a72ed8b40514f2e17fb3593fe5db832dcdc59b0e970`.

A clean detached worktree and separately named durable PostgreSQL 16.15 test
database qualify this version. Later documentation-only changes bind this tested
source/tests/dependency identity; the Verification does not contain its own commit.

### Proven defects and bounded corrections

1. Frozen comparison ordinal 2 could be the first successful observation after
   a canonical Provider gap, but old schema required ordinal 1. Success/gap/success
   had the analogous successor conflict. Independent canonical PostgreSQL RED
   cases proved both. The existing validator now permits skipped ordinals only
   when every skipped same-checkpoint window has a canonical negative terminal
   observed no later than the successor. It preserves frozen ordinals, latest
   actual predecessors and all prior hashes; it creates no synthetic observation.
2. Per-row Provider timer resets did not bound a whole effect or its response.
   One deadline now covers deferred login, query and row iteration; finite row
   and exact serialized UTF-8 byte budgets close resource use. Unsupported signal
   environments and an already-owned alarm fail before an effect. Successful
   Provider bytes are unchanged; SDK attempts remain one.
3. Supervision loss, stop signals, source drift or expired backups could leave
   later owner actions unguarded. The existing continuation checks process
   permission/resources before each owner boundary/claim. It drains committed
   work, then stops without blind external retries. Unknown external effects
   retain their explicit reconciliation error.
4. A matching dump did not alone authenticate rewritten backup metadata.
   A pinned receipt now binds the same-read inventory bytes, source scope,
   snapshot time and Artifact roster. Both snapshot and verification age count.
5. Public manual prospective write shortcuts and the legacy prospective CLI
   child could bypass preflight. They now refuse before connection/business
   work and direct operators to guarded `serve --operation-config`.
   Non-prospective legacy commands retain their behavior.
6. Strict health before recovery rejected a partially registered capture-Run
   roster and prevented continuation from repairing it. Service startup records
   OWNER_RECONCILIATION_PENDING, invokes canonical continuation, then checks the
   full roster strictly. A real disposable-PG interruption/backup/restart case
   passes with all 192 tables unchanged on repetition.

There is no new Runtime, scheduler, business registry, Evaluation truth, model,
formula or research threshold. Schema baseline 001 and every registered v1–v5
bundle retain their original bytes. New immutable
`002_prospective_revision_gap.sql` has SHA256
`bd5978ae2ccfd56a9d117c41e13e0a8f7c76fbdd4d83d4aa1b32757dbe753063`;
registered upgrade `wp18q_prospective_revision_gap_v6` changes catalog
`d14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1` to
`233c60c2b8b6efca4682f92fff8acbe85895a967cef0e11f7838f572e6ed69db`.
Fresh bootstrap applies exact 001+002; older registered upgrade routes retain
their exact historical targets. Current writer startup rejects v5 until an
explicit controlled upgrade. A successful read-only diagnostic is not schema
execution admission.

### Actual-time lifecycle and operational scope

Original `mra_wp18q_r2_operational_20260905`, OID 287543, cluster
7681924516459622681 remains the authorized original scope with the large Run
FAILED. Completed recovery OIDs 117559774/118013570 remain distinct evidence.
No recovery copy is adopted as the future writer. The proposed minimum path is
a separately approved exact original v6 upgrade, fresh scope-bound backup/profile,
and guarded startup. The read-only plan is an expiring proposal, not approval.

New isolated lifecycle drill: `mra_operations_lifecycle_drill_20260907`,
OID 142930962, cluster 7682058034626392615. Independent completed drill:
`mra_operations_completed_drill_20260907`, OID 144400596, same cluster.
Both controlled v5→v6 upgrades preserve every ordered row of all 189 business
tables and exact Artifact bytes, with changes confined to three schema metadata
tables. They do not prove original-database migration.

At intermediate `f55af294`, actual Provider preflight performed login/logout successfully, verified 2,770
Artifacts, current consistent backup, frozen Target and nine exact calendar
sessions. Capture proof remains false. Local profile content identity is
`9f62c632c05215f8d5704d0f79d8a68bdb3f3b440e2f703d987bed989e82dc2d`.
Budgets: 2 GiB disk reserve, 24-hour backup age, four pooled connections plus
one supervision connection, 10-second whole Provider call, 100,000 rows/32 MiB,
16 actual due claims and 120 seconds per tick, 120-second lease, 30-second wakeup.
All are explicit operation intent, not research thresholds.

That f55 actual-time isolated service exits 0 after owned-PID SIGTERM; a duplicate exits
2 with OPERATION_DUPLICATE_SUPERVISOR; bounded restart exits 0. Ticks take
2.85245/2.85882 seconds. Child peak RSS is 154,943,488 bytes. All 192 table hashes
and 2,770 Artifacts match before/after, with zero business writes. Health is
NOT_DUE; no Capture/Attempt was invented. Bounded lifecycle is not long-running
service proof. The supervisor template is uninstalled.

Health uses canonical complete window/generation/Runtime rosters and PostgreSQL
time. It separates expected/opened/future/due, capture, lateness, missed/gap/failure,
unknown effect, lease recovery and planning gaps. Capture success, on-time
capture and terminal coverage use distinct numerators; zero opened windows
produces typed NOT_ESTIMABLE rates. Market event freshness unavailable to this
projection is labelled separately from Capture known-time. Process-local alert
changes are logged internally; no external messages are sent.

### Completed research and read-only diagnosis

The completed drill at f55 revalidates the existing 44-day/32-instrument/four-arm
campaign, two FIT→VALIDATION dependencies, 936 complete actions and zero ready
actions. Generic inspect/report/self-compare/resume/replay/diagnose pass under
default read-only transactions. All 192 tables and 2,780 Artifacts
(130,289,170 referenced bytes) are identical before and after.
Report binding `66b20bc7-f8c9-51af-bb68-9cbea75d9322`, JSON SHA256
`c6ee9f51216693ece843a3e1578ac76e4a69e69ec6a19bf556e36c92eb406a88`
(517,803 bytes), Markdown SHA256
`6d2fcf61b5c999a5e4161d2a2e292e1ad1ec3ac1d0e5ff074cd2c30133a664f9`
(517,800 bytes) are unchanged. Self-comparison proves identity/comparability,
not independent replication. No training, new Run or report publication occurs.

[The research diagnosis](../operations/Research-Diagnostics.md) preserves all
9,472 declared member×arm×fold-session cells. There are 9,436 eligible Candidates
and 36 canonical eligibility exclusions, with no unexplained missing member.
97 NOT_ESTIMABLE metrics split into 88 frozen pre-eligibility denominator
mismatches with lawful exclusions, eight empty canonical partitions, and one
nonempty V1 economics slice with no estimable metric input. Eight Outcome
unavailable revisions remain negative evidence.

Four ModelVersions do not mean four independent samples: two have 640/640
estimable rows across 20 FIT days; two have 1,085 declared/1,084 estimable rows
across 34 days. Overlapping days and multiple arms cannot be summed as new
independent evidence. At the same Context setting, ridge and rule Forecast
RankIC are equal; ridge has lower descriptive error statistics. This does not
establish ranking increment, causal bottleneck, model selection qualification
or Alpha. Frozen V1 economics is neither corrected nor promoted by the prior V2
engineering gate. A future experiment needs an explicit denominator protocol;
daily Shadow also needs prospective Feature/Target/Model cutoff/Decision
bindings. Historical Validation is not untouched OOS.

### Performance, failures and evidence boundaries

Read-only original/copy diagnostics capture parameterized SQL and EXPLAIN
(ANALYZE, BUFFERS, FORMAT JSON), activity/locks/I/O, data statistics and repeated
timings. The recorded 22.660-second eight-Outcome batch was rechecked by exact
SQL hash and parameters; present repeats were much faster. The old failed resume
log did not retain its exact failing SQL/parameters or historical I/O/lock state.
Therefore ORIGINAL_DATABASE_ROOT_CAUSE remains UNPROVEN. No timeout increase,
cache reset, disabled integrity check, index change or original maintenance is
used to claim a fix. Counters shared with other connections cannot establish
historical causality.

The narrow real-data funnel projection used 13 SQL calls, 0.471 seconds and
101,416,960-byte peak RSS under its 5-second/48-call/512-MiB projection budget.
Those numbers exclude full upstream owner reconciliation. The complete
restore qualification at f55, including repeated owner reconciliation and two all-table/
physical scans, takes 254.2875 seconds and peaks at 405,684,224 bytes. A 100,000-row
SDK fixture returns 7,800,197 bytes in 0.370 seconds at 91,668,480-byte peak RSS;
this is explicitly fixture resource evidence, not real Provider capture capacity.

RED logs and all retry logs remain indexed. These include missing initial
implementations, the gap constraint, timer/byte bounds, snapshot-age and receipt
tampering, stale/lost supervision and public-entry bypass counterexamples.
Harness-only failures (wrong pytest fixture exception/import path, an initial
navigation test path, an `uv run export` command typo, and source fingerprint
changes while development tests overlapped editing) are preserved separately.
Successful reruns do not erase failures or change business assertions.


### Final revision, preflight refusals and compatibility reuse

The initial f55 full regression records **4,163 cases: 4,160 passes, three
failures, zero errors/skips**, exit 1. Two older schema-contract tests omitted
the new exact registered numbered migration; their exact roster was updated
without broadening Authority checks. The architecture guard caught SQL in the
interface module. All that SQL and session advisory-lock work now resides in
the existing PostgreSQL adapter layer. No test allowlist was weakened. The
original architecture counterexample is retained; architecture plus real-PG
operation guard pass 18 tests, and the migration-contract files pass 14 tests.

Final clean-worktree regression uses database
`mra_operations_final_repair_tests_20260907`, OID 153545579, on PostgreSQL 16.15
cluster `7682058034626392615`. It never points destructive fixtures at an
operational or restored evidence database. Final focused gate passes 152 cases,
zero failures/errors/skips. Final full gate passes 4,163 cases with zero failures/errors/skips (1,096
refoundation, 33 platform, 288 PostgreSQL-persistence), exit 0 in 2,061.25 seconds.
Architecture/docs 41 cases, Ruff, mypy, docs links, build and diff checks all exit 0.
The final recorder's nine command results bind the exact clean implementation.

Initial new-worktree dependency setup failed because PyPI TLS connection closed.
The preserved failed commands changed no dependency contract. Exact frozen sync
then succeeded using the already present cache with `UV_OFFLINE=true`.
Runtime requirements remain the same 47 locked versions. Python is 3.12.2.
The independent isolated build records setuptools 84.0.0; that build tool's
observed version is recorded separately from the runtime lock.

The final profile is content identity
`c2926cf07f362237ce1d41e197fe2d1f0163de52af074945786ab72c0b363243`,
file SHA256 `14ee2ffdb41bfe90b346f3e26fc0cb8574a81108b18bb9025d1533887d9e7625`.
It binds final source fingerprint, same isolated OID 142930962/root and verified
v6 backup. The first real startup and one explicit new request both return
`OPERATION_PROVIDER_ACCESS_UNAVAILABLE`, service exit 2 before an owner tick.
Each refusal preserves all 192 ordered table hashes and 2,770 Artifact
references/bytes, with no Attempt or business writes. No Provider effect was
faked and no third attempt was made. Positive final-source field lifecycle is
`BLOCKED_BY_PROVIDER_ACCESS`; positive f55 stop/restart is preserved only at its
own code identity. Final source PostgreSQL fixtures exercise the actual guard,
partial registration repair, lease/fence and stop/restart paths in disposable
scopes. These are engineering evidence, not sustained service or real capture.

Final installed-wheel smoke independently bootstraps only new database OID
146612586, verifies current v6 (192 tables, 3,929 objects), checks the ten retired
modules are absent and matches all 1,176 packaged Python/SQL files with frozen
source. On exact completed restore OID 144400596 with default read-only
transactions it verifies all 936 actions, matching replay and unchanged V1
report JSON/Markdown hashes. Pure V2 independent hand case remains: rejected
40% advice costs zero and leaves 1,000 cash; the next authorized episode buys
400, sells 440, pays 1.28 and finishes with 1,038.72. It is not a real Fill.

Independent installed wheel SHA256
`5f5cba8c23157e4393ac069e04857b87a9a67a8bd0a89610fc3c5c6726b0bd63`
(3,762,314 bytes); sdist
`4b69c75265ad43eb7a014131bc3533d05d1bb571b50f9fbcd1c2c1bbba0f3dbe`
(3,012,484 bytes). Installed qualification ledger SHA256
`c257dee78de410c65b242a8d98e1e52b192a1a7fc9e65da49fa872037b4141a2`.
No original evidence database is modified by installed smoke.

`final-schema-economic-dependency-compatibility.json` verifies that economics
algorithms, Evaluation writer/verifier, old migration/bundle bytes, seeds and
locked dependencies are unchanged from main. The f55→4c repair changes only the
SQL placement/guard seam, exact migration tests and a runbook command. Its
backup/restore/catalog and completed full-table proof remain reusable within
those exact unchanged owner/file scopes; the new final full suite, installed
real replay and real refused startup provide separate final-revision evidence.
No f55 failing full gate is reused as a PASS.

The original read-only v6 plan finishes with hash
`d3d5bbdd127f2825fb9c0a1deab02b0bbf94f2f9ee59c18eafe8868dc87d0e71`,
generated 2026-09-07 03:01:14.685669 UTC and expiring 03:11:14.685669 UTC.
It observes no active Attempts/conflicting connections, exact OID 287543 and
backup `013f366f…`; its apply status is NOT_AUTHORIZED/NOT_RUN. It must be
regenerated with current code/backup/preflight after approval. A successful
read-only plan is neither original upgrade nor adopted operational scope.
The latest controlled 256-row plans both use one PK Index Scan with Actual
Loops=1; no repeated/full scan or temporary spill was observed in this batch:
original planning 5,395.532ms/execution
1,858.359ms; restore planning 2.963ms/execution 31.390ms. Both estimate one and
return 256 rows. Original identity/catalog reads are slow too. These observed
scope differences, uncontrolled cache/load and disabled I/O timing do not
identify the historical QueryCanceled cause.

A complete-history Git bundle (10,574,274 bytes; SHA256
`8eb125b5988782e4302498fb50c731b7ada410cc9942986690fc57fde26ba3e7`)
verifies and independently restores the exact final implementation/source/tests
trees. It restores code; database and Artifact recovery remain separately
verified by their exact snapshot bundles. All 30,181 indexed originals (2,140,213,943 bytes) are now sealed in
`operations-activation-4c764b3d.tar.gz`, 1,570,966,599 bytes, SHA256
`f2a74158822e9400236e5e78824b026aae3f4b98988128b12c70dc7eb7870267`.
Per-file inventory SHA256
`1ec3061e527dea559df0bbb63d87c65348e8c25b097bfa56b5d59d7e249953ae`.
The archive is independently extracted and every original SHA/size matches,
with zero missing/extra members. Package/restore exits 0 in 75.59 seconds.
It includes exact code, retained failures, logs, snapshots, four database dumps
and referenced physical Artifact copies. Installed environment/cache and the
redundant bare Git extraction are excluded; their reproducible lock/build/code
inputs remain included. Storage is local SSD outside Git, not offsite or a
second physical-media failure domain. Later documentation-only delivery logs
and the final Git bundle are a separate receipt, not a changed implementation.

Old-writer admission is independently checked using unchanged qualified
`09561b25` against isolated v6 restore OID 146535672, with every session forced
read-only. Bootstrap rejects with CatalogDriftError before constructing the
writer or issuing any business command. No old worker is started, stopped or
replaced; the original database is untouched. This supports the proposed
upgrade boundary without claiming a performed operational cutover.

### Final completed-v6 backup and independent restore

At exact final `4c764b3d`, current completed-v6 source OID 144400596 is backed up
through the canonical exported-snapshot contract with every source connection
read-only. New bundle `completed-v6-final-backup` has dump SHA256
`72edc6c68dffde322887ee6e708ae05caefaada6ff20d142287aa7ce1f638d9c`
(310,004,476 bytes). Backup readability and complete pg_restore decode pass.
An independently created database `mra_operations_completed_v6_restore_20260907`,
OID 157024168 on cluster `7682058034626392615`, receives that exact dump and a
new Artifact root copied from its verified roster.

Schema verify, canonical restore-check/evidence verify, all five Archives,
WP17P replay and large completed Run replay pass. Source-after, snapshot and
restore-after hashes match across all 192 tables; source and restore physical
checks match 2,780 Artifacts/130,289,170 bytes, with zero missing/extra bytes.
Original JSON/Markdown report bytes and hashes are unchanged. No source business
writes or restored business writes after pg_restore occur. This is a completed
recovery scope; it does not change original OID 287543 or its FAILED Run.

The full driver exits 0 in 472.07 seconds, peak RSS 557,449,216 bytes. This is
whole backup/restore/reconciliation resource observation under shared I/O, not
the narrow diagnostic projection's 5-second/512-MiB budget or a controlled
cold/warm benchmark. Proof SHA256
`9d4d9308ea925406da911b66d08a3065a4cfe27c88f237211a30abaa316fe507`;
29-original manifest SHA256
`b97fe192aa245736d065215077f7df48b8740ee517115d6b633c93fcac6ce1b4`.

### Final original-clock and workspace recheck

Final fetched origin/main remains `85d0080ab3bf14fade5b91e8ef98aa9a16e0c2b2`,
with its initial tree unchanged. Original worktree HEAD/tree, unstaged-only
`.idea/modules.xml` bytes and index remain as recovered; the final qualification
worktree is clean. No local portfolio changes were mixed into this branch.
Repository Actions API still returns `enabled=false`:
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, never PASS.

Current final-source read-only status on original OID 287543 uses PostgreSQL
clock **2026-09-07 03:45:01.547047 UTC**. It reads all 288 expected slices,
288 future, zero due/overdue/planning gaps/captures and zero Attempts. The first
window is 2026-09-07 06:40–06:48 UTC. No wait, clock change or backdating occurs.
Registered parent Runs can say RUNNING while every capture Step is READY with
no Attempt; that does not prove a running worker or an actual capture.
The status explicitly says schema admission and physical/owner reconciliation
are not performed by this narrow read; separate restore/integrity proofs retain
their exact scope. Original writer activation still needs explicit v6 migration
authorization, current backup/preflight and accessible Provider. That operational
boundary is separate from the frozen WP-18Q real-due requirement.

### Requirement-to-evidence disposition

| Requested gate | Actual evidence | Remaining boundary |
|---|---|---|
| Exact revision / guarded runtime | Final 4c full 4,163 and focused 152 cases, static/type/architecture/docs/build/installed smoke; real-PG configuration, duplicate/signal/recovery/fence/unknown-effect tests | Positive 4c field lifecycle blocked by Provider access; earlier f55 bounded proof remains separately scoped |
| Original operations / due | Read-only exact OID/cluster, PostgreSQL time, full 288-slice roster and empty Attempts; expired read-only upgrade plan retained | Original v6 migration NOT_AUTHORIZED; actual due proof NOT_DUE; no successful capture or sustained service proven |
| Old slow read | Actual parameterized SQL, bounded plans, locks/I/O/counters and scope timings | Historical QueryCanceled root cause UNPROVEN; no speculative fix or timeout increase |
| Completed research | 936-action completed recovery, exact canonical report/replay/compare/resume, full-table zero-write proof; final installed and fresh-v6-restore replay | Original failed scope remains failed; V1 economics and retrospective evidence are not promoted |
| Read-only funnel | 9,472 declared cells, 36 legitimate exclusions, all 97 typed non-estimable results explained within recorded limits | No demonstrated ranking increment; new denominator protocol and prospective bindings needed before daily Shadow |
| Backup / recovery | Consistent v6 snapshots, fresh independent DB/Artifact restore, old-writer admission refusal and exact code-bundle restore | Local SSD evidence only; no operational adoption or offsite-redundancy claim |
| Remote Actions | Repository API enabled=false | BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN |

```text
WP18Q_EXIT_GATE = BLOCKED
OPERATIONAL_SCOPE_DECISION = ORIGINAL_RETAINED; V6_ACTIVATION_NOT_AUTHORIZED
ORIGINAL_DATABASE_ROOT_CAUSE = UNPROVEN
CONTINUITY_RUNTIME_IMPLEMENTATION = ENGINEERING_VERIFIED
REAL_DUE_ATTEMPT = NOT_DUE
SUCCESSFUL_REAL_CAPTURE = NOT_PROVEN
CONTINUOUS_SERVICE_PROOF = NOT_PROVEN
HEALTH_AND_RECOVERY = PASS_IN_ISOLATED_SCOPES
RESEARCH_FUNNEL_DIAGNOSTICS = PASS_READ_ONLY
BACKUP_AND_EVIDENCE_RECOVERABILITY = PASS_LOCAL_RESTORE
FINAL_REVISION_ENGINEERING_VERIFICATION = PASS_AT_4c764b3d
DAILY_MODEL_SELECTION_READINESS = NOT_READY
FULL_RUNTIME_CUTOVER = NOT_AUTHORIZED
ALPHA_PROVEN = NO
PRODUCTION_ADMISSION = NO
```

WP18Q's frozen real-due requirement is not relaxed. Provider startup failure is
not a Runtime-claimed Attempt, and a failed preflight is not successful capture.
No continuous service duration is claimed. Retrospective evidence stays
EXPLORATORY_RETROSPECTIVE; FORMAL_PROVIDER/PIT stay BLOCKED, FORMAL_OOS NOT_RUN,
PROSPECTIVE_PROVEN NO, MODEL_QUALIFIED NO. The minimum operating step is a new
explicit authorization for the original v6 upgrade, a refreshed exact backup/
plan/preflight, accessible Provider and canonical execution at an actually due
window. A restored copy is not selected as an Authority fallback.

The documentation containing this addendum is a subsequent documentation-only
commit. Its source/tests/dependency objects are identical to the tested 4c
implementation; no claim relies on the Verification's own commit identity.
Final document navigation/command/ceiling checks are repeated for that delta.
The original index's 367 entries and all preceding Verification bytes remain
preserved at baseline `85d0080a`; the index adds this activation as one named
continuation. The before/after scope of reused evidence is explicit above.
