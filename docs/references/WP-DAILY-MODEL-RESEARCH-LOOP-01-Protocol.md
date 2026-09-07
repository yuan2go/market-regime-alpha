# WP-DAILY-MODEL-RESEARCH-LOOP-01 — Post-close prediction protocol

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Versioned exploratory research contract; no qualification or execution Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-08
> **Code Evidence:** existing Market, Dataset, Target/Outcome, ModelForecast, Evaluation and Runtime owners

## Frozen first implementation scope

Protocol code: daily_close_next_session_intraday_v1. Market: SSE/SZSE A-share
equities, the existing explicitly enumerated r2_xshg32 32-instrument roster.
Actual TradingSession identities define every offset; no weekday inference.
No new model family, parameter search, Context slices or trading suggestions.

Primary target: next actual trading session's RAW_UNADJUSTED close/open - 1,
DECIMAL RATIO. Two future DAILY Outcome checkpoints select OPEN then CLOSE
from the same exact session/bar revision. Both are post-publication labels.
The ordinary Decision reference remains the input session's close and is not
the denominator of this metric. Outcome owns the new OBSERVATION_RETURN kind.
Different session, price basis, revision, missing or invalid prices fail closed.
This is a same-session raw-price prediction target, not executable PnL, overnight
investment return, episode economics or an account. No corporate-action or
cross-basis reconstruction is supported.

Input FeatureDefinition: session_open_close_move_v1, raw daily close/open - 1,
12 decimal places, ROUND_HALF_EVEN, fixed local Decimal precision. Warm-up is
one complete actual trading session. No fitted scaler, imputer or selection:
preprocessing is explicitly IDENTITY, frozen with the model.
Historical sealed and actual-time readers use the same pure computation.
The historical reader keeps its dual-clock restriction; the actual-time reader
requires every referenced fact visible at input cutoff <= DecisionTime.

DataReady preserves sampled, expected-active-input and feature-ready rosters, source
Capture/Artifact/revision identities, event interval, first known/recorded times
and input cutoff. It never infers full batch readiness from a last row or login.
Suspended/excluded members, source gaps, revision conflicts and calendar gaps
retain typed disposition; yesterday's value is not a replacement. Canonical
Eligibility is separately assessed by Selection. The new minimal research
policy checks listing age >= 0 and the last completed session's ACTIVE status;
it is not trading eligibility and does not claim complete A-share tradability.
Publication must be recorded before the target session opens. Late publication
is an immutable abstention. The first target session after the input session is
explicit; a late input does not silently move the prediction to another target.

## Historical baseline and full denominators

Freeze the first canonical available sequence with 20 FIT sessions, one purge
session, one embargo session and 10 VALIDATION sessions, plus target coverage,
before Outcome access. Existing observed history remains exploratory; no
untouched-OOS or Alpha claim. Use the existing transparent rank-rule forecast, fixed at 0.02 × the
Candidate arithmetic-midrank score − 0.01, and deterministic ridge on the shared
raw daily feature with fixed alpha=1, seed=18. The rule is explicitly a
Candidate-derived baseline, never a model prediction. No tuning.
Both arms use the same feature/Target/input scope; prediction population is all
eligible feature-ready members, independently of strategy Signal/Risk state.

Report sampled, eligible, feature-ready, predicted, mature and estimable Outcome
populations separately. Historical population coverage is a read-only count
projection of these reconciled rosters; do not set the eligible prediction
metric denominator to the sampled Universe size. Daily canonical prediction
Evaluation freezes the exact published commitment count before Outcome access. Common-sample error/rank comparisons show both arm
coverage losses and full member reasons. RankIC is per actual trading day before
time aggregation; zero variance and insufficient samples have typed reasons.
Preserve coefficient/prediction/rank vectors to test monotone equivalence.
No NAV, Sharpe, execution-profit or V2 economics claim is part of this protocol.

## Independent model use and lifecycle

Training uses completed FIT Evaluation via the existing Model owner and freezes
sample/Feature/Target order, IDENTITY preprocessing, algorithm, alpha, seed,
dependency fingerprint and fitted Artifact. Every daily use explicitly binds
one completed ModelVersion registered before DecisionTime, with mature labels
known by training cutoff. Experimental purpose is not Model qualification.
An explicit purpose-limited use binding defines activation/expiry/revocation.
No latest-model lookup or fallback. Old retrospective bindings remain unchanged.

Selection/Dataset/Candidate precede the daily Decision; future Outcome is never
an input to publication. ModelForecast retains a complete candidate prediction
roster even when strategy Signal is absent. Research publication includes
sampled exclusions and missing members, exact Feature/Target/Model/Dataset/
Decision and publication identities. Top-N is presentation only, not a trade.
Report bytes are immutable; revisions require a new identity.

Existing Runtime discovers pending target sessions, captures after maturity,
settles through canonical Outcome and completes existing Evaluation. Before
maturity remains PENDING; missing source is an explicit negative state.
Feedback influences only a later protocol/model version.
A daily input/Outcome collection phase has at most 16 observations, separated
by at least 30 minutes. Known empty responses may produce a new observation
identity; failed or unknown effects require recovery. Outcome missingness is
terminally evaluated after an eight-hour post-close observation allowance.
Input publication never moves beyond the next session opening.
Collection, snapshot, planned training, prediction and evaluation execute
serially under the same exact-database admission reservation. No second writer,
scheduler, fallback database or copied Authority rows.
Registered schema expansion, if needed, is proved in a disposable DB and
backed up before authorized original-scope upgrade. v6 bytes remain immutable.

## Acceptance seams

Use independent hand expectations at Target/Outcome and Feature/DataReady
interfaces; real PostgreSQL tests for Dataset/Decision/ModelForecast/Evaluation,
publication/replay, stale fences and unknown commit; bounded shared Runtime
handoff/deployment tests. Execute the new real sealed-input baseline, a current
future publication or exact abstention, and a separately labelled mature-history
publication-to-Outcome evaluation proof. Historical replay is not live prediction.
The existing Roadmap owns execution sequencing; this document is the research
protocol, not a parallel plan or qualification gate.
