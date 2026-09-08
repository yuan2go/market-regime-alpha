# Research Economics Correctness 01 Verification

> **Status:** CURRENT_STATUS
> **Verification State:** IMMUTABLE_EXACT_REVISION_PASS_WITH_EXPLICIT_SCOPE
> **Authority:** Local engineering evidence for the bounded economic model; no Alpha or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-06 (UTC; local timezone Asia/Shanghai)
> **Original baseline SHA / tree:** `32bcb2922e6ced805c51f320e5f5657521f8cf14` / `dddfe02092562989037140f8aff88250117be627`
> **Resumed main SHA / tree:** `58640732b1c51ccec004dc574d3df790ccc4994d` / `a15ab010cc0df4e12ce2b808c2d0a5c8a028431e`
> **Verified implementation SHA / tree:** `a107d98ee1f4e47db1dca5512211a02ad23029c9` / `fe5c2d80fcdfc2364df45cd822cc8a8e9cebbc60`
> **Source / tests tree:** `afcd0c8e3aebe83ab01f68637c586038f758d410` / `a38f5334f8dd4fa76ba233c9281967b571276c61`
> **Code Evidence:** `src/market_regime_alpha/infrastructure/postgres/evaluation_metric_record.py`, `src/market_regime_alpha/infrastructure/postgres/queries/research_verification.py`, `src/market_regime_alpha/infrastructure/postgres/queries/evaluation_episode_parent.py`, `tests/refoundation/research_qualification/test_episode_economics_postgres.py`, `tests/refoundation/research_qualification/test_episode_longitudinal_postgres.py`
> **Containing evidence commit:** Reported in delivery. It changes documentation/evidence only and does not purport to contain its own SHA.

## Decision and supported scope

```text
WP_EXIT_GATE = PASS
CORE_RISK_POSITION_TURNOVER_DEFECT = FIXED_FOR_V2_SUPPORTED_SCOPE
SUPPORTED_ECONOMIC_SCOPE = INDEPENDENT_FUNDED_CLOSED_ASSUMED_CHECKPOINT_EPISODES_V2
CANONICAL_INTEGRATION = PASS
EXACT_SHA_ENGINEERING_VERIFICATION = PASS_LOCAL
RESULT_ROOT_AND_CHILD_INTEGRITY = PASS
MULTI_EPISODE_CANONICAL_PROOF = PASS
HISTORICAL_REPLAY_COMPATIBILITY = PASS_EXACT_SCOPE
EXACT_REVISION_ENGINEERING_VERIFICATION = PASS_LOCAL
REAL_DATA_VALIDATION = PASS_LIMITED_RESTORED_EXPLORATORY
WP18Q_OVERALL_STATUS = BLOCKED
RESEARCH_ALPHA_PROVEN = NO
PRODUCTION_ADMISSION = NO
```

This closes the existing package under its [frozen design](WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Design.md),
including the result-integrity continuation. V2 remains independent funded,
fully liquidated hypothetical checkpoint-mark episodes. This continuation
introduces no new financial model, formula version, schema or qualification
framework. The [evidence index](WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Evidence.json)
binds commands, exit codes, logs, distributions, database identities, source/test
trees and exact financial/report records. Raw files remain in the local external
evidence bundle; shared configuration contains no personal paths or credentials.

Continuous accounts, opening inventory, carry, partial rebalancing, sell-only
opening positions, overlapping capital occupation, cross-session/corporate-action
prices, nonzero minimum fees/slippage, and continuous NAV/annualized/drawdown
statistics remain explicitly unsupported. Fractional same-session mark transactions
do not prove A-share executability, intraday resale legality or actual fills.
WP-18Q's large campaign, future prospective window and hard-cut remain separate
and unqualified. `BACKTEST_PLATFORM=NOT_ENGINEERING_QUALIFIED` remains unchanged.
No required local gate of this bounded package remains blocked. Remote Actions
is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`: the read-only API returns
`enabled=false`; local execution, not remote CI, supports this decision.

## Recovery and exact revision chain

Before Git mutation, local refs, worktrees, diffs, history and evidence were
inspected. The original workspace remains on `agent/wp-portfolio-execution-authority-01`,
SHA `10689a4db772be5a546a64448fcc6f39f6988412`, tree
`6d9c8ae5a977a0ab54c2a73c3ca9ec528415c39f`. Its unrelated `.idea/modules.xml`
modification was never modified, staged or committed. The initial fetched main
was verified as `32bcb292`; the original branch was zero ahead / 462 behind.

Earlier local economics work was recovered and retained through `6e9a0e16`,
whose complete tree is identical to the later fetched main `58640732` (PR #109).
The prior clean 4,043-case run is evidence for that prior tree only. The agent
did not push, open the PR or merge it. The continuation branch
`agent/wp-research-economics-correctness-01-integrity` starts at `58640732` and
contains `7012657e` (complete typed result/root and child bindings) followed by
`a107d98e` (actual Decision root check and longitudinal canonical acceptance).
Both original economics worktrees remain intact. No reset, clean, stash,
history rewrite, operational evidence mutation, frozen R2 process/source change,
broker operation, push, PR creation or merge was performed.

AGENTS, CLAUDE, Design, Canonical/Authority/Data architecture, Current State,
Capability Matrix, Roadmap and affected code/schema/test/evidence were read.
Existing V2 core and Runtime/composition were reused. Historical Verification and
failed results remain immutable. Independent spec and standards reviewers found
no remaining P0/P1 at `a107d98e`; read-only review is additional evidence, not a
substitute for execution. Current status/navigation updates accompany this record.

## Proven defects and changes

The original proposal-state defect remains recorded in `baseline-counterexample.log`:
an initially rejected 40% suggestion was charged turnover `0.40` and net return
`-0.00064`; the next authorized identical suggestion had turnover `0.00` and net
`0.0400`. V2's independent hand case starts with 1,000 cash. REJECTED/UNKNOWN
leaves 1,000 cash with no trade/fee. The subsequent authorized episode buys 400
at explicit entry mark 10, sells 440 at explicit exit mark 11, pays buy/sell
10/20 bps = 1.28 and ends with 1,038.72. This is an explicit round-trip model,
not a retrospective reinterpretation of V1's horizon.

On resumed main, changing only `estimable_count` from 1 to 2 while retaining the
old content hash still produced `matched=true`. The retained RED assertion in
`result-root-red.log` proves the root integrity gap independently of audit prose.
The writer and verifier now share `EvaluationMetricRecord` for all eleven
explicitly persisted business fields: result/run/protocol-metric/protocol IDs,
`metric_state`, `decimal_value`, `boolean_value`, `estimable_count`,
`acceptance_state`, `reason_code`, and `content_sha256`.

Reconciliation derives expected V2 results from the EvaluationRun's frozen
Protocol, not actual result rows joined through potentially damaged formula IDs.
It compares actual persisted fields against the recomputed typed record, exact
roster and parent bindings. Economic children bind the verified expected result
ID, not their own unverified claimed parent. This changes integrity verification,
not financial semantics or historical serialization. Database-default `created_at`
remains lifecycle metadata outside the historical financial content hash.

Eleven legal-domain corruption variants cover sample count, boolean, acceptance,
state/nullability, decimal, reason, hash, protocol, a V1 metric/protocol reassignment,
result identity and run identity while retaining prior hashes where applicable.
Every case causes Evaluation mismatch, Backtest replay mismatch, inspect
`INTEGRITY_ERROR`, and Report **publish refusal**. The observed result/source/input,
Receipt/Audit and Runtime run/step/attempt tables are unchanged by verification.
Corruption bypass is confined to a disposable qualification database; exact
restoration is verified after each case. Existing child/source/cost/classification
and read-after-acquisition input-change tests remain and pass.

Longitudinal negative tests exposed two further local defects: a missing Portfolio
parent raised a known input exception instead of returning an integrity mismatch;
and deleting actual `decision_run` while leaving its Backtest binding could pass.
The verifier now reports known canonical input errors as explicit mismatches.
The parent query reloads actual DecisionRun identity, Dataset binding and `OPENED`
status. It never treats the binding row as a substitute for Decision Authority.
RED logs `multi-episode-parent-second-red.log` and
`multi-episode-negative-matrix-second.log` remain indexed.

## Multi-episode canonical vertical proof

The new PostgreSQL test uses existing Generic Application/composition and canonical
capture/normalize/seal fixtures. One FIT episode precedes four Validation episodes,
two per explicitly dependent fold. All parameters are frozen before Outcome access.
Capital is 1,000 **per complete episode**, shared by its securities; buy/sell costs
are explicit 3/8 bps, with zero minimum fees/slippage. A fixed Risk line cap rejects
two positive-weight suggestions; two other episodes trade. There is no tuning or
removal of a negative member.

| Decision session | Fold | Canonical members | Behavior | Buy / sale | Fees | Final cash |
|---|---|---:|---|---|---|---|
| 2026-01-28 | A | 2 | REJECTED; cash | 0 / 0 | 0 | 1,000 |
| 2026-01-29 | A | 32 | Five allocations; +10% marks | 800 / 880 | 0.95 | 1,079.05 |
| 2026-01-30 | B | 32 | Five allocations; -10% marks | 800 / 720 | 0.85 | 919.15 |
| 2026-02-03 | B | 2 | REJECTED; cash | 0 / 0 | 0 | 1,000 |

| Metric selection | Independent expected net return | Episode count |
|---|---|---:|
| Entire parent | -0.00045 | 4 |
| Fold A | 0.039525 | 2 |
| Fold B | -0.040425 | 2 |
| January | -0.0006 | 3 |
| February | 0 | 1 |

Overall two-sided turnover is `0.8`. February zero is a computed funded cash
episode, not missing-value imputation. Six persisted metrics all retain the same
68-member parent source path; slicing selects completed episodes and never
reinitializes a subset of positions/capital. Exact JSON values, counts, formula V2,
result/evaluation IDs, and ALL/FOLD/TIME_MONTH selectors are checked independently.
JSON/Markdown bytes and report binding stay stable through repeat publish,
resume/replay. Before/after snapshots of **all 192 schema tables** prove
completed operations do not add or alter facts in this portable test.

An independent negative fixture contains only a February selector. Corrupting an
unselected January episode must still fail. Missing actual Decision, commitment,
Portfolio line or acquired observation, changed canonical Outcome price and
duplicate capital roster are exercised. Partial rosters cannot disappear; duplicate
lines are rejected by the canonical uniqueness constraint. Each case restores raw
PostgreSQL JSON text to preserve numeric representation and all-table hashes.
Full-path selectors and the supported-model refusal contracts remain enforced.
The same multi-episode protocol exercises concurrent/idempotent completion,
stale fence zero writes, partial child rollback and unknown commit recovery.

## Computation, persistence and historical boundaries

Input preparation closes its UoW before Outcome owner I/O and pure financial
calculation. The final write UoW rechecks full parent, identities, complete roster,
exact price guard and live fence; metric/source/cost facts, Receipt/Audit and
Runtime completion are atomic. The pure deterministic core is the sole current
financial transition algorithm. Explicit Decimal precision, cent rounding, units,
fees and entry/exit funding remain caller-context independent. Report only
projects reconciled Evaluation. No actual Account, Position, Fill or TradeOutcome
is created. No additional EpisodePolicy, UoW or infrastructure was introduced.

V1, formula-less and V2 remain exact-identity routed. Old formula/result bytes and
hashes are preserved; old proposal-based economics is excluded from V2 correctness
evidence and is not mixed into its capital/return model. The finite new control's
FIT/Validation prerequisite protocols consume non-economic canonical market labels;
its aggregate V2 protocol owns the three explicit episode metrics.

## Exact implementation execution

The detached worktree `economics-integrity-qualification-a107d98e` was clean and
bound to the SHA/tree above before and after all gates. Environment: Python
3.12.2, uv 0.11.7, PostgreSQL 16.15, macOS arm64; all Python commands use `uv run`.
`uv.lock` SHA256 is `5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d`; `pyproject.toml` SHA256 is `41f84a204da321edfa748aac95b428de3f50d6d06e48ef061d469d9c2424fdfb`.
Neither dependency file, any migration, schema package nor registered upgrade
bundle differs from resumed main. No DDL was invented for this correction.

`$EVIDENCE`, `$SMOKE_ENV` and database variables below identify external local
roles; they are not shared machine configuration. Every listed command was
executed. Full-run categories are subsets, not additional test totals.

| Command | Exit / result | Seconds |
|---|---|---:|
| `uv sync --frozen --extra dev --extra postgres` | 0 / PASS | 2.75 |
| `uv run python -m pytest -q tests/refoundation/research_qualification/test_episode_economics.py tests/refoundation/research_qualification/test_episode_formula.py tests/refoundation/research_qualification/test_episode_economics_postgres.py tests/refoundation/research_qualification/test_episode_longitudinal_postgres.py tests/refoundation/research_qualification/test_evaluation_closure_postgres.py tests/refoundation/research_qualification/test_evaluation_formula_schema.py tests/refoundation/research_qualification/test_backtest_query_plans_postgres.py tests/refoundation/research_qualification/test_backtest_reports.py '--junitxml=$EVIDENCE/qualified-a107d98e/focused.xml'` | 0 / PASS | 107.14 |
| `uv run python -m pytest -q '--junitxml=$EVIDENCE/qualified-a107d98e/full-repository.xml'` | 0 / PASS | 1954.97 |
| `uv run python -m ruff check .` | 0 / PASS | 0.99 |
| `uv run python -m mypy` | 0 / PASS | 11.65 |
| `uv run python -m mypy src/market_regime_alpha/research_qualification/domain/episode_economics.py src/market_regime_alpha/research_qualification/domain/episode_formula.py src/market_regime_alpha/research_qualification/domain/evaluation_computation.py src/market_regime_alpha/research_qualification/domain/evaluation_sources.py src/market_regime_alpha/research_qualification/application/evaluation_economics.py src/market_regime_alpha/outcome/domain/economic_prices.py src/market_regime_alpha/infrastructure/postgres/evaluation_metric_record.py` | 0 / PASS | 0.25 |
| `uv run python scripts/check_docs_links.py` | 0 / PASS | 0.11 |
| `uv run python -m pytest -q tests/architecture tests/scripts/test_check_docs_links.py` | 0 / PASS | 13.19 |
| `uv run python -m build --outdir '$EVIDENCE/qualified-a107d98e/dist'` | 0 / PASS | 11.14 |
| `git diff --check` | 0 / PASS | 0.01 |

Focused: **78 cases, zero failures/errors/skips**.
Full repository: **4045 JUnit cases, zero failures/errors/skips**.
No assertion weakening, deleted failure, skip/xfail or strategy threshold change
was used. The full run includes shared Evaluation/Outcome/FIT Model/Backtest,
PostgreSQL persistence/migrations/fresh schema/registered historical upgrades,
concurrency/replay, architecture and platform tests.

| Full-run category | Cases |
|---|---:|
| `tests.application` | 975 |
| `tests.architecture` | 21 |
| `tests.candidates` | 47 |
| `tests.cli` | 62 |
| `tests.core` | 10 |
| `tests.daily_decision` | 13 |
| `tests.daily_research` | 47 |
| `tests.data` | 111 |
| `tests.decision` | 10 |
| `tests.evaluation` | 5 |
| `tests.evidence` | 3 |
| `tests.execution` | 103 |
| `tests.features` | 94 |
| `tests.forecasting` | 14 |
| `tests.legacy` | 24 |
| `tests.market_data` | 56 |
| `tests.migration` | 29 |
| `tests.persistence.postgres` | 288 |
| `tests.persistence.test_cli_backend_selection` | 2 |
| `tests.persistence.test_postgres_bootstrap` | 6 |
| `tests.persistence.test_repository_factory` | 4 |
| `tests.persistence.test_settings` | 9 |
| `tests.platform` | 33 |
| `tests.portfolio` | 51 |
| `tests.position` | 88 |
| `tests.refoundation` | 993 |
| `tests.research` | 468 |
| `tests.scripts` | 38 |
| `tests.signals` | 22 |
| `tests.strategies` | 96 |
| `tests.test_a_share_bars` | 16 |
| `tests.test_buy_point_quality` | 5 |
| `tests.test_cosco_timing` | 16 |
| `tests.test_dividend_t_chan` | 2 |
| `tests.test_dividend_t_fundamentals` | 2 |
| `tests.test_dividend_t_model` | 20 |
| `tests.test_dividend_trend_snapshot` | 5 |
| `tests.test_fetch_baostock_5min_batch` | 4 |
| `tests.test_formal_dataset_builder` | 2 |
| `tests.test_macd` | 45 |
| `tests.test_macd_bars` | 18 |
| `tests.test_macd_experiments` | 39 |
| `tests.test_macd_oos` | 10 |
| `tests.test_market_environment` | 7 |
| `tests.test_notifications` | 4 |
| `tests.test_reproducible_environment` | 3 |
| `tests.test_signal_intent` | 31 |
| `tests.test_tencent_minute_cache` | 4 |
| `tests.test_tushare_client` | 5 |
| `tests.universe` | 81 |

| Supplemental command | Exit / result | Evidence |
|---|---|---|
| `uv run python $EVIDENCE/qualify_integrity_generic.py` | 0 / PASS | `integrity-generic-execution.log` |
| `uv run python $EVIDENCE/verify_integrity_oracle.py` | 0 / PASS | `integrity-independent-oracle.log` |
| `uv run python $EVIDENCE/measure_integrity_evaluation.py` | 0 / PASS | `integrity-performance.log` |
| `uv run python $EVIDENCE/verify_integrity_reproducibility.py` | 0 / PASS | `integrity-reproducibility.log` |
| `uv run python $EVIDENCE/verify_integrity_history.py` | 0 / PASS | `integrity-history-and-bytes.log` |
| `uv run python $EVIDENCE/verify_integrity_historical_reports.py` | 0 / PASS | `integrity-historical-reports.log` |
| `uv run python $EVIDENCE/verify_integrity_archive.py` | 0 / PASS | `integrity-archive-verification-script.log` |
| `uv run python $EVIDENCE/verify_integrity_environment.py` | 0 / PASS | `integrity-environment-script.log` |
| `uv run python -m build --outdir $EVIDENCE/integrity-build-smoke-dist` | 0 / PASS | `integrity-build-smoke-build.log` |
| `uv export --frozen --extra dev --extra postgres --no-emit-project --format requirements-txt --output-file $EVIDENCE/integrity-wheel-locked-requirements.txt` | 0 / PASS | `integrity-lock-export.log` |
| `uv pip install --python $SMOKE_ENV/bin/python -r $EVIDENCE/wheel-locked-requirements.txt; uv pip install --python $SMOKE_ENV/bin/python --no-deps $EVIDENCE/integrity-build-smoke-dist/market_regime_alpha-0.1.0-py3-none-any.whl` | 0 / PASS | `integrity-wheel-smoke-install.log` |
| `env -u PYTHONPATH -u VIRTUAL_ENV uv run --no-project --python $SMOKE_ENV/bin/python python $EVIDENCE/integrity_wheel_smoke.py` | 0 / PASS | `integrity-wheel-smoke.log` |
| `env -u PYTHONPATH -u VIRTUAL_ENV uv run --no-project --python $SMOKE_ENV/bin/python mra --help` | 0 / PASS | `integrity-wheel-cli-smoke.log` |
| `pg_restore --no-owner --no-privileges --dbname $ISOLATED_CONTROL_DATABASE $EVIDENCE/v5-reference-copy.dump` | 0 / PASS | `integrity-control-restore.log` |
| `uv pip install --python $SMOKE_ENV/bin/python --reinstall --no-deps $EVIDENCE/qualified-a107d98e/dist/market_regime_alpha-0.1.0-py3-none-any.whl` | 0 / PASS | `integrity-final-wheel-install.log` |
| `env -u PYTHONPATH -u VIRTUAL_ENV uv run --no-project --python $SMOKE_ENV/bin/python python $EVIDENCE/integrity_final_wheel_smoke.py` | 0 / PASS | `integrity-final-wheel-smoke.log` |
| `env -u PYTHONPATH -u VIRTUAL_ENV uv run --no-project --python $SMOKE_ENV/bin/python mra --help` | 0 / PASS | `integrity-final-wheel-cli-smoke.log` |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | 0 / PASS | `integrity-actions-permissions.json` |

The built wheel was installed into a separate locked environment and imported
from `site-packages` outside the repository. Its financial hand example, CLI,
packaged SQL/seed empty-database bootstrap and schema verification pass. Frozen
exported requirements match the installed requirement roster (generated header
excluded). Smoke wheel SHA256 is
`2184bc5829874a8f7b4cb6fbea409bb3bd6ce37f72b3750222e94f0b4b44a05e`,
size 3,759,225; sdist SHA256
`a45287ca6c1026c4c7a3b19d86d778bfecba325eff0ed397d9dd4b1480d4d5e7`,
size 3,007,488. Both final full-gate and installed-smoke distribution hashes
are in the index; the finite control binds this exact installed-smoke code wheel.
The final gate's wheel SHA256 is
`5484ee344f550118ea1c4783f101d96d77a5bc3e574442d55836657cb77200da`;
sdist SHA256 is
`59e289d2f836d75bb58f9ef7c4e0fe218854d630dba9f62e4ff1b0f2e2568228`.
Their 1,180 wheel / 1,204 sdist member contents exactly match the earlier build;
five wheel member timestamps differ. The exact final wheel was separately
reinstalled and passed the financial/CLI smoke and existing fresh-schema
verification. Fresh bootstrap was already proven with identical packaged SQL
member bytes. Neither differing archive hash is silently substituted for the other.

## Isolated databases, restore and immutable history

All mutations were on disposable test/restore databases in the qualification
PostgreSQL cluster, system identifier `7682058034626392615`, owner `yuan`,
with `fsync`, `synchronous_commit` and `full_page_writes` enabled. The original
operational database and frozen R2 campaign were not modified.

| Logical role | Database | OID |
|---|---|---:|
| Final exact regression | mra_economics_correctness_integrity_qualification | 108849871 |
| Finite control fresh restore | mra_economics_correctness_integrity_control | 108849872 |
| Installed-wheel empty bootstrap | mra_economics_correctness_integrity_wheel | 108849873 |
| Historical read-only replay copy | mra_economics_correctness_v5copy | 98520357 |
| Previously restored immutable backup source, read only | mra_wp18q_r2_receipt_index_fresh_upgrade_drill | 98243926 |

The retained dump `v5-reference-copy.dump` is 115806747 bytes with SHA256
`23684db1139b5df88ff26609a4cb75ca4defebdb64c68a34c5f23fe6ea48d7a0`; `pg_restore --list` verifies readability. This iteration restores
it into a fresh isolated control DB and clones the corresponding Artifact root.
The control's separate root has 2,470 physically verified Artifact references
after execution; identity/hash/size match. Archive
`fc699eea-1283-5192-b3ac-c9cbddc0da5e` reconciles with zero mismatches.
Neither a raw file nor a directory name substitutes for canonical Authority.

Restored/current fresh schema agrees: 192 tables, 4 views, 1,365 indexes,
1,834 constraints, 147 functions and 386 non-internal triggers; 3,929 objects.
Baseline `f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27`,
catalog `d14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1`,
seed `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11`,
vocabulary `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b`.

Historical comparison covers **45 explicitly selected tables / 656,361 prior
rows**, whose ordered hashes and identities are unchanged, plus 2,463 historical
Artifacts whose physical SHA/size match. `artifact.last_verified_at` is excluded
as mutable verification metadata; no unmeasured difference count is claimed.
Historical zero-write reader checks also cover Receipt/Audit/Attempt/result/report
counts. This is an exact observed scope, not a claim that every DB table was compared.

Exact replays all match with no mismatch codes:
`8f7b6def-9c63-533e-9777-a5a6c57866e0` (private WP17P historical),
`99227101-fabe-5244-a9ab-e2ebe492b22d` (old Generic), and
`62cdfc68-b80a-5f33-91ef-52c60542342e` (earlier V2 control).
Old Generic and prior V2 JSON/Markdown re-render byte-for-byte equal their already
published Artifact bodies; exact binding IDs, hashes and sizes are indexed.
Matching historical replay preserves old meaning; it does not qualify old economics.

## Limited real restored control and replay

The immutable input archive supplies 32 deterministic instruments, FIT sessions
January 5/6 and one January 9 Validation session, with explicit purge January 7
and embargo January 8. One rule arm and frozen costs/capital are reused without
parameter search or validation tuning. No ModelTraining is claimed for this control.
It is not a 40-session campaign or formal PIT/OOS result.

| Fact | Exact identity/value |
|---|---|
| BacktestRun | `1e80a091-4311-5f16-b3b1-f723435cfd10` |
| Aggregate V2 Evaluation | `eb92c2cf-0d97-5e3b-82ef-3b33a1591edb` |
| Performance Evaluation, same frozen inputs | `fd96de64-63e0-5857-9c16-0c935f8f195c` |
| Report binding | `dd8d1ca1-02e0-53dd-899b-b4a3669f6df8` |
| JSON Artifact | `50e54d1f-29c7-4ff8-903a-1e84b556dcdb`; 10,024 bytes |
| JSON SHA256 | `4a96b03902f540e7ee8fb6a69b540982271f13ad3c5b1a0ce37f4e7c4f40e433` |
| Markdown Artifact | `06c4ef3a-f928-4851-9768-071b4cb70091`; 10,010 bytes |
| Markdown SHA256 | `16dd288cdecdca67af592d1291a3127e236996545f297354cdc888ee51fa61c1` |

The independent reference consumes canonical Portfolio/Risk and exact Outcome
checkpoint prices, never production economic functions or raw bars. Capital
100,000; buy 80,000; sale 80,915.55; fees 88.74; final cash 100,826.81.
Gross return `0.0091555`, net `0.0082681`, turnover `1.6091555`; all three stored
metrics, identity bindings and source ledger match. Generic execution completes;
inspect/resume stay COMPLETED and replay matches with no mismatches. Snapshot
hashes for **48 explicitly selected tables** plus the physical Artifact roster
are unchanged; both report formats are byte-stable. The separate portable
multi-episode test provides the all-192-table repeat-operation proof.

## Measured resource and query evidence

For the predeclared 32-revision, three-metric workload, 559 SQL calls remain below
600; input preparation 0.142669s and final write UoW 0.208457s remain below one
second each. Total completion 0.581473s is below three seconds; peak RSS
86,589,440 bytes is below 200 MiB. Exact Outcome owner reload occurs once per
distinct revision (32), outside the final write transaction. Query row-count sum
is 6,182 **returned or affected** rows, including writes; it is not claimed as
6,182 returned data rows. No measured budget exceeded, so no optimization was added.

| EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) query | Output rows | Execution ms | Max node rows × loops |
|---|---:|---:|---:|
| `FROM mra.evaluation_observation AS observation` | 32 | 1.721 | 1024 |
| `FROM mra.market_target_outcome_revision AS revision` | 1 | 0.029 | 1 |
| `to_jsonb(fact)` | 32 | 1.458 | 32 |
| `FROM mra.backtest_arm_fold binding` | 1 | 0.061 | 3 |

Growing Outcome/input/parent paths use bounded indexed lookups. Tiny cost and
fold tables legitimately use sequential scans. The source's bounded 32×32 join
and existing per-revision owner verification are explicitly measured, not hidden
or generalized as unbounded scaling proof. SQL, parameters and full JSON plans
remain in the external indexed files. No Authority validation was bypassed.

## Failure retention and remaining boundary

RED logs retain the original risk defect, unchanged-hash root defect, missing
actual Decision and parent-error mismatch defects. Test-construction failures
(initial missing fixture option, ambiguous fixture join, and lossy JSON numeric
restoration) also remain with their corrections; the final tests restore raw
records and use independent literal financial expectations. Earlier interrupted
or incomplete qualification attempts are retained as prior/nonqualifying evidence.
Final PASS is derived only from the exact implementation run listed here.

No required implementation or local verification item of this package is pending.
Remote Actions was not run because repository configuration disables it. Future
windows, the frozen 44-session R2 campaign, broad real-market model validation,
continuous account economics, WP-specific hard-cut, Model qualification and
formal Provider/PIT/OOS remain outside this acceptance and unproven.
`RETROSPECTIVE=EXPLORATORY_RETROSPECTIVE`, `FORMAL_PROVIDER=BLOCKED`,
`FORMAL_PIT=BLOCKED`, `FORMAL_OOS=NOT_RUN`, `PROSPECTIVE_PROVEN=NO`,
`MODEL_QUALIFIED=NO`, Runtime/CLI cutover and Production remain `NO-GO`.
