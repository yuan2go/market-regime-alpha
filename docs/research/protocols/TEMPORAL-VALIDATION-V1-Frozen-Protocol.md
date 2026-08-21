# TEMPORAL_VALIDATION_V1 Frozen Protocol

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Subordinate frozen research protocol  
> **Repository Baseline:** `main@091324c7e28a2b6a3b89f894d18afc7380486d13`  
> **Frozen By:** explicit user decision on 2026-08-21  
> **Evidence Ceiling:** `EXTERNAL_VALIDATION`; `FORMAL_OOS=false`  
> **Last Updated:** 2026-08-21

This protocol freezes the first Temporal External Validation before Alpha
Correctness is known. It does not unlock outcome access, execute the campaign,
or create Alpha, Strategy, Formal OOS, prospective or Production authority.
The persisted `ResearchExperimentDefinition` remains the executable Experiment
owner.

Protocol execution state: `FROZEN_NOT_EXECUTED`.

## 1. Contamination gate

The baseline contamination audit is recorded in
[TEMPORAL_VALIDATION_V1 Contamination Audit](../../references/TEMPORAL-VALIDATION-V1-Contamination-Audit.md).
It found no real observation population from this window used for Factor
discovery/direction/filtering, Candidate/Top-K selection, threshold or cost
tuning, hyperparameter tuning, model selection or positive-result selection.

If later owner evidence contradicts that audit before the Experiment is
persisted, the contradiction fails the freeze closed. The original window must
be recorded as contaminated; it must not be silently replaced after inspecting
outcomes.

## 2. Calendar-owned temporal partition

The frozen inputs are:

```text
START_DECISION_SESSION = 2025-07-15
SESSION_COUNT = 126
TARGET = NEXT_VALID_TRADING_SESSION 10:30 Asia/Shanghai
```

The ending Decision session is deliberately not hard-coded. The exact window
must be constructed as follows:

```text
canonical A-share TradingCalendarArtifact owner
→ reload and hash-verify the exact calendar
→ require 2025-07-15 to be an explicit session
→ take that session and the next 125 explicit sessions
→ resolve one additional explicit session for the final T+1 Target
→ freeze all 126 Decision session identities, the final Target session,
  calendar reference and calendar hash in the Experiment identity
```

Weekdays, estimated holiday lists or an implementation-local end date are not
calendar authority. The calendar must cover all 126 Decision sessions plus the
last T+1 Target session. Insufficient coverage is `INCONCLUSIVE`/blocked input,
not permission to infer a date.

The temporal separation rationale is frozen:

- discovery last Decision session: `2025-07-11`;
- discovery last T+1 10:30 Target session: `2025-07-14`;
- first External Decision session: `2025-07-15`.

Therefore discovery Decision/Target population ends before the External
Decision population begins.

## 3. Frozen hypothesis and economics

Only `TEMPORAL_PARTITION` changes. These values remain identical to the frozen
discovery owner:

| Field | Frozen value |
|---|---|
| Universe | discovery frozen effective-dated CSI 300 universe |
| Provider | discovery BaoStock provider and request semantics |
| Factors | `intraday_return_to_decision_time`, `price_vs_vwap_return`, `vwap_slope` |
| Factor directions | discovery-frozen directions |
| Scoring | equal-weight rank percentile |
| Candidate scoring | discovery-frozen Candidate score |
| DecisionTime | `14:55 Asia/Shanghai` |
| Target | T+1 10:30 return |
| Top-K | discovery-frozen values |
| Cost policy | discovery-frozen policy |
| Economics policy | discovery-frozen policy |
| Entry semantics | discovery-frozen execution-entry semantics |
| Qualification thresholds | discovery-frozen thresholds |
| Bootstrap protocol | discovery-frozen moving-block protocol and sensitivities |
| Random seed | discovery-frozen seed |

The Experiment must reject any second changed dimension, Factor rescan,
direction flip, weight change, Top-K change, threshold change, cost change,
provider substitution or post-result window selection.

## 4. Outcome-access gate

The calendar window and Experiment identity are frozen now. External outcomes
remain inaccessible for research evaluation until a typed, owner-resolved
correctness campaign concludes `CORRECTNESS_SUPPORTED`.

```text
CORRECTNESS_SUPPORTED
→ execute TEMPORAL_VALIDATION_V1

CORRECTNESS_FAILED or INCONCLUSIVE
→ BLOCKED_BY_CORRECTNESS
→ do not read External outcomes for research judgment
→ do not create External Validation Evidence
```

An executed result may be only `SUPPORTED`, `NOT_SUPPORTED` or `INCONCLUSIVE`.
Free-data/PIT-incomplete evidence always retains `FORMAL_OOS=false`.
