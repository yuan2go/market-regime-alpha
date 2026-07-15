# R5 Provider-Rehearsal Trading Eligibility Policy v2

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** IMPLEMENTED CONTRACT — code and tests committed; provider-backed evidence materialization remains pending
> **Purpose:** Restore the original first-rehearsal Candidate-pool coverage for listing age, liquidity and Decision-Time buyability without conflating Candidate Eligibility with Execution Feasibility
> **Current audit:** `docs/architecture/Original-Intent-to-R5-Eligibility-Readiness-Audit.md`

---

## 1. Why v2 Exists

The original project conversation defined the first Candidate / overnight-opportunity MVP stock pool with constraints including:

```text
non-ST
non-suspended
listed for more than 60 days
liquidity threshold
exclude instruments that cannot be bought because of price-limit state
complete PIT data
```

Eligibility v1 correctly implemented:

```text
ST exclusion
suspension exclusion
exact-Decision-Time evidence
explicit UNKNOWN semantics
Policy / Materializer provenance
```

but did not yet represent:

```text
listing age
liquidity threshold
Decision-Time buyability
```

v2 adds those dimensions before provider-backed Candidate panels are treated as satisfying the original first-rehearsal population intent.

---

## 2. Compatibility Rule

v1 remains valid for:

```text
Legacy compatibility
minimum infrastructure tests
historical sidecars that do not contain v2 evidence
```

v2 does not retroactively reinterpret Legacy sidecars as if they contained provider-grade listing-age, liquidity or buyability evidence.

Therefore:

```text
Legacy/v1 observation
+
v2 policy
+
missing v2 evidence
        ↓
UNKNOWN
```

not:

```text
fallback to v1 ELIGIBLE
```

---

## 3. Provider-Rehearsal Policy Identity

Factory:

```text
r5_provider_rehearsal_trading_eligibility_policy_v2(...)
```

Human-readable Policy version:

```text
r5-provider-rehearsal-trading-eligibility@v2
```

The caller must explicitly provide:

```text
minimum_liquidity_value
liquidity_measure_id
```

The current default listing-age threshold is:

```text
minimum_listing_age_calendar_days = 60
```

This resolves the ambiguous original phrase `listed for more than 60 days` into an explicit v2 semantic:

```text
calendar days
```

A later research program may define a different Policy using trading-session age, but that would be a different result-affecting Policy identity.

---

## 4. v2 Evidence Contract

The canonical raw observation now supports optional provider-rehearsal evidence:

```text
listing_age_calendar_days
liquidity_value
liquidity_measure_id
decision_buyability
```

The fields remain optional at the raw-object level for v1 compatibility.

A v2 Policy makes them required according to its configuration.

---

## 5. Listing-Age Rule

Policy configuration:

```text
minimum_listing_age_calendar_days
```

### Below threshold

```text
listing_age_calendar_days < minimum
        ↓
INELIGIBLE
LISTING_AGE_BELOW_MINIMUM
```

### Missing evidence

```text
listing_age_calendar_days = missing
        ↓
UNKNOWN
LISTING_AGE_MISSING
```

The policy does not infer listing age from a symbol code, current snapshot, or present-day security master.

Provider-backed research must obtain an as-of-correct listing-date or identified listing-age value.

---

## 6. Liquidity Rule

v2 does not hard-code one global liquidity threshold.

The Policy requires an explicit pair:

```text
minimum_liquidity_value
liquidity_measure_id
```

Example research configuration:

```text
liquidity_measure_id = AVG_AMOUNT_20D_CNY
minimum_liquidity_value = <explicit run configuration>
```

The exact threshold is a research-policy parameter and enters Policy Identity.

### Below threshold

```text
liquidity_value < minimum_liquidity_value
and
liquidity_measure_id matches Policy measure
        ↓
INELIGIBLE
LIQUIDITY_BELOW_MINIMUM
```

### Missing value

```text
UNKNOWN
LIQUIDITY_VALUE_MISSING
```

### Missing measure identity

```text
UNKNOWN
LIQUIDITY_MEASURE_MISSING
```

### Measure mismatch

```text
Provider observation uses a different liquidity measure
        ↓
UNKNOWN
LIQUIDITY_MEASURE_MISMATCH
```

The policy must not compare values produced by different liquidity definitions as if they were the same feature.

---

## 7. Decision-Time Buyability Rule

New evidence enum:

```text
DecisionBuyabilityStatus
```

with:

```text
BUYABLE
NOT_BUYABLE
UNKNOWN
```

### `NOT_BUYABLE`

When the identified provider/adapter evidence contract explicitly classifies the instrument as not buyable under the scoped Decision-Time rule:

```text
INELIGIBLE
DECISION_NOT_BUYABLE
```

### `UNKNOWN`

```text
UNKNOWN
DECISION_BUYABILITY_UNKNOWN
```

### Missing evidence

```text
UNKNOWN
DECISION_BUYABILITY_MISSING
```

### `BUYABLE`

`BUYABLE` means only:

> the identified provider/adapter evidence did not classify the instrument as blocked by the scoped Candidate-population buyability rule.

It does not prove:

```text
guaranteed fill
queue priority
order-book depth
execution probability
final Execution Feasibility
```

---

## 8. Price-Limit Metadata Remains Separate

Existing fields:

```text
prev_close
limit_up_price
limit_down_price
limit_regime
```

remain useful raw evidence and completeness metadata.

They do not automatically derive:

```text
BUYABLE
NOT_BUYABLE
```

because a limit price alone does not describe:

```text
current market state
sealed limit-up state
available ask liquidity
queue depth
expected fillability
```

The provider-backed adapter must explicitly define how `DecisionBuyabilityStatus` is produced.

That adapter definition and evidence convention must be identified.

---

## 9. Decision Rules and Priority

The Policy evaluates hard exclusions first.

Possible hard exclusions include:

```text
SUSPENDED
ST_EXCLUDED
LISTING_AGE_BELOW_MINIMUM
LIQUIDITY_BELOW_MINIMUM
DECISION_NOT_BUYABLE
```

A known hard exclusion remains `INELIGIBLE` even if unrelated evidence is missing.

When no hard exclusion is known but required evidence is missing, late, unknown or incompatible:

```text
UNKNOWN
```

Only complete evidence with no hard exclusion becomes:

```text
ELIGIBLE
```

---

## 10. Policy Identity

v1 Policy Identity remains based on the original v1 fields.

When provider-rehearsal evidence requirements are enabled, Policy Identity uses the v2 schema and includes:

```text
policy_name
version
exclude_st
require_prev_close
require_limit_metadata
minimum_listing_age_calendar_days
minimum_liquidity_value
liquidity_measure_id
require_decision_buyability
```

Therefore changing:

```text
listing-age threshold
liquidity threshold
liquidity measure
buyability requirement
```

changes Policy Artifact Identity.

---

## 11. Original MVP Coverage After v2

The current R5 population path can now represent:

```text
A-share research Universe Membership
        ∩
non-ST
        ∩
non-suspended
        ∩
minimum listing age
        ∩
minimum PIT liquidity
        ∩
explicit Decision-Time buyability
        ∩
complete required PIT evidence
        =
Candidate Population
```

Actual provider-backed materialization is still pending.

The code contract being able to represent the policy does not prove that a chosen provider supplies all required evidence correctly.

---

## 12. Still Not Implemented by v2

v2 does not yet define:

```text
major next-session event-risk exclusion
final execution feasibility
order-book queue models
fill probability
lot-size feasibility
cash / shares availability
Portfolio approval
Entry timing
Position Lifecycle
Exit
```

Those require separate owners and evidence.

---

## 13. Provider-Backed Readiness Requirement

The next provider-backed or provider-export-backed REHEARSAL Market Artifact must be able to provide or justify enough evidence for:

```text
historical listing age
identified PIT liquidity measure
Decision-Time buyability status
ST status
suspension status
price-limit metadata
availability semantics
```

A provider that cannot support a required v2 field may still be useful for other research roles, but it cannot silently produce a complete v2 Candidate Population.

Missing required evidence becomes:

```text
UNKNOWN
```

---

## 14. Tests

Current v2 tests cover:

```text
complete v2 evidence → ELIGIBLE
listing age below minimum → INELIGIBLE
liquidity below threshold → INELIGIBLE
explicit NOT_BUYABLE → INELIGIBLE
missing listing age → UNKNOWN
missing liquidity → UNKNOWN
liquidity measure mismatch → UNKNOWN
missing buyability evidence → UNKNOWN
buyability UNKNOWN → UNKNOWN
v1 remains Legacy-compatible
v2 does not silently downgrade to v1
Policy Identity changes with threshold / measure
```

---

## 15. Current Authority

The current implementation proves only:

```text
The R5 eligibility contract can represent the original first-rehearsal Candidate-pool requirements
for listing age, liquidity and explicit Decision-Time buyability under a versioned Policy.
```

It does not prove:

```text
A provider supplies those fields correctly.
The liquidity threshold is optimal.
BUYABLE guarantees fill.
The Candidate Population produces Alpha.
```

---

## 16. Next Implementation Step

The next step is now:

```text
Provider-backed or Provider-export-backed REHEARSAL Market Artifact
```

The artifact must preserve:

```text
source identity
schema identity
retrieval / availability semantics
bar finality
price-adjustment basis
historical raw eligibility evidence
listing-age evidence
PIT liquidity evidence
Decision-Time buyability evidence
Decision-Time snapshots
next-session OHLC
```

Only then should the project build the first provider-backed v2 Candidate Population and target-specific Candidate panels.

---

## 17. Principle

> **Candidate eligibility must reproduce the declared research population, not merely filter whatever fields happen to exist. The v2 policy restores the original MVP requirements for listing age, liquidity and Decision-Time buyability while preserving the distinction between Candidate eligibility and final execution feasibility.**
