# Repository Hygiene and Truth Rebuild — verification

> **Status:** HISTORICAL
> **Scope:** Local repository engineering and read-only historical reconciliation
> **Evidence ceiling:** No research, Provider, operational or Production promotion

This record is immutable evidence for the implementation below, not a new active
plan. Current development starts at `docs/README.md`. The later delivery commit
adds this record and reconciles documentation; it does not change the verified
source, tests, dependency lock, SQL resources or executable templates.

## Revision and scope

- Baseline `origin/main`: `1581a8f24dabf140a493354ff59b933a42f89f46`;
  tree `6f9c1b169f3f30674b00a58f2ffe2ae44b29edc4`.
- Verified implementation: `3135fd4146986c196dd50df1fd757c53385d8a02`;
  tree `b386c2a4da0c8c09125608b33b5ad496194a00f3`.
- Source tree `fe296ed81315c4668abfb72c1b2e06aae7a57e37`;
  tests tree `587ee2d9774bdb1d9a030c3549b9a07f403f71ed`;
  explicit-history tests tree `5248f79c2cd020a1d38107db39432590540e8dd6`;
  scripts tree `b3e913af199002f07e8a7f9342e5b58ac35b7b53`.
- Local branch: `agent/repository-hygiene-20260908`. No push, PR or merge.
- Original workspace stayed at `10689a4db772be5a546a64448fcc6f39f6988412`.
  Its unrelated `.idea/modules.xml` modification was never edited or staged;
  SHA256 remained `1f4d49d435a7355fdfe18d629e177c419c2464d56446a5200dbed317dba6b040`.
- Independent detached qualification checkout was clean at start and after
  moving this run's generated build outputs into the external evidence folder.
  This task did not mutate operational databases, Provider facts, deployed
  code/configuration or services.

Environment: Python 3.12.13, uv 0.11.7, PostgreSQL 16.15. `uv.lock` SHA256
`5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d`;
`pyproject.toml` SHA256
`41f84a204da321edfa748aac95b428de3f50d6d06e48ef061d469d9c2424fdfb`.
Both files are unchanged from baseline.

## Current truth and disposition

There are eleven current Markdown documents: root README, AGENTS and CLAUDE;
`docs/README.md`; Architecture, Authority Map, Data and Evidence; Current State,
Roadmap, Development and Runtime Runbook. The optional branch-reconciliation
skill remains opt-in; its command is normalized to `uv run python`. It grants no
business or independent planning authority. The archive is never startup context.

The actual installed path is CLI → `bootstrap_application` → composed owner
Applications → Domain/ports → narrow UoW/Repository → PostgreSQL and verified
Artifact bytes → owner queries/reconciliation → report/consumer. Backtest,
prospective Runtime and daily research reuse that composition. Runtime owns due
time, admission, lease and fence; Outcome owns labels; Evaluation owns results;
Report only projects reconciled Authority. The separately installed legacy CLI
and PostgreSQL persistence families still have real consumers: full cutover is
not claimed. The current Architecture and Authority Map name the exact paths.

The generated `docs/architecture/code-inventory.json` indexes all source/script/
operator-template modules, installed entry points, static consumer edges, SQL
references/resources, test functions and support imports. It is a regenerable
index, not reachability, coverage or deployment Authority. Dynamic SQL/imports,
public APIs and historical decoders still require owner review.

| Category | Actual disposition |
|---|---|
| Historical documents | 97 Markdown + 4 JSON files retained byte-for-byte under `docs/archive/pre-hygiene`, with original-path/hash/size manifest |
| Current documents | 11 current Markdown files: 10 rewritten +1 new Development guide; archive navigation also rewritten; old bytes retained; one optional skill command normalized |
| Historical evidence | No Verification/result content deleted or rewritten; archived relative links verified against their original baseline namespace |
| Python commentary | 80 docstrings removed, 57 rewritten; 2 comments removed with their dead function; 2,511 docstrings and 390 comment tokens retained |
| Production code | 11 uncalled private functions + 8 private compiler-only constants removed (815 definition lines); total source diff +59/−971 lines across 130 modules |
| Released SQL | All 113 resources byte-identical; no migration/registered upgrade bundle edits |
| Tests/support | 184 files renamed/rehomed and 18 phase-named functions renamed to contracts; one fixture self-test file (including two builders) removed; 9 test contracts deleted; 6 new hygiene guard contracts; 7 external-history cases moved out of default collection and explicitly executed |
| Overlap/public APIs | Retained where actual consumers or historical interfaces exist; no package deleted merely for zero static consumers |

All 1,079 production Python ASTs match baseline after excluding commentary and
the explicitly enumerated dead definitions/imports. The complete comparisons,
file dispositions, docstring before/after, dead-helper names and SQL hashes are
in the evidence index. Financial expected values, protocol/result identities,
Provider rules and business algorithms were not changed.

AGENTS shrank from 322 to 70 lines while retaining NO_ACTION/HOLD, calibration,
Provider direction and formal Model Governance boundaries.

Deleted test contracts have specific reasons:

- Three catalog-fixture tests only asserted rosters built by their own fixture.
  Exact decoder rejection, current generic execution and real PostgreSQL
  historical reconciliation remain.
- Two phase-local architecture tests prohibited owners that later code already
  implemented. Current import/owner/schema and rejection contracts remain.
- Two line-count/layout tests duplicated stronger import/UoW/composition guards
  or constrained formatting rather than behavior. Meaningful boundary/signature
  assertions in related tests remain.
- Two obsolete documentation snapshots forced legacy script placement, a single
  migration count and historical status prose. Current link/metadata/hygiene
  guards, installed documented CLI smoke, real migration execution and the
  PostgreSQL production-qualification rejection tests remain.
- The shared-ranking contract remains. Its roster no longer lists the module
  whose only ranking consumer was the removed private `_constrain_candidates`.
  It still requires the common kernel for every retained listed consumer.

No exact duplicate test-function bodies justified indiscriminate deletion.
Mocked-port tests for time/error contracts and real legacy account/CLI consumers
were retained. Missing historical prerequisites now fail explicitly rather than
skip. No failure was converted to xfail, no business assertion or research
threshold was relaxed, and no compatibility fallback was added.

## Test-to-contract map

The index covers 3,348 test functions (parameterized collected cases are counted
separately). Categories describe declared contracts, not measured coverage:

| Category | Functions |
|---|---:|
| Domain / serialization | 1,611 |
| Application | 571 |
| PostgreSQL integration | 418 |
| Runtime / recovery | 376 |
| Migration | 222 |
| Architecture | 72 |
| Repository tooling | 37 |
| Research correctness | 34 |
| Explicit historical reconciliation | 7 |

Baseline collection: 4,211 cases. Final retained collection: 4,208 cases =
4,201 default + 7 explicit historical cases (−9 removed +6 added). The new guards
reject current historical-task context, historical commentary, schema drift,
archived-byte corruption and broken internal imports, while retaining immutable
business identity strings and correct relative-import member resolution.

## PostgreSQL and artifact evidence

All qualification scopes use cluster `7682058034626392615`:

| Scope | Database | OID | Allowed use |
|---|---|---:|---|
| Disposable full tests | `mra_hygiene_final_20260908` | 179492867 | Fresh/migration/concurrency/failure fixtures |
| Fresh installed wheel | `mra_hygiene_wheel_313520260908` | 179635349 | Independent bootstrap and schema verification |
| Existing completed restore | `mra_wp18q_r2_completed_restore_20260906` | 118013570 | Read-only historical tests only |

Installed schema: epoch `MRA_REFOUNDATION_1`, release `DRAFT`, 194 research
tables. Baseline SQL SHA256
`f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27`;
catalog checksum
`44a27e01109567395ad803e0c0c3b2859e8890fb23cf27b0b2c26b98db559e51`.
The separate legacy migration catalog is not added to this research table count.

The historical connection enforces `default_transaction_read_only=on`. The
completed allowlisted Run `8f7b6def-9c63-533e-9777-a5a6c57866e0` is verified with
its actual restored Artifact root. All seven retained historical cases execute
owner replay, zero-write checks, exact specification equivalence, batched Outcome
and Model input checks, and representative query plans. No restored success is
copied to the original failed campaign or promoted to original-scope continuity.

The independent wheel installation matches 1,192 source/SQL files byte-for-byte,
passes all seven installed CLI help commands and all 29 documented CLI surfaces,
and bootstraps/verifies its own fresh database. Build identities:

- wheel SHA256 `4e27ee70e66446c9118f139fa5bbb14d03648b19ef8a343e6751654b7e74c438`,
  3,828,737 bytes;
- sdist SHA256 `a78f47f746102c5babbc9914db5204ccbb8855d77424514f7cfedb330df15617`,
  3,068,916 bytes.

## Executed gates

| Command / check | Result | Exit | Seconds | Raw log |
|---|---|---:|---:|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS | 0 | 3.228 | `closure-sync.log` |
| `uv run python scripts/check_docs_links.py` | PASS | 0 | 0.182 | `closure-docs.log` |
| `uv run python scripts/check_repository_hygiene.py` | PASS | 0 | 25.6 | `closure-hygiene.log` |
| `uv run python -m ruff check .` | PASS | 0 | 1.618 | `closure-ruff.log` |
| `uv run python -m mypy` | PASS | 0 | 20.274 | `closure-mypy.log` |
| `uv run python -m build` | PASS | 0 | 13.77 | `closure-build.log` |
| `uv run python -m pytest -x --durations=20 --junitxml=$EVIDENCE/closure-full-pytest.xml` | PASS | 0 | 2361.564 | `closure-full-pytest.log` |
| `uv run python -m pytest -q tests_historical --junitxml=$EVIDENCE/closure-historical-pytest.xml` | PASS | 0 | 3.319 | `closure-historical-pytest.log` |
| `uv run --no-project --python $WHEEL_ENV/bin/python $EVIDENCE/verification-scripts/hygiene_wheel_smoke_closure.py $QUALIFICATION $EVIDENCE` | PASS | 0 | 41.839 | `closure-installed-wheel.log` |
| `uv run python $EVIDENCE/verification-scripts/hygiene_documented_cli_closure.py $QUALIFICATION $EVIDENCE` | PASS | 0 | 22.367 | `closure-documented-cli.log` |
| `uv run python $EVIDENCE/verification-scripts/hygiene_preservation_closure.py` | PASS | 0 | 35.887 | `closure-semantic-proof.log` |
| `git diff --check` | PASS | 0 | 0.042 | `closure-diff-check.log` |

The documentation-only delivery edits were then checked without changing the
verified implementation/source/test trees:

| Command | Result | Exit | Raw log |
|---|---|---:|---|
| `uv run python scripts/check_docs_links.py` | PASS | 0 | `delivery-docs.log` |
| `uv run python scripts/check_repository_hygiene.py` | PASS | 0 | `delivery-hygiene.log` |
| `uv run python -m pytest -q tests/scripts/test_check_docs_links.py tests/scripts/test_repository_hygiene.py` | PASS | 0 | `delivery-document-tests.log` |
| `git diff --check` | PASS | 0 | `delivery-diff-check.log` |

The documentation regression contains 13 passing cases already represented in
the retained suite; these are reruns, not additional unique test counts.

Full retained Python result: **4,201 default cases plus four subtests; seven explicit historical cases; zero failures/errors/skips**. The complete default invocation uses
an explicitly disposable PostgreSQL URL; tests are not collected-only evidence.
JUnit, exact command arrays, revision, exit code, elapsed time and raw logs are
preserved. Remote Actions: NOT_RUN (local-only delivery); Provider capture,
operational upgrade/service changes and research campaigns: NOT_RUN/out of scope.

Failures and interrupted runs are retained:

1. The new hygiene guard initially failed before implementation (expected red).
2. The first relocated collection exposed a seventh historical query-plan test
   importing the removed path. It was moved with its six peers; all seven pass.
   A dangling-internal-import guard now catches that class of failure.
3. Initial `git diff --check` found original archived Markdown hard-break spaces
   and two new EOF blanks. The archive bytes were preserved with a single-path
   whitespace attribute; current test formatting was corrected. An initial
   checkpoint had proceeded after the check failure; the correction is a later
   visible commit, not a rewritten history.
4. The final dead-helper audit exposed two cascading unused helpers; the prior
   owned regression was interrupted and replaced with the corrected version.
5. The stale ranking-consumer roster failed independently and in full regression.
   Its red log, minimal roster correction and green rerun are retained; the
   owned obsolete run was interrupted and the final full suite rerun.

6. Current main already had stale Model schema expectations (eight tables versus
   the actual ten), a table-name namespace omission, and a two-migration seed
   count versus the four registered resources. Exact roster/constraint/trigger
   and migration-name/hash checks now cover the actual schema; business rows
   must still remain empty after bootstrap.
7. Historical upgrade tests wrongly supplied the current vocabulary checksum to
   old epochs. They now freeze each historical identity and reject mixed epochs;
   no registered route or SQL bytes were changed. The remaining-suite precheck
   retained its eight failures, and the repairs passed 36 focused tests before
   the final freeze. An intermediate test-edit mistake in the expected constraint
   list also remains in its failed log and corrected rerun.

An additional `git diff --check` invocation used the external non-Git evidence
directory and exited 129; the same check passed in the correct worktree. Its
invocation-error record is retained separately from test failures.

The two retired prose snapshots are distinct from these repaired executable
schema/upgrade contracts: no failed business invariant was discarded.

## Evidence and remaining debt

See [the immutable evidence index](Repository-Hygiene-Evidence-2026-09-08.json).
`cleanup-final.json` contains each disposition and reason;
`closure-semantic-preservation.json` proves source/SQL preservation;
`closure-*.json/log/xml` bind final commands and outcomes.

The index is an immutable pointer to this run's recoverable external raw logs,
commands, test XML, audit dispositions, reproducibility scripts and build bytes.
It is not a new business Authority. Archived original documentation remains
self-contained in Git with byte hashes; external databases/Artifacts remain
separate identified scopes.

Remaining architectural debt: two persistent/CLI families; overlap among
`research`, `research_qualification`, `platform` and historical applications;
large composition/orchestration modules; some retained source-text architecture
guards; dynamic/public/history consumers requiring explicit migration evidence.
These are recorded in the single current Roadmap. No speculative package
merger, Runtime cutover, registry or new research capability was introduced.

`REPOSITORY_HYGIENE_EXIT_GATE_PASS = YES`.

This gate qualifies repository hygiene at the recorded implementation. It does
not change frozen research/operational exit gates, financial maturity, Alpha,
Model or Production admission. Alpha proven: NO. Production admission: NO.
