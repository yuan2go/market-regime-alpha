# WP-ALPHA-CORRECTNESS-02 Execution Report

> **Status:** HISTORICAL
> **Authority:** Exact PostgreSQL and reacquired-physical-owner execution record
> **Protocol:** [WP-ALPHA-CORRECTNESS-02 Frozen Protocol](../research/protocols/WP-ALPHA-CORRECTNESS-02-Frozen-Protocol.md)
> **Last Updated:** 2026-08-27

**Starting baseline:** `origin/main@1a92ee41b02dd94df9ef4488c59cba55df4674ce`.
The executed Experiment is bound to correctness code revision
`8cd79972fa96d397967948d75592f5163613e02a`; later test/documentation commits
do not alter its immutable identity or result.

## Conclusion

The final correctness Evidence is **`INCONCLUSIVE`**, with proof status
**`PARTIALLY_REPRODUCED`**. Raw-to-Normalized reproduction matched all
6,548,518 observations, all 37,800 persisted Target semantic results matched
an independent reconstruction, and 37,722 of 37,800 Feature rows were fully
reproduced. All 113,166 independently reconstructed Feature ranks match. The
remaining 78 Feature rows were honestly partial because their Decision-time
source bars were missing or not estimable.

This is not positive Alpha evidence. All three frozen higher-is-better Factors
have adverse mean RankIC, the three-factor challenger remains economically
negative, the Factors are partially redundant, and the target-time-shift
controls dominate the real Factors. Consequently the result is `NO-GO`:
External Validation, Locked OOS Outcome access, Candidate/Forecast promotion,
Strategy qualification, trading authority and Production remain closed. No
Target, direction, threshold, Top-K, cost, Universe, sample or statistical rule
was changed after observing results.

## Exact identities and scope

- Experiment:
  `research-experiment-definition:543d539cc172a00926aa186657ad6ed2f94a87239fdb262be070cf8d22794a60`.
- Target protocol:
  `outcome-target-protocol:4aefda5e5c76883a01ca7ec01d21e2f3633d385afd9c8e8a87f2c21fa0052bcb`.
- Target semantics:
  `target-semantic-specification:7b93416252c0d164f7328d39370c70ec62207db6b75e2ac1f8e082fee4ab9704`.
- Predecessor failure index:
  `alpha-correctness-failure-index:4dad7822c0c9371a393b02c29422a69d86808cb7cf046642c12173f8c17c4877`.
- Raw owner:
  `historical-data-owner-c744a6181b03ab8215ddb4ba@sha256:c744a6181b03ab8215ddb4ba8112ca117bc109057b52cc25e05e00a195d48092`.
- Normalized owner:
  `historical-data-owner-6dcb5f3850c7909b8c15428d@sha256:6dcb5f3850c7909b8c15428d0e0a19a2e4f97d2695e3902e7d95bd0d6d1ef23c`.
- Calendar:
  `trading-calendar-c5b2e78e0cf5c9a405bc307a@sha256:c5b2e78e0cf5c9a405bc307a889e57bdf526e565054d214b40ffec220673c862`.
- Historical run:
  `historical-research-run-acaa77a9adfe7a07b5ed181d@sha256:acaa77a9adfe7a07b5ed181df59752a0b326a9acad5dce5bbcc189ad8baec5eb`.
- Independent recovery run (completed materialization; its separate
  nonterminal replay is excluded from Proof below):
  `historical-research-run-0f11ce5b866f42f906f5915d@sha256:0f11ce5b866f42f906f5915dc7cb02b76955f72f636271f960855c667da9f365`.
- Final correctness Evidence:
  `historical-evidence-fe2b1060e72d59e04bf27295@sha256:fe2b1060e72d59e04bf2729599cad2537301458928c1d3d42cec33e9b1effb71`.
- Final proof:
  `alpha-correctness-proof:8cedafbaecb12c1137dc6c01f84d731445216370ed47d310d6b80a08056d5f55`.

The run covers the unchanged 126 Discovery Decision sessions from 2025-01-02
through 2025-07-11 and adjacent Target sessions only. It completed at journal
version 1513 with 126/126 complete sessions and 756 distinct stage receipts.
The new Experiment owns one final `ALPHA_CORRECTNESS` row plus the five
existing Historical Evidence companion kinds; it owns no `EXTERNAL_VALIDATION`
Evidence. The exact terminal matrix is:

| Evidence kind | Evidence owner | Evidence hash | Classification |
|---|---|---|---|
| `ALPHA_CORRECTNESS` | `historical-evidence-fe2b1060e72d59e04bf27295` | `sha256:fe2b1060e72d59e04bf2729599cad2537301458928c1d3d42cec33e9b1effb71` | `INCONCLUSIVE` |
| `ALPHA_ABLATION` | `historical-evidence-17a735f228d95aa196d24499` | `sha256:17a735f228d95aa196d2449940a2cfb8d6681a4d785ad8cc732dd061a04eefa3` | `INCONCLUSIVE` |
| `CORPUS_SUMMARY` | `historical-evidence-6776c14867d1abd7b0b159ff` | `sha256:6776c14867d1abd7b0b159ff88cf39f9f8655eca21577f1e9b5ef9c2a3d69be9` | `INCONCLUSIVE` |
| `METHODOLOGY_ASSESSMENT` | `historical-evidence-8f95e6786a10adda68d5108d` | `sha256:8f95e6786a10adda68d5108d3691de09166531b8fd5a050386844ab596def93d` | `INCONCLUSIVE` |
| `STRATEGY_ECONOMICS` | `historical-evidence-5e406a867f3561f1185a2962` | `sha256:5e406a867f3561f1185a2962c43604c4732f934f79006c9371f5393d0a0ce44d` | `NOT_ESTIMABLE` |
| `PORTFOLIO_PERFORMANCE` | `historical-evidence-065a9a2e627159be0f53d974` | `sha256:065a9a2e627159be0f53d974dd961a41bf3676b3840dc8ef0d826d653cd8cc1a` | `NOT_ESTIMABLE` |

PostgreSQL counts remain zero in
`locked_oos_raw_evidence_unlock`, `locked_oos_target_observation_consumption`
and `locked_oos_evidence_consumption`.

## Architecture audit and convergence

The pre-change audit followed the executable CLI through the existing
Historical runner, Phase-II operator/service, Decision materializer,
PostgreSQL component owners, correctness checker and Evidence repository. It
found four real correctness gaps: Decision/path/derived Target state was
collapsed in v2; the eight failed rows existed only as aggregate Evidence;
Feature value checking omitted an independently reconstructed rank; and the
inference implementation sampled around the observed estimate instead of the
null. The historical report also contained an abbreviated Raw-owner locator;
the database-reloaded full identity above is authoritative.

The repair converges the writer and checker on shared pure Target semantic and
observation-window kernels while preserving independently selected inputs. It
uses the existing Historical runner, repositories and Evidence authority; no
parallel runner, backtest, Feature/Target engine, workflow or qualification
plane was added. The already-retired duplicate backtesting/runtime surfaces
remain deleted. Target v1/v2 readers were not removed because immutable owner
reload and replay are current consumers; they remain compatibility-only rather
than a competing write path. No other dead or consumer-free execution surface
was found whose deletion was safe in this bounded Work Package.

## Physical and independent reproduction

The unavailable original historical physical package was not relabeled as
reproduced. This Work Package uses the separately identified
`REACQUIRED_EQUIVALENT_SOURCE`; it does not invent historical `available_at`
or upgrade BaoStock beyond `PIT_INCOMPLETE`.

The Raw owner records Provider
`BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS`, retrieval `2026-08-25T12:09:04+08:00`,
market range 2025-01-01 through 2026-08-24, exact request/row references inside
the verified physical partitions, and `RETROSPECTIVE_EVENT_TIME /
EXPLORATORY / PIT_INCOMPLETE`. The Normalized owner binds that Raw parent and
normalization `baostock-historical-normalization/v1`; retrieval time is never
backfilled as historical `available_at`.

- Normalized physical package hash:
  `sha256:813a0ab6d287bcfb586579c2481c43ddd8aed55d679f9b973e4905a50ef36fb6`.
- Raw physical package hash:
  `sha256:8223b44009dd8e03d1f946a12bb2c64b3b7a2ad4145466fac5bdb321687039bd`.
- 706 normalized checksums verify under checksum-set hash
  `sha256:687d6d8f660d4c09dab1c8a93fbf9390f059e504769b3967b9fb170c1ed057c3`.
- Independent normalization verification
  `independent-normalization-verification:9acb5811ce9f1d25af0ec42547f05f80f1f49759c9e9c99cfee02217b690312b`
  is `MATCHED`: 6,548,518 comparisons, zero discrepancies, equal canonical
  and independent value hash
  `sha256:07c404531a3eb23ccf8b7713ad9a5c7dec7b2f90081416e9929eb2e71b575e87`.
- Corpus replay verified exact Raw and Normalized owners and physical hashes
  with `network_requests=0`; no replay substituted another Provider.

Therefore the old unavailable package remains
`PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`, while the reacquired-equivalent Raw
and Normalized evidence is physically verified and independently matched.

## Feature and Target reconstruction

Feature reconstruction reopened the physical owner and independently selected
Decision-time bars before computing source interval, cutoff, value, rank,
missingness and lineage:

| Result | Rows |
|---|---:|
| `CORRECTNESS_SUPPORTED` | 37,722 |
| `PARTIALLY_REPRODUCED` | 78 |
| Discrepancies | 0 |

Of the 78 partial rows, 22 have missing Decision-time source bars and 56 are
not estimable. No missing Feature was zero-filled or promoted into a usable
rank. Independent cross-sectional ranking performed 113,166 comparisons across
378 session/factor populations: all 113,166 were ranked and rank mismatches are
zero.

Target reconstruction matched all 37,800 persisted semantic results with zero
value, status, reason or source-lineage discrepancy. `CORRECTNESS_SUPPORTED`
here means that valid `COMPLETE`, `PARTIAL`, `UNAVAILABLE` and `FAILED` states
were independently reproduced; it does not mean every return is estimable.

| Semantic dimension | Exact state counts |
|---|---|
| Decision reference | 37,722 `COMPLETE`; 78 `UNAVAILABLE` |
| Outcome window | 37,722 `COMPLETE`; 78 `UNAVAILABLE` |
| Checkpoint observation | 37,722 `COMPLETE`; 78 `UNAVAILABLE` |
| Checkpoint return / MFE / MAE | 37,367 `COMPLETE`; 347 `FAILED`; 86 `UNAVAILABLE` |
| Barrier | 37,023 `COMPLETE`; 344 `PARTIAL`; 347 `FAILED`; 86 `UNAVAILABLE` |

The eight predecessor failures now retain the exact intended state:
Decision reference `UNAVAILABLE`, observed T+1 path `COMPLETE`, and
Decision-dependent metrics `UNAVAILABLE`. The predecessor Evidence and every
intermediate correction attempt remain immutable.

Four entry diagnostics keep Information Cutoff, Decision reference, executable
proxy and Target reference distinct. For the fixed diagnostic observation,
`DECISION_REFERENCE_ONLY` is explicitly non-executable (11.43 to 11.44,
gross 0.00087489). `NEXT_BAR_OPEN` is an executable proxy (11.44 to 11.44,
gross 0); `NEXT_OBSERVABLE_PRICE` and `SESSION_CLOSE` are executable proxies
(11.43 to 11.44, gross 0.00087489). Every executable proxy carries
`EXECUTION_PROXY_NOT_FILL_PROOF`; none is a broker Fill or Strategy claim.

One first correction attempt produced immutable Evidence
`historical-evidence-5846abec0edba5ee08ffb5bf` and correctly failed because
60 rows exposed a second defect: diagnostic selection could read a prior
session's intraday bar while the writer used Decision-session input. The fix at
`6a7b406` bounds diagnostics to the Decision session. A differential regression
test proves that a previous-session intraday bar cannot change Target reasons
or lineage.

A later immutable attempt
`historical-evidence-ae6cd0eb9c395b8cb9804429` reached zero value
discrepancies but is ineligible as final Evidence after review: independent
rank comparison was absent, executable v3 Entry proxies were skipped and
bootstrap p-values were computed from the observed rather than null-centered
sampling distribution. Revision `8cd7997` fixes those review gaps under a new
Experiment, run and Evidence identity; the final campaign above reproduced
every Target and all independently reconstructed ranks.

## Falsification, redundancy and dependence-aware statistics

Mean RankIC by negative control:

| Factor | Random rank | Factor lag | Symbol permutation | Target permutation | Target shift |
|---|---:|---:|---:|---:|---:|
| Intraday return to DecisionTime | 0.00515 | -0.01149 | 0.00534 | 0.00982 | 0.68877 |
| Price versus VWAP | 0.00515 | 0.00240 | -0.00094 | 0.00543 | 0.16761 |
| VWAP slope | 0.00515 | -0.00106 | -0.00169 | 0.00302 | 0.25613 |

The real frozen higher-is-better Factors do not outperform the target-shift
control. This negative control is retained as falsification evidence and is not
used to retune the Target or reverse a Factor.

Redundancy is `PARTIALLY_REDUNDANT`. Pairwise Pearson correlations are
0.7037, 0.7173 and 0.7921; rank correlations are 0.6497, 0.7097 and 0.8248.
The equal-weight composite RankIC is -0.06731. Incremental RankIC is -0.00381,
-0.00699 and +0.00648 for intraday return, price-versus-VWAP and VWAP slope;
residual RankIC is -0.03084, -0.05704 and +0.02271 respectively. The three
expressions are not three independent Alpha claims.

The frozen inference protocol uses 2,000 null-centered moving-block iterations,
block lengths 1/5/10, two-sided tests, 95% intervals, seed 20260813, the maximum
block-sensitivity p-value and Benjamini-Hochberg correction. Mean session
estimates are -0.06364, -0.07221 and -0.04870; every block-length interval
remains below zero and temporal stability is `STABLE`. Raw p-values are
0.00049975, 0.00049975 and 0.00349825; adjusted values are 0.00074963,
0.00074963 and 0.00349825. This supports a statistically adverse association,
not positive Alpha. Sampling intervals, hypothesis tests and economic magnitude
remain separate claims.

## Discovery economics and final gate

The unchanged challenger has 37,367 complete Target observations and 66
estimable sessions:

| Metric | Result |
|---|---:|
| Mean RankIC | -0.0911520 |
| ICIR | -0.4965584 |
| Positive IC ratio | 0.348485 |
| Raw p-value | 0.00005482 |
| BH-FDR | 0.00172687 |
| Top-5 gross return | -0.00089056 |
| Assumed cost | 0.00210033 |
| Top-5 net return | -0.00299088 |

The statistically clear sign is adverse to `HIGHER_IS_BETTER`, and the net
economic diagnostic is negative. It may motivate a separately frozen future
hypothesis, but not a direction flip under this Experiment.

```text
CORRECTNESS = INCONCLUSIVE / PARTIALLY_REPRODUCED
REACQUIRED_PHYSICAL_REPRODUCTION = MATCHED
ORIGINAL_PHYSICAL_REPRODUCTION = PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
FORMAL_PIT = PIT_INCOMPLETE
FORMAL_OOS = false
LOCKED_OOS_CONSUMED = false
EXTERNAL_VALIDATED = false
ALPHA_PROVEN = false
STRATEGY_ECONOMICS = NOT_ESTIMABLE
PRODUCTION_QUALIFIED = false
TEMPORAL_EXTERNAL_VALIDATION_ADMITTED = false
```

## Resume, replay and validation

The Historical run was interrupted at bounded checkpoints and resumed through
1/126, 11/126, 31/126, 61/126 and 91/126 sessions before completing 126/126.
A terminal resume was a no-op at the same version 1513. Historical replay
`historical-replay-018133d5ca19d31cbf253297@sha256:018133d5ca19d31cbf253297556b263f49a794d37ec1d53e27cd9afde242d972`
then recomputed all 126 sessions continuously from the same frozen inputs and
exited zero with `matched=true` and zero mismatches. The staged run's receipts
therefore equal the uninterrupted recomputation, and replay equals the original
authoritative result. Final correctness and companion Evidence typed reloads
verify all six content hashes, classifications and exact run, Experiment and
source projections.

A second, separate read-only replay invocation for recovery run
`historical-research-run-0f11ce5b866f42f906f5915d` was manually interrupted
at an operator checkpoint with exit 130 before it returned a terminal
`HistoricalReplayReport`. It therefore has no terminal report identity,
`matched` value or mismatch set and is expressly excluded from Proof and
Evidence. The invocation did not mutate the immutable run or Evidence owners.
The completed recovery run establishes staged resume-to-completion; only
`historical-replay-018133d5ca19d31cbf253297` establishes the authoritative
replay equality above.

Packaged migration head is 106, `alpha_correctness_failure_revision`. Fresh
001→106, 097→106 upgrade, 104→105→106, idempotency, concurrent migration,
append-only failure-index reload, Historical materialization and schema/runtime
tests pass against PostgreSQL 16.14. The local validation ledger at the
immutable code/Evidence revision is:

| Local command / scope | Local result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| docs inventory/links + docs pytest (7 tests) | PASS |
| Correctness/Target/Phase-II/CLI focused tests (62 tests) | PASS |
| PostgreSQL owner tests (6 tests) | PASS |
| fresh/upgrade/idempotency/concurrency migrations (5 tests) | PASS |
| `tests/architecture` + `tests/platform` (54 tests; platform 33) | PASS |
| full pytest (3,035 collected tests) | PASS |
| Ruff | PASS |
| mypy (423 source files) | PASS |
| wheel and sdist build | PASS |
| `git diff --check` | PASS |

GitHub CI is a separate evidence plane. At Delivery Closure it is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`: repository Actions permission
reports `enabled=false`, and merged PR #79 has no check runs. This is not a CI
PASS and does not upgrade the local or research Evidence level.

Validation retained two environment diagnoses rather than hiding them. One
invocation used the global pyenv interpreter and loaded the original worktree;
the exact nodes pass under the isolated worktree `.venv`. A later complete run
exhausted the host volume because the dedicated test database had grown to
2.7 GiB; only the named temporary test database and failed pytest temp tree
were removed, then the complete suite was rerun from a fresh database to PASS.
No physical package, PostgreSQL campaign owner or historical Evidence was
deleted or rewritten.

## Routing

Do not enter Temporal External Validation for this Experiment. Preserve the
adverse Discovery result, strong target-shift controls, partial Feature
coverage, redundancy and Formal-PIT limitation. The next research action, if
approved, is a new Alpha Discovery hypothesis with a new Experiment identity;
it must not consume the frozen External or Locked OOS Outcomes while being
designed.
