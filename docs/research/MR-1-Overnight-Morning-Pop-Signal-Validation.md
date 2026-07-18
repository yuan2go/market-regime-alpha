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

The predeclared descriptive assessment is:

- `PROMISING_EXPLORATORY`: BASE net cumulative return exceeds the Candidate baseline; all three
  20-date segments are positive; maximum drawdown is no worse than -15%; LOW, BASE and HIGH all
  have positive net cumulative returns; and gains are not more than 50% concentrated in one day.
- `FAILED_EXPLORATORY`: BASE or HIGH net cumulative return is non-positive, or maximum drawdown
  is worse than -25%.
- `INCONCLUSIVE`: neither condition applies.

This label is a predeclared research disposition, not production approval or Alpha evidence.

## Current run

The first MR-1 cached-Dataset run used Dataset
`prr-dataset-fa40337727427b2f1ff63548` and generated
`data/processed/mr1_morning_pop_runs/mr1-38b4458700aa653fe7a0/` locally.

It evaluated 9 fixed models × 4 exit endpoints × 3 cost scenarios over 60 Decision Dates.
All 36 BASE model/exit combinations received `FAILED_EXPLORATORY` under the above rule.  This is
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
