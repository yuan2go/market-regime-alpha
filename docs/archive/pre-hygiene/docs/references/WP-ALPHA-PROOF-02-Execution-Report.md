# WP-ALPHA-PROOF-02 Execution Report

> **Status:** HISTORICAL
> **Authority:** Exact PostgreSQL and physical-owner execution record
> **Protocol:** [WP-ALPHA-PROOF-02 Frozen Vertical Slice Protocol](../research/protocols/WP-ALPHA-PROOF-02-Frozen-Vertical-Slice-Protocol.md)
> **Last Updated:** 2026-08-26

**Git baseline:** `main@adbc7857e261835eccbe2acf4902910363dae724`;
frozen design checkpoint `a926b95`.

**Delivery:** implementation head `ded5f6e` was merged through PRs #76 and
#77; `main@8e71535f06d29c148d8588d8ab142d14d4b99364` contains the complete
code, tests, terminal evidence and local-campaign ignore rule. This delivery
record is documentation-only and does not revise the frozen Experiment or its
negative result.

## Conclusion

The pre-registered three-factor, higher-is-better, equal-weight Top-5 hypothesis
is **REJECTED at Discovery** and the independent physical correctness campaign
is **CORRECTNESS_FAILED**. Formal PIT is `PIT_INCOMPLETE`. Consequently the
frozen External experiment was not admitted, Locked OOS Outcomes were not read,
and Candidate, Conditional Forecast, Strategy Economics and qualification remain
`NOT_ESTIMABLE / BLOCKED_BY_CORRECTNESS`. No direction, factor, Top-K, cost,
threshold, target, window or stopping rule was changed after observing results.

## Exact owners and scope

- Experiment: `research-experiment-definition:d242097bff7299a4ed61745aa4f6272807d83a549178ac2c0af268b261db6315`.
- Raw owner: `historical-data-owner-c744a67a4ec2113a2bdb4e13`.
- Normalized owner: `historical-data-owner-6dcb5f3850c7909b8c15428d`.
- Discovery run: `historical-research-run-0382e3c92084432a7d7b9c36`.
- Discovery evidence: `historical-evidence-f61fffd7e47cfcb901f5932e`.
- Correctness evidence: `historical-evidence-fda0316e89f0c9e8275a3710`.
- Locked scope: `frozen-locked-oos-scope:ed65a20e87fba32e48194f3c74592d880defa8ec972e593aa69f84217751c8b3`.
- Discovery contains the frozen 126 decision sessions from 2025-01-02 through
  2025-07-11. Exact Historical replay matched the materialized run.

The reacquired corpus covers 2025-01-02 through 2026-08-24 with 338 union
symbols, 134,134 Daily bars and 6,414,384 five-minute bars (6,548,518 total).
All 1,408 package files passed physical checksum verification. Independent Raw
normalization compared all 6,548,518 observations and produced identical
logical hashes. BaoStock still supplies retrospective event time without
historical `available_at`; this is not Formal PIT.

Physical package integrity and Raw→Normalized reproduction are `SUPPORTED`.
The broader Feature→Target correctness conclusion is nevertheless
`CORRECTNESS_FAILED`; these two statements are intentionally distinct.

## Discovery evidence

For `alpha:INTRADAY_CORRECTNESS_CHALLENGER` under the frozen higher-is-better
directions:

| Metric | Result |
|---|---:|
| Population before / after | 19,522 / 19,522 |
| Mean RankIC | -0.0911379 |
| ICIR | -0.496474 |
| Positive IC ratio | 0.348485 |
| RankIC p-value | 0.00005498 |
| BH-FDR adjusted p-value | 0.00173193 |
| Top-5 gross return | -0.00089056 |
| Top-5 assumed-cost net return | -0.00299088 |
| Top-5 spread | -0.00321952 |
| Top-5 turnover | 0.9744 |
| Top-5 max drawdown | -0.249272 |

The significant sign is adverse to the pre-registered direction. It is not an
invitation to reverse the factors under the same Experiment identity.

## Correctness and evidence ceiling

The correctness proof is
`alpha-correctness-proof:9196bf13d40dde78f50ab3314ac511d05f952f91b4075bf5f201c755eeb1067b`
with terminal status `CORRECTNESS_FAILED`:

- Features: 37,722 supported and 78 partially reproduced out of 37,800.
- Targets: 37,367 supported, 425 partially reproduced and 8 failed out of
  37,800.
- All eight failures are `PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE`.
- Missing/corporate-action cases remain explicit, including 424 unavailable
  targets, 77 missing five-minute checkpoints and 347 corporate-action policy
  fail-closed observations.
- Frozen placebo, permutation, lag, time-shift, redundancy and moving-block
  inference were executed; no failed result was removed or relaxed.

Therefore:

```text
FORMAL_PIT = PIT_INCOMPLETE
PHYSICAL_CORRECTNESS = CORRECTNESS_FAILED
DISCOVERY_REPRODUCED = REJECTED
EXTERNAL_VALIDATED = NOT_ESTIMABLE / BLOCKED_BY_CORRECTNESS
ALPHA_SUPPORTED = REJECTED
LOCKED_OOS_CONSUMED = false
LOCKED_OOS_SUPPORTED = NOT_ESTIMABLE
FORECAST_BASELINE_BEATEN = NOT_ESTIMABLE
CALIBRATED = false
NET_ECONOMICS_SUPPORTED = NOT_ESTIMABLE
STRATEGY_QUALIFIED = false
PROSPECTIVE_READY = ENGINEERING_READY_EVIDENCE_INACTIVE
PROSPECTIVE_PROVEN = false
PRODUCTION_QUALIFIED = false
```

Strategy Economics and Portfolio evidence for the Discovery run are both
`NOT_ESTIMABLE`: no admissible Strategy Path Outcome exists. Context hard-gate
diagnostics show the current Capital hard gate reduces 19,522 observations to
zero; that is evidence of over-gating, not authority to alter the frozen
protocol or activate an unvalidated Context.

## Performance

- Acquisition: 7,480/7,480 provider requests; resumable checkpoint campaign.
- Independent normalization: 1,194.95 seconds; peak RSS approximately 4.62 GiB.
- Discovery materialization: 126 sessions through bounded six-stage commits;
  the final 55-session drain took 3,287.99 seconds, peak RSS 3.07 GiB.
- Discovery evidence aggregation: 315.44 seconds, peak RSS 3.12 GiB.
- Correctness: 3,441.24 seconds, peak RSS 4.89 GiB.
- Exact Historical replay: 4,117.70 seconds, peak RSS 3.84 GiB.
- Artifact Root: approximately 1.5 GiB; campaign PostgreSQL database was
  1,528 MiB at final catalog inspection.

Repeated immutable-file verification now memoizes SHA-256 only while the exact
device/inode/size/mtime/ctime signature is unchanged. Physical mutation forces a
new hash and still fails closed. The remaining dominant cost is per-session
business materialization and JSON decoding, not provider I/O.

## Engineering convergence and validation

Packaged migrations are contiguous and checksummed through 104. Fresh
001→104, explicit 097→104 upgrade, idempotency, concurrent serialization,
append-only Locked-scope ownership, exact owner reload, acquisition
interruption/resume, corruption rejection, Historical replay and Continuous
recovery tests pass against PostgreSQL 16.14. Catalog inspection reports 280
application tables in the migrated schema; neither Repository construction nor
Runtime execution applies migrations implicitly.

Full regression initially exposed stale test contracts rather than positive
research evidence: current-head assertions still named migration 097/98, four
forward-upgrade fixtures had already auto-migrated to 104, one CLI fixture had
not published the typed Calendar owner required by migration 101, and one
visualization test plus its sample CSV still referenced the duplicate
backtesting plane retired in `da66b41`. The tests now exercise the actual
canonical owners; the orphan visualization test/data are deleted. The final
validation ledger is:

| Command / scope | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS after one disk-capacity retry |
| docs links + docs pytest | PASS |
| `tests/platform` | PASS |
| focused PostgreSQL migration/replay/recovery/append-only/corruption tests | PASS |
| full `python -m pytest -q` | PASS |
| Ruff | PASS |
| mypy (423 source files) | PASS |
| build | PASS |
| `git diff --check` | PASS |

Two interrupted validation attempts are retained as environment history: the
host ran out of disk while PostgreSQL was generating test-schema WAL. After
removing only rebuildable caches and the orphan test schema, both migration and
full suites were rerun from the beginning to PASS. No campaign owner or
physical artifact was removed or mutated.

## Research routing

Do not execute External or Locked OOS for this Experiment. Preserve the eight
correctness discrepancies and the adverse-sign Discovery evidence. The next
highest-information work is to explain the Target-source reproduction failures
and the time-shift control behavior under a new, explicitly frozen correctness
revision. Any reversed factor direction is a new hypothesis/Experiment and must
not reuse the untouched Locked roster as if it belonged to this failed family.
