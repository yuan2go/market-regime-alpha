# MR-1 Overnight Morning-Pop Signal Validation

## Scope

MR-1 is an EXPLORATORY validation of the existing fixed Candidate B0/B1 ladder on the
question: after a 14:55 research-mark entry, does the next-session early-morning path support
an earlier exit than the existing next-close comparator?

It does not implement an Entry Gate, an Entry Model, a Position State, an Exit Model, model
selection, or execution.

## Evidence and time convention

The input is an immutable PRR-MVP-1 normalized 5-minute Dataset.  Features and Candidate ranks
remain the existing 14:55 materializations.  MR-1 only reads next-session bars after that
decision time to form evaluation Targets.

| Target | Mark convention | Missing behaviour |
| --- | --- | --- |
| `NEXT_SESSION_0935_RETURN` | exact next-session 09:35 five-minute close | unavailable; no forward fill |
| `NEXT_SESSION_1000_RETURN` | exact next-session 10:00 five-minute close | unavailable; no forward fill |
| `NEXT_SESSION_1030_RETURN` | exact next-session 10:30 five-minute close | unavailable; no forward fill |
| `NEXT_SESSION_CLOSE_RETURN` | prepared complete next-session close | unavailable if the prepared session is absent |
| `NEXT_SESSION_1030_MFE` / `MAE` | extrema from 09:35 through exact 10:30 | unavailable without the exact 10:30 endpoint |

`14:55 → 09:35/10:00/10:30` sleeves are closed before the following 14:55 Decision Time, so
the next daily sleeve may be entered.  The retained `CLOSE` comparator keeps the prior
cash-lock treatment for overlapping 14:55-to-next-close sleeves.

All fills are explicitly `SIMULATED_REFERENCE_FILL`.  A reference mark is not evidence that a
historical order could have filled at that price.

## Fixed evaluation

All four B0 controls and B1-A through B1-E are replayed independently at every exit endpoint
under fixed LOW, BASE, and HIGH cost assumptions.  There is no automatic winner selection.

The v4 comparator family separates raw selection lift from trade-count, population, and
minimum-commission effects. Each comparator is bound to the exact model/date population where
`eligible_for_ranking` is true and rank is present:

- `ALL_CANDIDATE_GROSS_V1` is the equal-weight gross comparator within that model population.
- `MATCHED_K_HASH_GROSS_V1` and `MATCHED_K_HASH_NET_V1` use the same Top-5 capital sleeves,
  missing-weight rule, exit endpoint, cost mechanics, and CLOSE cash-lock state as the model.
  Their rank-blind symbols are selected by a stable SHA-256 algorithm with frozen seed `17`.
  The actual slots are retained in `matched_k_selections.parquet`; population and selection
  identities can be reconstructed from immutable Candidate rankings without rerunning a model.
- `ALL_CANDIDATE_NET_DIAGNOSTIC_V1` remains available only as a non-tradable diagnostic because
  its trade count and minimum-commission structure differ from Top-5.

Every daily comparator row records observed, missing, and cash-locked weight. These weights sum
to one without reweighting observed Targets. The predeclared descriptive assessment is:

- `PROMISING_EXPLORATORY`: BASE net cumulative return exceeds the matched-K net comparator; all three
  20-date segments are positive; maximum drawdown is no worse than -15%; LOW, BASE and HIGH all
  have positive net cumulative returns; and gains are not more than 50% concentrated in one day.
- `FAILED_EXPLORATORY`: BASE or HIGH net cumulative return is non-positive, or maximum drawdown
  is worse than -25%.
- `INCONCLUSIVE`: neither condition applies.

This label is a predeclared research disposition, not production approval or Alpha evidence.

## Current run

The current MR-1 v4 cached-Dataset run used Dataset
`prr-dataset-fa40337727427b2f1ff63548` and generated
`data/processed/mr1_morning_pop_runs/mr1-c06821bf7db2dc787244/` locally. Its
`candidate_daily_baselines.parquet` contains 25,920 rows: 60 Decision Dates × nine fixed models ×
four exit times × three cost scenarios × four identified baselines. The 28,350 persisted
matched-K slot rows use seed `17`. All 3,240 model-specific CLOSE baseline rows for overlapping
Decision Dates are explicitly cash-locked, matching the model sleeve state.

This Dataset happened to have 20 eligible symbols for every model/date. The v4 contract does not
assume that equality: model/date populations are independently identified and the verified reader
fails closed if a baseline or selected symbol crosses its population boundary. The average
descriptive overlap between model Top-5 and matched-K Top-5 was about 21.60%; it is not a model
quality metric.

The earlier `mr1-4b6036dd44e5ca2ffab5` and `mr1-38b4458700aa653fe7a0` runs are retained as
historical evidence but are **SUPERSEDED** for comparator interpretation because they predate
model-specific population binding and auditable selection evidence.

It evaluated 9 fixed models × 4 exit endpoints × 3 cost scenarios over 60 Decision Dates.
All 36 BASE model/exit combinations received `FAILED_EXPLORATORY` under the v4 rule. This is
not Formal OOS evidence and does not establish a negative conclusion beyond the current
watchlist, cache, period, reference-mark convention, and fee assumptions.

## Limitations

- `CURRENT_WATCHLIST_BACKFILL_BIAS`
- `HISTORICAL_PIT_NOT_VERIFIED`
- `HISTORICAL_BUYABILITY_NOT_VERIFIED`
- `REFERENCE_MARK_NOT_FILL_PROOF`
- `NO_LEVEL2_OR_ORDER_BOOK`
- `FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION`
- `AUXILIARY_DATA_ONLY`
- `FORMAL_OOS_NOT_ESTABLISHED`

The appropriate follow-up after this failed exploratory validation is Target/Feature design
review, not Runtime expansion, Entry modelling, or model winner selection.
