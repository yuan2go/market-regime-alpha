# Golden Loop V2 Research Correctness Report

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Evidence Date:** 2026-08-20
> **Starting main:** `6f6e4681e71af49172607a75a05a94358805f63b`
> **Executable revision:** `bcee87a7d79f1028667a5874b7273a10fdcaacfa`
> **Migration proof:** isolated Phase E3 PostgreSQL dump, 084 through 090
> **Qualification ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`, `NOT_ESTIMABLE` where applicable, `UNQUALIFIED`, `FORMAL_OOS=false`, `CALIBRATED=false`

## Outcome

WP-GOLDEN-LOOP-01 is complete for retrospective research-correctness
engineering and Canonical Evidence closure. It does not prove Alpha or Strategy
economics.

The final scorer uses exact rational arithmetic for arithmetic midranks and
composite Factor scores until one order-preserving Decimal projection. Entity
identity never participates in ranking. Top-K boundary handling is the separate
`FRACTIONAL_BOUNDARY_WEIGHT_V1` research policy; it does not replace the
canonical Cross-Strategy Portfolio.

The final 126-session campaign is negative. Price and Price+Volume have negative
RankIC, spread, Top-10 gross and net. Context layers add no boundary/economic
value in this corpus. Candidate selects no rows, so the canonical Strategy path
correctly emits `NO_ACTION` and downstream economics remain `NOT_ESTIMABLE`.

## Frozen identities

| Item | Exact identity |
|---|---|
| Run | `historical-research-run-12e8dd606b480380dc0df356` |
| Command | `sha256:12e8dd606b480380dc0df356ca5aa6c2fdc7b2abd6b215feca74195a50227029` |
| Experiment | `research-experiment-definition:277357216e427e687d05ddf1f0e15dfeb10e89a20ffb15224494de1e5c47c473` |
| Scoring contract | `WITHIN_SESSION_TIE_AWARE_EXACT_RATIONAL_FACTOR_PERCENTILE_MEAN_V2` |
| Scoring hash | `sha256:ae1a0ad8a5b9563746a4d35305d562b54d92b7b6752996cef39efd56a47200c5` |
| Boundary policy | `FRACTIONAL_BOUNDARY_WEIGHT_V1`, Top-10 |
| Dataset | existing Phase E3 normalized Dataset and Artifact Root |

The campaign keeps the existing Target, Decision Time, Horizon, Factors,
Candidate/Signal thresholds, Forecast floor, cost assumptions and canonical
Portfolio policy. Only research-correctness identity, scoring, boundary
diagnostics and Canonical Evidence wiring change.

## Runtime and owner proof

The original Phase E3 schema was restored into an isolated database. Migration
verification reports PostgreSQL 16.14, 90 checksummed migrations, migration head
090 and 270 tables. The bounded campaign stopped after 15 sessions/90 receipts,
then resumed the same run identity to terminal state:

| Measurement | Result |
|---|---:|
| Decision sessions | 126/126 complete |
| Stage receipts | 756 |
| Session components | 1,764 |
| `RESEARCH_EVALUATION` owners | 126 |
| Canonical Cycle ID/hash joins | 126/126 |
| Canonical Portfolio ID/hash joins | 126/126 |
| Attribution reference/owner joins | 252/252 |
| Portfolio status | 126 `NO_ACTION` |
| Portfolio lines | 0 |

Every Evaluation also binds its Historical Outcome, cost policy, Experiment and
scoring owner. Historical execution is explicitly Shadow/Simulation and creates
neither an observed Fill nor physical Position authority.

Replay recomputed all 126 sessions from frozen inputs and returned
`matched=true` with zero mismatches. The immutable report is
`historical-replay-784d5601fbc1f0a1331afadc` /
`sha256:784d5601fbc1f0a1331afadc8a2004fcdfa73af32c81852e8e4c0bcb2da78337`.

## Ranking correctness findings

Metamorphic tests cover input permutation, symbol renaming, equal values,
constant factors, positive affine transforms, tie-group expansion, Factor-order
permutation, explicit missingness and fractional boundary exposure.

The first V2 campaign exposed a second defect after removing V1's identity
tie-break: recurring Decimal percentiles were rounded before composition. On
four dates this manufactured 13 bottom-boundary winners/losers across the
Price+Volume and Price+Volume+Regime variants. Exact-rational V2 assigns the
affected tie groups equal fractional weights.

Across the final real campaign, adding Regime, ETF, Theme, Capital, Dynamic
Pool, Candidate, Signal or Forecast changes zero Top/Bottom boundary weights.
Regime and Theme are neutral in this corpus. Dynamic Pool is non-constant in
only 3/126 sessions and slightly changes full-cross-section RankIC, but it does
not change Top-10 exposure or economics. Wholly unobserved layers are
`NOT_ESTIMABLE`, never zero-value claims.

## Coverage and missingness

| Measurement | Result |
|---|---:|
| Panel rows | 37,800 |
| Estimable T+1 targets | 37,375 |
| Missing/excluded targets | 425 |
| `COMPLETE` / `PARTIAL` | 37,159 / 216 |
| `CORPORATE_ACTION_EXCLUDED` / `UNAVAILABLE` | 347 / 78 |
| Candidate selected | 0/37,800 |
| Signal emitted | 0/37,800 |
| Forecast emitted | 0/37,800 |

All Candidates are rejected under the unchanged gates: Capital 15,595, Regime
14,978, Theme 7,199, Dynamic Pool 22 and Liquidity 6. Signal diagnostic is
`NOT_EMITTED_NOT_SELECTED` for all rows; Forecast diagnostic is
`NOT_EMITTED_NO_SIGNAL` for all rows.

Price is observed on 37,359 target rows and Volume on 37,319. ETF, Capital,
Candidate, Signal and Forecast have no observations. Market Regime is constant
in 76 sessions and unobserved in 50; Theme is constant in 125 and unobserved in
one; Dynamic Pool is constant in 123 and available in three.

## Transparent V2 results

| Variant | RankIC | Spread | Top-10 gross | Cost | Net | Turnover | Drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| Price | -0.061618 | -0.002222 | -0.000839 | 0.002100 | -0.002939 | 0.5528 | -0.420412 |
| Price + Volume | -0.059226 | -0.001937 | -0.000798 | 0.002100 | -0.002899 | 0.7684 | -0.457415 |
| Full frozen chain | -0.059283 | -0.001937 | -0.000798 | 0.002100 | -0.002899 | 0.7684 | -0.457415 |

Mean MFE is 0.009648 and mean MAE -0.008758. Volume changes Top-10 gross by
only +0.000041 and does not create positive information or economics. Regime,
Theme and Dynamic Pool have exactly zero Top-10 gross increment. ETF, Capital,
Candidate, Signal and Forecast incremental lifts are `NOT_ESTIMABLE`.

The current V2 owner reports only the frozen Top-10 diagnostic. Quantile
monotonicity, Top-1/3/5 sensitivity, capacity and empirical cost calibration
remain real gaps for WP-ALPHA-RESEARCH-01; they are not inferred here.

## Immutable correction lineage

V1 Evidence and the first V2 Evidence remain queryable under their original IDs
and hashes. The final Methodology Assessment binds 15 exact superseded
references, records `prior_evidence_mutated=false`, and names both defects:

- `TIE_SPLIT_BY_OBSERVATION_ID_V1`;
- `FINITE_DECIMAL_INTERMEDIATE_TIE_DRIFT_V2`.

The Phase E2 positive ranking/Portfolio interpretation is therefore
methodology-invalidated. This campaign does not fabricate a corrected Phase E2
estimate. The exact-rational Phase E3 rerun preserves the important negative
result: absolute ranking and Top-10 research economics remain negative. The old
Phase E3 six-checkpoint pseudo-portfolio output remains historical diagnostic
evidence, but it is no longer admissible as Canonical Strategy/Portfolio
economics; those are `NOT_ESTIMABLE` in V2 because the real canonical Portfolio
has no lines.

## Durable V2 Evidence

| Evidence | Classification | Exact owner |
|---|---|---|
| Corpus Summary | `INCONCLUSIVE` | `historical-evidence-41300ec27ffe096771ab357d` / `sha256:41300ec27ffe096771ab357d748881bb289795c6a4c74bbbb341cb6c1cb08ff3` |
| Alpha Ablation | `NEGATIVE` | `historical-evidence-748d4445d6a3ef7fb8cd3484` / `sha256:748d4445d6a3ef7fb8cd348408d9a61393e869c3aca0078621dba3d8897deeb4` |
| Strategy Economics | `NOT_ESTIMABLE` | `historical-evidence-509d1c89923a35fab4ba6171` / `sha256:509d1c89923a35fab4ba6171a0e438daeb7e819d467264d2c3eb7e0fd99566f0` |
| Portfolio Performance | `NOT_ESTIMABLE` | `historical-evidence-c04e680b924c9f2e26af4156` / `sha256:c04e680b924c9f2e26af4156cc909b5d44b064b2ae058af161b991e02d7cf05b` |
| Methodology Assessment | `INCONCLUSIVE` / methodology-invalidated lineage | `historical-evidence-a913adc7963a01e48a7e590b` / `sha256:a913adc7963a01e48a7e590ba458f83f6b163434c9c1a3f78b03d76f7c160e12` |

## Evidence ceiling and next route

This is `CODE_IMPLEMENTED`, `CANONICAL_WIRED`, `TEST_EXECUTED` and historical
`RUNTIME_PROVEN` at the declared SHA. It remains `EXPLORATORY`,
`PIT_INCOMPLETE`, `UNQUALIFIED`, not Formal OOS, not calibrated, not
Research-qualified and not Production-qualified.

Prospective proof is `BLOCKED_BY_EVIDENCE`: the isolated historical campaign
contains no live-origin future market window and Replay/Fixture/Backfill cannot
start that clock. The next highest-information Work Package is
WP-ALPHA-RESEARCH-01. Strategy/Cost/Portfolio optimization remains downstream
of a Factor/Gate/Candidate baseline that currently has negative information
and economics.
