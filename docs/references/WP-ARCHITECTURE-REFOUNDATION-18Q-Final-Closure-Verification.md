# WP-18Q Final Qualification Closure Verification

> **Status:** CURRENT_STATUS
> **Verification State:** IMMUTABLE_EXACT_SHA_BLOCKED
> **Authority:** Exact-SHA engineering ledger; no research, Provider, trading or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-05 (Asia/Shanghai)
> **Baseline:** `66c30e0159b8ce4bb3e17a7fdf1c3cc48dae6167`
> **Implementation Checkpoint:** `7818253cda85755175d87ff3acec1b1d8d7af762`
> **Implementation Tree:** `87e2d8f137eb5732960ef371ad64f25505076ccd`
> **Source / Tests Trees:** `a411f63a5534dd91ed4562c9fe87133490d4db51` / `8b0c63e5349651f14e583d96a936725498b3d886`
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha`, `tests/refoundation`, `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
> **Review / Merge Candidate:** Implementation SHA/tree above; final containing documentation commit is reported in the handoff, avoiding a self-referential SHA. No merge, push or PR was requested or performed.

```text
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = NOT_ENGINEERING_QUALIFIED
PROSPECTIVE_REQUIRED_ATTEMPT = BLOCKED_BY_TEMPORAL_WINDOW_AND_OPERATIONAL_ACCESS
PROSPECTIVE_RUNTIME_CONTINUITY = NOT_FULLY_WIRED
HARD_CUT = BLOCKED
```

## 1. Baseline and scope freeze

Fetched execution-time latest origin/main and created
`agent/wp18q-final-closure-20260905` with its own worktree from the exact
baseline above. Final engineering validation uses the separate clean worktree
`wp18q-final-exact-7818253c`. The original checkout's unrelated
`.idea/modules.xml` change is preserved and excluded.

Reviewed AGENTS, CLAUDE, canonical/supporting architecture, Authority Map,
current status/roadmap/capabilities, immutable WP-17P Verification, WP-18 and
WP-18Q designs/plan, actual source, migrations and tests. Current docs had
WP-17P-only status and stale target catalog counts. Their assertions were not
used as current implementation evidence.

The correction boundary is historical identity correctness, one measured
Evaluation-query join amplification, exact catalog/composition test contracts,
and PostgreSQL-clock prospective fixtures. No migration bytes, Constitution,
risk parameters, model hyperparameters, new root/runtime/registry, business
Authority or empirical evidence ceiling changed. Market export formatting
preserves an identical AST and the existing public names.

## 2. Exact engineering commands

Every Python command uses the locked environment. Test processes use separate
new databases; historical compatibility connects read-only to the historical
copy and exact Artifact root. `-o addopts=` makes the explicit pytest command
verbosity effective; it does not deselect, skip or relax assertions.

| Command | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| `uv run python -m pytest -o addopts= -q tests/refoundation -k 'backtest or prospective or model or operational_schema or formula' -ra --tb=short` | PASS: 148 |
| `uv run python -m pytest -o addopts= -q tests/refoundation -ra --tb=short` | PASS: 868 |
| `uv run python -m pytest -o addopts= -q tests/platform -ra --tb=short` | PASS: 33 |
| `uv run python -m pytest -o addopts= -q tests/persistence/postgres -ra --tb=short` | PASS: 288 |
| `uv run python -m pytest -o addopts= -q -ra --tb=short` | PASS: 3,910 tests + 4 subtests in 1,878.82 seconds |
| `uv run python -m pytest -o addopts= -q tests/architecture tests/refoundation/test_target_architecture.py tests/scripts/test_check_docs_links.py -ra --tb=short` | PASS: 38 |
| `uv run python -m ruff check .` | PASS |
| `uv run python -m mypy` | PASS: 621 source files |
| `uv run python -m build --outdir $EVIDENCE_ROOT/dist` | PASS: wheel and sdist |
| `uv run python scripts/check_docs_links.py` at implementation SHA | PASS |
| `git diff --check` at implementation SHA / clean worktree inspection | PASS |
| Current documentation links/navigation after reconciliation | PASS: link inventory plus 7 script tests |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | PASS: read returned `enabled=false` |
| Remote GitHub Actions | BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN |

JUnit paths and complete command arrays are recorded in the external evidence
bundle. All final suites have zero failures, errors, skips or xfails.
Separate explicit WP-18 definition/report/executor/Model contract inspection
passed 13 tests. It is fixture/contract evidence, not a real current campaign.

## 3. PostgreSQL qualification

PostgreSQL **16.15** on a dedicated disposable instance. Durability settings:
`fsync=on`, `synchronous_commit=on`, `full_page_writes=on`;
`max_locks_per_transaction=1024`. No operational server configuration changed.

| Purpose | Exact DB name | OID |
|---|---|---:|
| Full final repository gate | `mra_wp18q_final_exact_full` | 912918 |
| Named focused/refoundation/platform/persistence gates | `mra_wp18q_final_exact_named` | 912919 |
| Clean bootstrap / verify / guarded recreate / verify | `mra_wp18q_final_exact_qual` | 912920 |
| Existing restored historical evidence copy | `mra_wp18q_closure_history_20260905` | 31313 |
| New restored additive-upgrade rehearsal copy | `mra_wp18q_final_upgrade_copy` | 1366598 |

Connected/owning maintenance role for qualification is `yuan`. The exact
recreate plan was bound to name/OID, current epoch/catalog, operator, nonce and
challenge; no other client was present. Bootstrap, verify, exact guarded
recreate and second verify agree on all checksums and table identities.

```text
tables                           192
views                            4
indexes                          1364
constraints                      1834
non-internal triggers            386
baseline SHA256                  aae59a527154fd19da4bf07a0402d353d2b02a8da56cef6c4a505509683c412b
catalog SHA256                   a61a4ed2a4ae93521942053c37ab6560386bc49c43e64ef3a03f21ab4ab14a71
reference seed SHA256            9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
reference vocabulary SHA256      d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b
```

The executed refoundation suite includes exact retry/idempotency, concurrent
claims/predeclaration, stale-fence zero writes, expired-lease recovery,
transaction failure injection, unknown-commit exact probes, resume, replay and
reconciliation. Runtime's unknown remote outcome waits for explicit resume
instead of blindly repeating an external effect. Schema tests exercise wrong
OID/checksum/vocabulary, disabled triggers, interrupted bootstrap, active
Attempt/upgrade and insufficient backup/disk preconditions.

These engineering tests do not establish continuous prospective operation or
sustained large-campaign performance.

## 4. Representative actual query plans

Ran `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on the exact read queries using
the real historical run/archive scopes. Plans and SQL are preserved externally.

| Owner | Final execution ms | Scope / interpretation |
|---|---:|---|
| Backtest Dataset identity lookup | 0.018 | Three actual historical Datasets |
| Model training/version lookup | 0.022 | One actual fitted historical ModelVersion |
| Evaluation fold metric states | 0.607 | 23 metric rows; no source-observation multiplication |
| Runtime expired attempts | 0.055 | No active attempts; limited empty-result plan evidence |
| Archive capture observation lookup | 0.271 | 386 historical observations |

The original Evaluation join produced **31,008** intermediate rows for 23
metrics. A red test measured that multiplication, then the query was corrected
to deduplicate exact fold/Evaluation bindings before joining metrics.
Results remain identical; the final join produces 23 rows. No Authority or
metric calculation changed. Small-table sequential scans are not rejected
merely for node type. This does not prove performance of the blocked real
40-session campaign.

## 5. Historical equivalence and zero writes

Exact allowlisted completed WP-17P run:

```text
BacktestRun       8f7b6def-9c63-533e-9777-a5a6c57866e0
definition hash   ac2686e2ef3105e8a5ca5a2a2ece6cfd7821ea84d56ae7611eb1e9b0e7305d78
FIT Dataset       a3f34d1b-f8c2-5026-93a7-f939a14dae36
rule Dataset      dba9a84c-d242-5eaf-a267-df97a1466374
model Dataset     1702b8b9-13ea-5dba-a041-b9e0c53b16be
FIT Evaluation    e5d9e408-fb41-514c-bd16-d4a8fab783be
validation Eval   5ec39747-d375-5100-9dfd-4796ae6ff211
TrainingRun       d68c200e-2426-5124-bd52-e6d38ceb3cfd
ModelVersion      269fc66c-600c-5e13-835a-cf112096fb44
```

Private exact decoder -> FrozenBacktestRun -> Generic planner/executor
inspect/resume -> Generic replay verifier:

```text
matched = true
mismatch_count = 0
expected_actions = 12
execution_state = COMPLETED
business_action_calls = 0
all_database_row_counts_and_ordered_hashes_unchanged = true
all_Artifact_bytes_and_hashes_unchanged = true
```

The connection enforces read-only transactions. The no-business-action executor
would raise if a completed action were executed again. Whole-database
before/after snapshots include Dataset, Candidate, Decision, Outcome,
Evaluation, Model, receipt/audit and Artifact rows, not only the root DTO.

398 Artifacts / 2,382,761 bytes were physically hash-verified; Artifact roster
SHA256 is
`e35d6327c3140835fcf2fb33b3d4c8ccfe01fad453ec4e2afe014a21b57d3255`.
Historical reports/documents/identities were not rewritten.

WP-18: PASS for exact definition/specification equivalence only (four arms,
ten folds, five explicit dependencies, 40 fixture sessions). No historical
multi-fold execution is claimed. Unknown legacy-shaped identity and missing
current specification remain fail-closed; the fixture's dates are not real
campaign trading-session evidence.

## 6. Additive operational upgrade boundary

**Original operational DB upgrade: BLOCKED / NOT_RUN.** The original archive
database was not found on the inspected instances. The primary checkout's
configured legacy connection is also unavailable. A new restored copy cannot
attest to the original operational OID, current counts or active attempts.

The non-destructive rehearsal used the actual historical pre-v2 dump restored
into the new copy above. Before applying the registered `wp18q_track_a_c_v2`
route, recorded exact name/OID/owner, old epoch/catalog, zero active attempts,
disk floor (5 GB), successful pg_dump and readable pg_restore inventory.

```text
prior baseline     9da7396d6dd46e3a896b8845df2ef8619a55d66f1d05285a0dd802d1381dfa98
prior catalog      c5ea34221f82e38358943215e48d4ba3f58bb46d814669dda72d6af28835326a
backup bytes       4831022
backup SHA256      1a73d79d9548b75aa42937e444c532d14bb4d7e27f171b06f6074ed88a8148b4
upgrade receipt    cc3c4efb-91d9-58b4-a8ca-489b2b9b05e5
receipt hash       c1de15ff49663ed4ca4c10aaf0962449008324a6a0a0ae3bef597be969adb5a0
historical digest  7f8aabb3be99a52d4283f13ca4daef086c5b458713a149d4ea2091054785e3ad
```

The existing SchemaManager applied only its registered additive transaction.
Historical row counts/ordered hashes, projected on original columns, and all
Artifact bytes/hash rosters matched before/after. Schema/catalog converged to
the clean baseline. A further full `pg_restore --file=/dev/null` decode passed.

The restored snapshot initially failed archive reconciliation with
`ARTIFACT_INTEGRITY` because its physical verification observations were
older than Market's readability policy. Fresh actual physical observations
were appended through ArtifactApplication, only in the new copy, with current
timestamps. No historical observation or Artifact identity/hash/bytes was
rewritten. The upgrade preservation snapshot precedes those additional
verification/receipt/audit rows. Afterwards both archives and Generic WP-17P
replay matched; a separate whole-database before/after replay snapshot again
proved zero writes.

## 7. Real campaign, report and Alpha funnel

**Real Generic campaign: BLOCKED / NOT_RUN.** Canonical market bars in the
accessible archive span 2026-01-05 to 2026-01-19: **11 distinct sessions**.
The separate materialized qualification archive ID
`94a00500-c867-5ede-bf7d-886fbbd5fcaf` and its canonical source-capture
Authority are absent from the accessible restored databases. Raw objects and
the old operator manifest are not substitutes for that missing lineage.

No validation Outcome was inspected for parameter selection, no parameter
search occurred, and no synthetic or short pilot was presented as the required
>=40-session, 32-symbol, >=2-dependency, four-arm rule/ridge campaign.

| Requested real output | Result |
|---|---|
| Frozen current BacktestSpecification / BacktestRun identity | NOT_RUN_BY_SOURCE_AUTHORITY_BLOCKER |
| Current ModelTrainingRun / ModelVersion | NOT_RUN |
| Current canonical fold/aggregate/slice Evaluation identities | NOT_RUN |
| Standard metrics across Data/Candidate/Context/Signal/Forecast/Portfolio/Risk/Economics/Stability | NOT_RUN; no substitute zeros, NaN or invented metrics |
| Current JSON/Markdown report Artifact IDs/hashes | NOT_RUN |
| Real current campaign inspect/resume/replay and byte stability | NOT_RUN |
| Alpha funnel diagnosis | NOT_DETERMINED; no new canonical campaign Evaluation |

The unavailable archive is an execution prerequisite blocker, not an empirical
finding that Data is the Alpha bottleneck.

## 8. Prospective Runtime reality

Before long retrospective qualification, PostgreSQL-clock inspection found
only restored historical evidence. At the exact audit the prospective archive
`a26fbdb2-fb8c-50d1-8651-00e29cb952cc` had:

```text
due windows           0
overdue slices        160
future/not-due        32
historical captured   1
terminal MISSED rows  0
current generations   0
planning gaps         0
active attempts       0
all attempts          110 SUCCEEDED / 1 FAILED_TERMINAL (historical)
```

**This turn's real prospective result: NOT_DUE on the inspected copy;
original operational state unavailable.** No new live prospective Attempt was
claimed, no future window was awaited, and nothing was backdated. The one old
capture is not this turn's prospective proof. The mandatory true-window gate
therefore cannot pass.

Outcome-path versus point-window definitions, early-window rejection, planning
gap domain/UoW clock and Runtime lease/unknown-effect mechanisms have passing
local tests. Continuous integration is not fully wired: current
`ProspectiveArchiveRuntimeApplication.run_due` selects frozen manifest windows
using PostgreSQL time and does not call generation roll-forward, planning-gap
recording or overdue finalization. No corresponding CONTINUOUS_RESEARCH
integration is established by the claim/fence fixture. This is a concrete
remaining call-chain/qualification blocker, not a second-scheduler proposal.

## 9. Hard-cut and exit decision

Source/import audit retains `Wp17pCampaignOperations`, WP-specific
Model/Evaluation/Decision/Outcome orchestration, prospective facade and generation
dispatch. **No deletion was attempted.** Historical equivalence passes, but
real Generic campaign, real report and real exact campaign replay do not.
Deleting now would violate the approved hard-cut prerequisites.

| Failed / blocked P0 gate | Root cause | Minimum repair boundary |
|---|---|---|
| Real campaign / standard report / real resume-replay | Required canonical qualification archive and source-capture Authority unavailable | Restore exact authority access; freeze and execute the existing Generic path; retain negative/not-estimable results |
| Required prospective Attempt | No real due window in accessible snapshot; original operational state unavailable | Restore operational access and use an actually due existing Runtime claim; do not wait/backdate |
| Continuous prospective closure | Roll-forward/planning-gap/overdue commands not in current generic run_due call chain | Complete and qualify those existing Runtime/Market seams only |
| Original operational upgrade | Exact original DB/OID/current checksum and state unavailable | Original-DB backup/preflight followed by its registered additive route and preservation proof |
| Hard cut | Preceding real proofs incomplete | Retain WP executors until all approved prerequisites pass |

The local PostgreSQL, historical compatibility and test proofs are real but
bounded. They do not produce BACKTEST_PLATFORM=ENGINEERING_QUALIFIED.

## 10. Retained non-final failures and evidence files

- Initial full invocation failed legacy DSN validation because a socket-only
  shorthand lacked a URL host. Retried with an explicit URL host and socket
  parameter; no configuration parser was weakened.
- Default local PG16 had max_locks_per_transaction=64. Recreate/test cleanup
  failed with out-of-shared-memory; those runs were stopped and preserved.
  Final gates use new DBs on the isolated durability-enabled instance.
- Baseline contract tests reproduced ten failures. Historical model/partition
  names were then tested explicitly red before restoring their original names.
  Stale exact inventory tests now enumerate the approved companions and their
  concrete constraints; no failing test was removed.
- The prospective fixture mixed a frozen 2026-09-04 clock with actual
  PostgreSQL lease time. It now aligns only stub test windows with the actual
  lease clock and asserts due-window membership. This is fixture evidence only.
- The existing Market export size test failed. Compact grouped imports/exports
  retain an identical AST; the assertion and public surface remain unchanged.
- The actual query-plan regression failed at 31,008 joined rows versus 23
  metrics, then passed after deduplication.
- A preliminary read-only audit harness used a different SQL whitespace
  prefix, and an inventory query used the wrong session-column name. Corrected
  read-only probes are retained separately; neither failed probe is a PASS.
- The pre-refresh restored archive integrity failures above remain recorded.

External evidence is kept under the task archive directory
`wp18q-final-closure-20260905`: exact command JSONL/JUnit/logs,
`final-schema.json`, `final-catalog.txt`, `final-history.jsonl`,
`final-upgrade-copy.jsonl`, `final-upgraded-history.jsonl`, physical
verification observations, query-plan/source audits and the backup.
Credentials, machine paths, raw backup and generated build files are excluded
from Git. The final evidence manifest records hashes of these files.
Evidence manifest SHA256: `ae0fe5f0fe59762a7a2c2fb3c5fd782f0ece7ef96334a75212bd0ea3887f5865`.
The task-owned disposable PostgreSQL instance was cleanly stopped after the
complete gates; its database files are retained for inspection/reproduction.
`final-candidate.json` records the final containing commit/tree and source/test
tree equality after the documentation commit; the candidate remains unmerged.

```text
RETROSPECTIVE = EXPLORATORY_RETROSPECTIVE
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
Runtime/CLI full cutover = NO-GO
Production = NO-GO
```
