# WP-17P Prospective Archive and Exploratory Backtest Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP17P_ENGINEERING_EXIT_GATE_PASS`
> **Authority:** Immutable exact-SHA engineering and bounded real-execution ledger; not Provider Qualification, Formal PIT, Formal OOS, Prospective value, Alpha, Model Qualification, Runtime/CLI Cutover, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-03 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@f67a4f34761516dab65825c38c4e81019f8c2dd1`
> **Implementation Checkpoint:** `5cc3831e93fa30a58283471e2185bbad5c72cec3`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP17P_ENGINEERING_EXIT_GATE = PASS

RETROSPECTIVE_2026_BACKFILL = PARTIAL_WITH_PENDING_NOT_DUE
RETROSPECTIVE_PILOT_CAMPAIGN = COMPLETED
RETROSPECTIVE_EVIDENCE_CEILING = EXPLORATORY_RETROSPECTIVE

PROSPECTIVE_ARCHIVE = STARTED
FIRST_PARTY_KNOWN_TIME = ACCUMULATING
PROSPECTIVE_PROVEN = NO

MODEL_RUNTIME = OPERATIONAL
BASELINE_BACKTEST = COMPLETED
MODEL_BACKTEST = COMPLETED
MODEL_CHALLENGER = NOT_ESTIMABLE
MODEL_QUALIFIED = NO

FORMAL_PROVIDER_QUALIFICATION = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover = NO-GO
Production = NO-GO
```

This Verification proves an engineering-qualified two-lane archive and one
bounded real exploratory campaign. It does not reinterpret the immutable
WP-15 BaoStock `REJECTED` Provider Decision or the WP-16 external-evidence
blocker. Real BaoStock bytes captured during WP-17P remain exploratory or
first-party observation evidence; they are not a qualified vendor publication
or finality contract.

## 1. Baseline, branch, and exact identities

WP-17P fetched the latest remote main, created an independent branch and linked
worktree, and left the primary checkout and its unrelated local configuration
untouched. Historical immutable Verifications were read only.

```text
remote                         git@github.com:yuan2go/market-regime-alpha.git
origin/main baseline           f67a4f34761516dab65825c38c4e81019f8c2dd1
branch                         agent/wp-17p-prospective-archive
worktree                       market-regime-alpha-worktrees/wp-17p-prospective-archive
implementation checkpoint      5cc3831e93fa30a58283471e2185bbad5c72cec3
root tree                      2c8cb1fd07bfdecb6b726e374e675765fee4a446
source tree                    7f5f46d771b4a53c1b22fcaa435a9b750cac28ed
tests tree                     7aacee077254783875b7c3c66bb2dd15083f4b6a
Research Qualification tree   92efab1dd8cefce89880a5d639f0f3110599b57d
Market tree                    a4872e6c29927126658db0a9a89632fc6ceafb24
Runtime tree                   b01c45b9ca7009fe8ddc9cba227f2f656473c6c1
target baseline blob           351450dcfda986a00ca2252a3d0bacb58137c21a
target baseline SHA-256        2faf445b96aaa9f89f13c59094e35af23d5b5142270ee465a9e7d483aa330c26
WP-15 Verification blob        4f642c897ced4d442fc15492d819943f6a7cf3a7
WP-16 Verification blob        4a1e816211a9cff0884166697e9dbdbb82407ea7
```

The implementation was advanced through dependency-coherent documentation,
Market archive, dual-clock, Model, Decision Support, Outcome, Evaluation,
campaign/replay, and correctness checkpoints. Qualification changes after the
first implementation freeze produced new exact SHAs and caused affected gates
to be rerun. The final two corrections at the verified SHA bound schema-only
migration lock waits while restoring the five-second business lock budget, and
prevented any prospective observation before its frozen event window.

## 2. Permanent evidence-lane separation

Market owns two closed archive lanes:

```text
RETROSPECTIVE_BACKFILL
PROSPECTIVE_CONTEMPORANEOUS
```

Retrospective facts freeze a real PostgreSQL archive-seal
`knowledge_cutoff` and an earlier historical `simulated_event_cutoff`.
Their evidence class is database-fixed to `EXPLORATORY_RETROSPECTIVE`.
Ordinary PIT continues to require `known_at <= DecisionTime`; no ordinary
resolver was weakened. Formal Provider visibility, Formal Dataset/PIT,
LOCKED_OOS, and PROSPECTIVE admission reject retrospective bindings.

Prospective archives freeze PostgreSQL `archive_start_at`, exact event windows,
schedule slots, Provider Product, exchange calendar, instrument roster,
code/config Artifacts, and provenance. PostgreSQL and the Application command
reject observations before the frozen window. Backfill cannot enter this lane.
Repeated content is retained as an observation relation and never inferred as
vendor finality.

## 3. Archive operations and real Provider integration

Market owns immutable archive root, complete slice roster, capture
observations, typed gaps/resource stops, and retrospective seal. Runtime retains
leases/fences; no second Runtime exists. The controlled operator supports
start, resume, retry, inspect, gap/revision report, and daily health through
Application commands. Remote I/O and Artifact byte publication occur outside
short PostgreSQL business transactions.

The BaoStock archive adapter records exact request identity, response fields
and rows, response error metadata, raw bytes, Artifact hash/size, capture
times, PostgreSQL `known_at`, and normalized Market revisions. Missing
historical publication/finality metadata remains `UNKNOWN`; capture time and
bar event time are never inflated into `source_available_at`.

The archive planner freezes one explicit exchange calendar per campaign. The
final XSHG pilot contains exactly 32 stable-hash-selected XSHG instruments;
SSE/SZSE cross-calendar mixing is rejected. This roster is an engineering
scope, not a representative A-share or CSI300 research conclusion.

## 4. Canonical retrospective Model/backtest chain

The exploratory run freezes complete ordered arms, chronological FIT and
VALIDATION folds, purge and embargo sessions, Target, policies, Decimal
`ASSUMED_COST`, seed, code/config Artifacts, archive seal, and provenance.
Canonical owners remain the truth chain:

```text
Archive seal
→ Dataset / Feature
→ Candidate
→ DecisionRun / Context / Signal / Forecast / Opportunity / Portfolio / Risk
→ DecisionTargetCommitment
→ MarketTargetOutcome
→ ResearchPartition / Experiment / Evaluation
→ ModelTrainingRun / ModelVersion
→ later validation ForecastModelBinding
```

`ExploratoryBacktestRun` is predeclaration and lineage only; it does not own a
parallel label, portfolio, risk, or metric store. The Model family and Version
are optional Research & Qualification Authority. The deterministic ridge
trainer consumes only complete FIT Evaluation inputs, freezes its sample
roster, seed, algorithm, fitted Artifact, and coefficients, and can bind only a
strictly later validation fold. Same-generation/fold feedback is rejected.

Evaluation metrics are sourced by concrete relational bindings to Outcome,
Candidate, Signal, Forecast, Portfolio, cost assumption, and Risk Authority.
Every protocol metric has the complete metric-member matrix; unavailable,
failed, excluded, and `NOT_ESTIMABLE` states are not dropped.

## 5. PostgreSQL schema and qualification

The unreleased `001_baseline.sql` remains the only target migration. WP-17P
adds 36 typed tables: six Market capture-normalization bindings; six archive
tables; three retrospective Universe/Eligibility/Dataset bindings; seven
backtest root/feature/arm/fold/session/cost/Dataset bindings; one retrospective
Decision Run binding; five Model/training/version tables; one
`forecast_model_binding`; and seven canonical Evaluation source tables.

```text
PostgreSQL                       16.14
tables                           165
views                            4
indexes                          1,184
constraints                      1,618
functions                        130
non-internal triggers            339
catalog objects                  3,441
baseline checksum                2faf445b96aaa9f89f13c59094e35af23d5b5142270ee465a9e7d483aa330c26
catalog checksum                 351270cbd354a4a914d5664ccf7c551b6b807cb0696d1b04a9156a38c6c8511f
seed checksum                    9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
reference vocabulary checksum   65168428b2edecf6434454c32a4c5f4e6b96e706ec047466153e6c9ef87e4c25
```

A fresh disposable PostgreSQL database was bootstrapped, verified, recreated
under the guarded exact database OID `569275499`, and verified again with the
same baseline/catalog/seed/vocabulary checksums. The recreate plan hash was
`fa8924782b9a26e91719e84a9f9f72cb28bc35329931b4cffeb18bf98240030c`
and challenge `aa7b4f5e8d5f91a9c6d4261e`.

Focused concurrency/failure/recovery coverage proves exact duplicate replay,
changed-request rejection, concurrent slice/capture/revision convergence,
lease/fence failure, stale-fence zero writes, resource stops, provider timeout
and malformed response gaps, partial rollback, unknown-result exact recovery,
Model input immutability, chronological/purge/embargo leakage guards, complete
Evaluation Cartesian rosters, and completed-campaign replay.

## 6. Engineering command ledger

| Command / check | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| final explicit WP-17P focused manifest | PASS, 103 tests |
| `uv run pytest -q tests/refoundation` | PASS, 734 tests |
| `uv run pytest -q tests/platform` | PASS, 33 tests |
| `uv run pytest -q tests/persistence/postgres` | PASS, 288 tests on a fresh disposable database |
| `uv run pytest -q` | PASS, all 3,776 tests on a fresh disposable database |
| clean bootstrap / verify / guarded exact-OID recreate / verify | PASS |
| `uv run ruff check .` | PASS |
| `uv run python -m mypy` | PASS, 603 source files |
| `uv run python -m build` | PASS, sdist and wheel |
| `uv run python scripts/check_docs_links.py` plus docs test | PASS |
| architecture/import test manifest | PASS, 22 tests |
| representative `EXPLAIN (ANALYZE, BUFFERS)` | PASS |
| read-only archive/backtest/Decision/Evaluation reconciliation | PASS, `matched=true`, `mismatch_count=0` |
| exact campaign replay byte comparison | PASS |
| `git diff --check` | PASS |
| remote CI | `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` |

The first persistence-suite attempt recorded one transient PostgreSQL
`LockNotAvailable` inside an existing runtime regression. The exact test passed
in isolation, and the complete 288-test suite passed from zero on a second
fresh disposable database. No business lock timeout was widened. The first
full-suite attempt reached 51% and stopped with PostgreSQL `DiskFull`; this was
not reported as a code PASS. Only the exact disposable test database and pytest
temporary directory were removed. With 5.8 GiB available, the entire 3,776-test
suite was rerun from 0% and passed. No operational database or Artifact was
deleted or recreated.

## 7. Real retrospective execution

### 2026 backfill operations lane

The isolated operational database `mra_wp17p_archive_f5d5130d` and Artifact
root `wp17p-f5d5130d` retain archive
`3829aaa6-d8ee-5eaf-948e-d48398697593`:

```text
event coverage                   2026-01-01 through 2026-09-03
planned slices                   907
captured slices / raw Artifacts  843 / 843
pending NOT_DUE                  64 current-date daily/5m slices
typed gaps / resource stops      0 / 0
raw Artifact bytes               29,546,537
raw Artifact roster SHA-256      9257b36ef1c239c665008cd530006f7b71e7b3e6f1428d858fd55b542e517f9f
normalized revisions             265,714
revision roster SHA-256          c3991fa51070e01158b4c5eb9705447d61f4832bbc53006a9ee3e27af7e97749
status                           PARTIAL_WITH_PENDING_NOT_DUE
```

The 64 current-date slices were not forced before their frozen due time and the
archive was not falsely sealed complete. Resume remains safe and exact.

### Exact-SHA XSHG-32 campaign archive

The final verified implementation used a separate operational database and
Artifact root:

```text
database                         mra_wp17p_campaign_5cc3831e_g14
database OID                     587604756
Artifact root                    wp17p-campaign-5cc3831e-g14
retrospective archive            5b138e9b-232c-59bb-9307-490dd2b21c4e
seal                             cf8eb599-bf3a-4095-af80-dd638613b5b9
seal knowledge cutoff            2026-09-03T10:54:52.402360Z
slices / captures / Artifacts    386 / 386 / 386
normalized revisions             19,533
typed gaps / resource stops      0 / 0
capture roster SHA-256           8c7ff6eecec3da59cef593240a093f138939d7f9215f7278efdddd72fafc144d
Artifact roster SHA-256          a6705fa24b690afbc2ac5c949ed82cd678a1fbb8d2c41c15e36f7aa5eb868b81
revision roster SHA-256          5ecdc1bcb215034b7ad062c472230a73829c02089333bc336172dfd1365d3233
seal content SHA-256             06ddeda0ace2c0de10620574994ee0af0c503d93bf0265fb4f5b11b72fdef246
```

The exact stable-hash roster is frozen in the campaign config Artifact and
contains 32 XSHG instruments. It is not a claim about all CSI300 members or
all A-shares.

## 8. Dataset, Model, and exploratory results

The campaign created one FIT Dataset and two same-input validation Datasets,
each with 32 rows, one Feature, 32 available cells, and zero missing/unknown
cells. Their exact identities are:

```text
FIT Dataset                      a3f34d1b-f8c2-5026-93a7-f939a14dae36
baseline validation Dataset      dba9a84c-d242-5eaf-a267-df97a1466374
model validation Dataset         1702b8b9-13ea-5dba-a041-b9e0c53b16be
FIT Evaluation                   e5d9e408-fb41-514c-bd16-d4a8fab783be
validation Evaluation            5ec39747-d375-5100-9dfd-4796ae6ff211
ModelTrainingRun                 d68c200e-2426-5124-bd52-e6d38ceb3cfd
ModelVersion                     269fc66c-600c-5e13-835a-cf112096fb44
training samples                 32 / 32 estimable
algorithm / alpha / seed         deterministic_ridge / 0.01 / 1729
fitted Artifact SHA-256          42ec227261511e20e593ad118903c718e579224bb8cb5d8578cc67a08428a362
```

The descriptive result is deliberately non-positive and retains
not-estimability:

| Metric | Rule baseline | Model challenger |
|---|---:|---:|
| mean Target return | `0.00002683702730307253125` (n=32) | `0.00002683702730307253125` (n=32) |
| RankIC | `NOT_ESTIMABLE` (n=0) | `NOT_ESTIMABLE` (n=0) |
| forecast coverage | `NOT_ESTIMABLE` (n=0) | `NOT_ESTIMABLE` (n=0) |
| selected ratio | `0.15625` (n=32) | `0.15625` (n=32) |
| signal coverage | `0` (n=32) | `0` (n=32) |
| exposure / turnover | `0 / 0` | `0 / 0` |
| gross / assumed-cost net | `0 / 0` | `NOT_ESTIMABLE / NOT_ESTIMABLE` |
| drawdown | `0` | `NOT_ESTIMABLE` |
| risk rejection rate | `0` | `NOT_ESTIMABLE` |

The FIT model mean is `-0.00098328155692452915625` over 32 samples. No metric
supports Model qualification, Alpha, cost realism, or Production value.
`ASSUMED_COST` remains an assumption, not empirical transaction-cost evidence.

The same frozen campaign request returned byte-identical business identities
on replay. Archive, backtest, three Decision Runs, and two Evaluation Runs all
reconciled with `matched=true` and aggregate `mismatch_count=0`.

## 9. Prospective start and accumulation ceiling

Generation 15 started a separate prospective archive in the final operational
database:

```text
archive                          a26fbdb2-fb8c-50d1-8651-00e29cb952cc
archive_start_at                 2026-09-03T10:58:05.079157Z
first frozen window              2026-09-03T10:59:04.182722Z
next real XSHG session           2026-09-04
planned slices                   193
early request result             NOT_DUE / no capture / no observation
due smoke capture                944eb378-7693-4c0e-8dc1-7e6db231de5b
captured / pending               1 / 192
on-time observations             1
typed gaps / resource stops      0 / 0
observed Artifact bytes          269
observed Artifact roster hash    7d8a4ac235a18aa0163dda718e863e5034e9be4eb98331dc88c50e1f3106591e
archive reconciliation           matched=true / mismatch_count=0
```

The remaining schedule freezes Decision-near, post-close, evening, next-session
pre-open/post-close, and later verification windows. Those future slices are
not executed or claimed here. Only captures actually recorded inside future
windows may accumulate prospective Decision evidence. One start smoke cannot
prove sustained Prospective value.

## 10. Representative plans and retained failures

`EXPLAIN (ANALYZE, BUFFERS)` was executed on the populated final operational
database for due-slice discovery, exact archived 5-minute feature resolution,
cutoff-visible exact Outcome revision, Model training sample roster, and the
Evaluation metric-member Cartesian reconciliation. Exact feature, Outcome,
Model, observation, Artifact, and successor paths use FK-leading indexes. The
planner chose sequential scans for the 579-row archive-slice table and
1,440-row metric-input table; these bounded scans showed no join explosion or
lock amplification and are not pinned to a node shape.

Earlier operational generations are retained as debugging/negative evidence:

- cross-exchange security/session mismatches failed before a valid campaign;
- invalid purge-bound generations failed closed;
- the first successful prior-SHA campaign remains reproducible but cannot
  qualify the final implementation SHA;
- prospective generation 13 contains one pre-window observation produced
  before the final due guard and now fails reconciliation as `EARLY_OBSERVATION`;
  it is preserved and never counted as prospective evidence.

None was deleted, relabeled, or used to hide a failed member.

## 11. Evidence ceiling and next action

```text
WHAT_IS_PROVEN = TWO-LANE ARCHIVE ENGINEERING;
                 DUAL-CLOCK EXPLORATORY RESEARCH;
                 EXACT-SHA REAL XSHG-32 BACKFILL/CAMPAIGN;
                 DETERMINISTIC BASELINE/MODEL EXECUTION;
                 FIRST-PARTY PROSPECTIVE ARCHIVE STARTED

WHAT_IS_NOT_PROVEN = PROVIDER HISTORICAL PUBLICATION OR FINALITY;
                     FORMAL PIT; FORMAL OOS; PROSPECTIVE VALUE;
                     MODEL QUALIFICATION; ALPHA; COST REALISM;
                     RUNTIME/CLI CUTOVER; TRADING; PRODUCTION

NEXT_REQUIRED_ACTION = RUN THE FROZEN FUTURE CAPTURE WINDOWS;
                       RESUME THE 64 DUE BACKFILL SLICES WHEN DUE;
                       ACCUMULATE REVISION OBSERVATIONS;
                       REOPEN WP-16 ONLY WITH ITS EXTERNAL RE-ENTRY EVIDENCE
```

WP-17P ends here. It does not authorize a Formal campaign, calibration,
parameter mining, broker work, automatic execution, or Production admission.
