# WP-3 Candidate Directional Accuracy Diagnostics Design

> **Date:** 2026-07-16
> **Status:** APPROVED DESIGN
> **Authority:** Bounded WP-3 engineering design under `AGENTS.md`; the Constitution and current
> R5 research authorities remain higher authority

## 1. Purpose

WP-3 already provides source-aware Candidate dataset construction, fixed B0/B1 ranking runs and
immutable evidence artifacts. The next bounded increment is to make Candidate ranking quality easier
to interpret without calling a Candidate rank an Entry or Exit decision.

This design adds a target-aware directional diagnostic for the existing Next-Session Close Return
Target. It answers:

```text
Does a declared Candidate ranking place more positive next-session returns in its fixed Top 5
than occur in the same date's Target-observed Candidate Population?
```

It does not answer:

```text
Should a position be entered now?
Should an existing position be exited now?
Would an order have filled?
```

Those questions remain owned by Entry, Position Lifecycle, Exit, Portfolio and Execution contracts.

## 2. Scope and Non-Goals

### In scope

- a versioned positive-return diagnostic specification;
- per-Decision-Time Top-5 and baseline outcome counts and rates;
- chronological panel aggregation with micro and macro metrics;
- explicit applicability status for each Target family;
- integration with the existing fixed B0/B1 runner and WP-3 evidence artifact;
- focused contract and integration verification;
- current-status documentation.

### Non-goals

- changing B0 or B1 features, weights, missing policy, scores or ranking order;
- adding Entry `UP_FIRST / DOWN_FIRST / TIMEOUT` Target contracts;
- adding Position State or Exit continuation Target contracts;
- calling a positive-return diagnostic a probability, buy signal, sell signal or trading win rate;
- training B2 or a nonlinear model;
- adding portfolio construction, broker connectivity or trading execution;
- upgrading Tencent evidence above `EXPLORATORY`;
- claiming a real Xuntou run without a real identified Xuntou input.

## 3. Approaches Considered

### 3.1 Add directional fields to the generic Candidate evaluator

This is mechanically small, but it would imply that one directional rule applies uniformly to Close
Return, MFE and MAE. Their Target semantics differ, so the generic contract would become shallower
and easier to misuse.

### 3.2 Add a target-aware diagnostic layer — selected

A separate Candidate-owned module consumes the same dataset and ranking evidence as the generic
evaluator. The caller must supply an explicit diagnostic specification. Only the approved
Next-Session Close Return Target is applicable in this increment.

This preserves the generic continuous-target evaluation, keeps Target semantics explicit and gives
later Entry work a clean boundary rather than retroactively redefining Candidate metrics.

### 3.3 Move directly to Entry competing-event Targets

This would address the practical buy-point problem more directly, but it would skip the bounded WP-3
evidence increment and mix WP-3 with WP-4. It also would not make an Exit model valid because Exit
requires canonical Position State and continuation targets.

## 4. Architecture

The new diagnostic remains in the Candidate research boundary:

```text
Provider evidence
        ↓
Candidate research datasets
        ↓
B0 / B1 rankings
        ├── Existing continuous-Target evaluation
        └── Target-aware directional accuracy diagnostic
                    ↓
             Existing WP-3 evaluation artifact
```

The intended module is:

```text
src/market_regime_alpha/candidates/directional_accuracy.py
```

It owns only:

- the versioned diagnostic specification;
- directional outcome classification;
- slice diagnostics;
- chronological panel aggregation;
- validation of dataset, ranking and Target alignment.

Provider routing, provider normalization and Candidate scoring do not depend on this module.

## 5. Diagnostic Specification

The first and only approved specification is:

```text
Spec ID: R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1
Applicable Target: Next-Session Close Return
Positive: target value > 0
Negative: target value < 0
Neutral: target value == 0
Top K: 5
```

The threshold is the mathematical sign boundary for an already approved return Target. It is not a
tuned profitability threshold. Transaction costs are not silently embedded. A later cost-aware Entry
or Portfolio experiment must use a separately identified specification.

The spec identity, rule and `top_k` are serialized into evidence output. A result-affecting change
requires a new spec identity.

## 6. Slice Semantics

For one Decision Time, the diagnostic records two baselines and one selected group:

1. **Candidate Population baseline:** all dataset rows whose Target status is `AVAILABLE`, including
   rows rejected by the ranking model because of missing Feature evidence.
2. **Ranked baseline:** all ranked predictions whose Target status is `AVAILABLE`.
3. **Top K:** the first five ranked predictions, retaining only those whose Target is `AVAILABLE` for
   metric denominators.

The Top 5 membership is fixed before looking at Target availability. If a Top-5 Target is unavailable,
the diagnostic records a smaller observed Top-K denominator. It must not backfill from rank 6 or
later, because that would allow future Target availability to alter the selected group.

Each group records observed, positive, negative and neutral counts. Each rate uses its group's
observed count. When the observed count is zero, the rate is `None`, not zero.

The slice also records:

- Target coverage over the full Candidate Population;
- Top-K observed coverage over the requested K;
- Top-K positive rate minus Candidate Population positive rate;
- Candidate Population negative rate minus Top-K negative rate.

The two differences are descriptive absolute percentage-point changes. They are not probabilities of
success or causal treatment effects.

## 7. Panel Semantics

Panel diagnostics preserve the existing chronological slice order and expose all slice records.

The panel records:

- pooled counts and rates across slices (`micro`);
- equal-weight mean of defined slice rates (`macro`);
- number of slices with comparable Top-K and Candidate Population rates;
- fraction of comparable slices where Top-K positive rate is strictly above the Candidate Population
  positive rate;
- Candidate Population, ranking and Target coverage counts.

Macro metrics skip only slices where their required denominator is zero. Micro metrics use pooled
counts. Both forms are retained because a pooled rate can be dominated by dates with larger observed
populations, while a date-equal mean can overemphasize small dates.

The metric is descriptive chronological evidence. This increment does not introduce a train/test
split, confidence interval, significance test or formal OOS claim. Such claims require an identified
research charter and frozen sample roles.

## 8. Applicability and Failure Semantics

The fixed R5 runner evaluates all three existing Target families separately.

- Next-Session Close Return: `APPLICABLE`, with the identified diagnostic result.
- Next-Session MFE: `NOT_APPLICABLE`, with an explicit Target-semantics reason.
- Next-Session MAE: `NOT_APPLICABLE`, with an explicit Target-semantics reason.

The runner must not emit an ambiguous bare `null` for MFE or MAE.

Evaluation fails closed when:

- the dataset and ranking identities do not align;
- the ranking does not account for the exact Candidate Population;
- the specification Target does not match the dataset Target;
- the specification identity, threshold rule or Top K is invalid;
- panel rankings do not cover each dataset slice exactly once;
- a panel mixes model identities.

Unavailable Target observations remain unavailable. They are never converted to neutral or zero.

## 9. WP-3 Integration and Identity

The fixed B0/B1 runner attaches an optional directional result to each named evaluation. Serialization
uses one explicit object:

```text
directional_accuracy:
  status: APPLICABLE | NOT_APPLICABLE
  spec_id: <identified value when applicable>
  reason: <explicit reason when not applicable>
  metrics: <identified diagnostic record when applicable>
```

The existing `b0_b1_evaluation.json` remains the owner of Candidate evaluation evidence. No parallel
result ontology or extra success-artifact file is added.

The WP-3 manifest records the directional evaluation protocol identity when applicable. The run's
existing canonical JSON hashing then makes any serialized metric change content-visible. Existing
continuous metrics remain unchanged and continue to be emitted beside the additive diagnostic.

Provider authority is preserved:

- Tencent-backed runs remain `EXPLORATORY`;
- Xuntou-backed runs remain bounded by their actual input and `REHEARSAL` semantics;
- no provider fallback is triggered by a weak or empty diagnostic result;
- no diagnostic result upgrades data eligibility.

## 10. Public API

Intended public Candidate APIs are limited to:

- the diagnostic specification type and fixed V1 specification;
- slice and panel diagnostic result types;
- slice and panel evaluation functions;
- the applicability status carried by named R5 evaluation records, if consumers need to inspect it.

Outcome-counting helpers, ratio helpers and serialization helpers remain private.

## 11. Verification

Focused tests will cover:

- positive, negative and exactly neutral classification;
- unavailable Target exclusion without Top-K backfill;
- Candidate Population and ranked-baseline differences;
- zero-denominator `None` behavior;
- micro and macro aggregation;
- strict chronological slice preservation;
- fraction of dates where Top K improves on the Candidate baseline;
- dataset, Target, model and population mismatch rejection;
- explicit `APPLICABLE` and `NOT_APPLICABLE` serialization;
- B0/B1 ranking semantics remaining unchanged;
- WP-3 artifact JSON and content hashing remaining deterministic.

After focused tests, the affected Candidate and WP-3 checks will run. Scoped Ruff and mypy checks
will cover changed source and test files. Full-repository checks may be run, but any existing unrelated
failures must be reported without being attributed to this increment.

## 12. Documentation and Commit Boundaries

Documentation updates will distinguish:

```text
WP-3 Candidate directional diagnostic    IMPLEMENTED / VERIFIED
Candidate Entry timing accuracy           NOT YET AVAILABLE
Exit timing accuracy                      NOT YET AVAILABLE
Trading execution                         OUT OF SCOPE
```

The intended commit sequence is:

1. `docs: design WP-3 Candidate directional diagnostics`
2. `feat: add WP-3 Candidate directional diagnostics`
3. `feat: integrate directional diagnostics into WP-3 artifacts`
4. `docs: record WP-3 directional diagnostic status`

Commit boundaries may be combined only when a code and integration change cannot be reviewed
truthfully in isolation. No unrelated technical debt is included.

## 13. Completion Criteria

This increment is complete when:

- the V1 diagnostic has a stable identity and exact sign semantics;
- every B0/B1 Close Return evaluation carries applicable directional evidence;
- MFE and MAE explicitly report non-applicability;
- all denominators, coverage and missing Target behavior are visible;
- WP-3 artifacts remain deterministic and non-overwriting;
- provider authority and data eligibility do not inflate;
- no Entry, Exit, Portfolio or Execution action is introduced;
- current-status documentation reports exactly what is and is not validated.

The next recommended package remains WP-4: implement identified Entry competing-event Target
contracts and materializers. Exit work remains sequenced after canonical Position State.
