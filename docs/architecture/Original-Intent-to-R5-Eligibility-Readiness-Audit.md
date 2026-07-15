# Original Intent to R5 Eligibility Readiness Audit

> **Status:** CURRENT audit before provider-backed Candidate panels
> **Scope:** Preserved original ChatGPT project conversation, Constitution `00–09`, current R5 Charter, current R5 status, versioned Trading Eligibility v1, and provider-backed rehearsal readiness
> **Authority:** Architecture and implementation interpretation. This document does not override the Constitution.

---

## 1. Audit Question

This audit asks:

> Does the current R5 Candidate Population implementation preserve the user's original intended first-rehearsal stock-pool constraints, or has the project treated a minimal ST/suspension policy as if full Candidate eligibility were already complete?

The preserved original conversation remains chronological evidence. Later explicit user corrections override earlier assistant formulations.

The later correction that removed mandatory next-morning Exit did not remove the earlier Candidate-pool requirements.

---

## 2. Original Candidate-Pool Intent

The preserved original conversation defined the first Candidate / overnight-opportunity MVP stock pool with constraints including:

```text
A-share universe
non-ST
non-suspended
listed for more than 60 days
liquidity threshold
exclude instruments that cannot be bought because of price-limit state
complete PIT data
```

A closely related formulation also included:

```text
average daily amount filtering
exclude unbuyable limit-up states
exclude major next-session risk where such evidence is available
```

These were Candidate-population requirements.

They were not removed when the user later corrected:

```text
T+1 morning mandatory exit
```

into:

```text
independent Position Lifecycle / Exit
```

Therefore the preserved direction is:

```text
Candidate opportunity research may use a next-session target family
while Candidate eligibility remains a separate PIT population contract
and Exit remains a separate future owner.
```

---

## 3. Current Direction-Level Assessment

### Candidate Discovery

**ALIGNED**

The current R5 system remains an independent cross-sectional Candidate Discovery program.

### Fixed Exit

**ALIGNED**

The current R5 Charter still states:

```text
Candidate Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

### ETF / Theme / Market Context

**ALIGNED**

They remain upstream and available for later controlled incremental comparison.

### Legacy authority

**ALIGNED**

Legacy remains a compatibility and characterization source, not the new Candidate authority.

### Candidate eligibility coverage

**PARTIAL — MATERIAL SCOPE GAP FOUND**

The current v1 policy is intentionally smaller than the preserved first-rehearsal stock-pool intent.

---

## 4. What Eligibility v1 Correctly Implements

Current policy:

```text
r5-rehearsal-trading-eligibility@v1
```

Correctly provides:

- versioned Policy Identity;
- exact-Decision-Time materialization;
- explicit `ELIGIBLE / INELIGIBLE / UNKNOWN`;
- ST exclusion;
- suspension exclusion;
- raw evidence availability checks;
- fail-closed missing evidence;
- explicit Policy / Materializer / raw-evidence provenance;
- valid empty Eligibility Snapshot preservation;
- separation from final Execution Feasibility.

This is valuable and remains valid.

---

## 5. What Eligibility v1 Does Not Yet Implement

The current v1 policy does not yet implement the complete original first-rehearsal Candidate-pool requirements for:

```text
minimum listing age
minimum liquidity
explicit Decision-Time buyability / unbuyable price-limit state
```

It also does not yet implement event-risk exclusion.

The existing fields:

```text
prev_close
limit_up_price
limit_down_price
limit_regime
```

are currently raw-evidence completeness fields.

Their presence alone does not prove:

```text
BUYABLE
NOT_BUYABLE
actual fillability
queue depth
execution probability
```

That distinction is correct and must remain.

---

## 6. Why This Is a Scope Gap, Not a Direction Failure

The v1 policy was introduced as a minimal explicit policy over the raw fields already available in the Legacy rehearsal sidecar.

It was not intended to be a universal A-share tradability model.

The error would occur only if the next provider-backed Candidate panel were built under the assumption:

```text
v1 ST/suspension policy
=
complete original Candidate eligibility
```

That assumption is prohibited by this audit.

---

## 7. Required Provider-Rehearsal Eligibility v2

Before the first provider-backed Candidate panel is treated as satisfying the original MVP population intent, the project requires a versioned provider-rehearsal Eligibility Policy that can represent at least:

### 7.1 Listing age

Evidence:

```text
listing date
or
identified listed-age value at Decision Time
```

Policy:

```text
minimum listing-age threshold
```

The preserved original requirement was:

```text
listed for more than 60 days
```

The exact semantic unit must be explicit in the policy contract:

```text
calendar days
or
trading sessions
```

It must not remain an ambiguous `60d` string.

### 7.2 Liquidity

Evidence:

```text
identified PIT liquidity measure
```

Examples may include:

```text
rolling average amount
rolling median amount
other explicitly versioned liquidity measure
```

Policy:

```text
explicit minimum threshold
+
measure identity / convention
```

No universal threshold is invented by this audit.

The threshold must be explicit experiment / policy configuration.

### 7.3 Decision-Time buyability

The original requirement was to exclude instruments that are not actually buyable because of price-limit state.

The project must not implement this as:

```text
limit_up_price exists
→ buyable
```

or:

```text
last_price == limit_up_price
→ universally not executable
```

without the required evidence.

The provider-rehearsal contract therefore needs an explicit Decision-Time buyability evidence state such as:

```text
BUYABLE
NOT_BUYABLE
UNKNOWN
```

with identified source / adapter semantics.

`NOT_BUYABLE` may exclude a Candidate.

`UNKNOWN` must fail closed when the policy requires buyability evidence.

`BUYABLE` is still not final Execution Feasibility or guaranteed fill probability.

---

## 8. Ownership Boundary

The required ownership remains:

```text
Universe Membership
    owns research-population membership

Trading Eligibility
    owns point-in-time Candidate-population eligibility policy

Candidate Discovery
    owns Membership ∩ Eligibility

Execution
    later owns actual order feasibility and fill semantics
```

Therefore:

```text
minimum listing age
minimum liquidity
Decision-Time candidate buyability
```

may participate in a Candidate Eligibility Policy when explicitly defined for the research scope.

They must not be hidden simultaneously inside both Universe Membership and Trading Eligibility without lineage.

---

## 9. Documentation Residues Found

### 9.1 Previous R5 consistency audit is a historical snapshot

`Original-Intent-to-R5-Consistency-Audit.md` correctly identified the earlier Close Return-only gap.

That gap has since been corrected with identity-distinct:

```text
Close Return
MFE
MAE
```

The previous audit remains useful historical evidence but is not the current implementation status.

### 9.2 R5 Charter deliverable list is stale

The current Charter still lists historical Trading Calendar and PIT Universe loading as future deliverables even though those capabilities now exist.

This is a status residue, not a direction contradiction.

`R5-Current-Status.md` remains the current short-form implementation status until the Charter receives a later consolidation pass.

### 9.3 Detailed Eligibility policy document predates final provenance additions

The detailed Eligibility document correctly describes v1 behavior, but some earlier provenance wording predates the later addition of:

```text
materializer_version
raw_evidence_convention
```

The current short status is authoritative for active sequencing.

---

## 10. Current Direction-Level Conclusion

```text
Direction-Level Contradiction: NONE FOUND
```

```text
Eligibility v1 Infrastructure: VALID
```

```text
Original MVP Candidate Eligibility Coverage: PARTIAL
```

```text
Provider-Backed Candidate Panel Readiness:
BLOCKED UNTIL THE PROVIDER-REHEARSAL ELIGIBILITY CONTRACT CAN REPRESENT
LISTING AGE + LIQUIDITY + DECISION-TIME BUYABILITY
```

This does not require a complete future Execution engine before provider-backed research.

It requires the provider-backed rehearsal path to carry enough identified evidence to reproduce the original Candidate-pool scope honestly.

---

## 11. Updated Next Implementation Sequence

The next sequence is:

```text
Original-Intent Eligibility Readiness Audit
        ↓
Provider-Rehearsal Eligibility Policy v2 Contract
        ↓
Listing-Age Evidence
+
PIT Liquidity Evidence
+
Decision-Time Buyability Evidence
        ↓
Provider-Backed / Provider-Export-Backed REHEARSAL Market Artifact
        ↓
Exact Historical Candidate Populations
        ↓
Features
        ↓
Close Return / MFE / MAE
        ↓
Target-Specific Candidate Panels
        ↓
B0 vs B1
        ↓
Immutable R5 Run Artifact
```

The v1 Policy remains useful for Legacy compatibility and minimal infrastructure tests.

The v2 provider-rehearsal policy must not be retroactively applied to Legacy sidecars that do not contain the required evidence.

---

## 12. Binding Guardrails for the Next Stage

1. Do not call Eligibility v1 the complete original MVP stock-pool policy.
2. Keep v1 available for Legacy/rehearsal compatibility.
3. Make listing-age semantics explicit.
4. Make the liquidity measure and threshold explicit.
5. Do not infer Decision-Time buyability from limit-price metadata alone.
6. Treat missing required v2 evidence as `UNKNOWN`, not `ELIGIBLE`.
7. Keep `BUYABLE` distinct from guaranteed fillability.
8. Keep Candidate Eligibility distinct from Execution Feasibility.
9. Do not hide the same filter in both Universe Membership and Eligibility without lineage.
10. Do not proceed to provider-backed Candidate panels until the required eligibility evidence can be represented.
11. Keep Target Horizon distinct from Exit timing.
12. Keep Market/ETF/Theme research available for later controlled incremental comparison.

---

## 13. Audit Conclusion

> **The project remains faithful to the user's latest intended A-share Candidate Discovery → Entry → Position Lifecycle → Exit architecture. No direction-level contradiction was found. One material readiness gap was found before provider-backed Candidate panels: the current v1 Trading Eligibility Policy is a valid minimal ST/suspension and evidence-completeness policy, but it does not yet represent the original first-rehearsal stock-pool requirements for listing age, liquidity and explicit Decision-Time buyability. The next stage must add those capabilities as a versioned provider-rehearsal Eligibility Policy without confusing buyability with final execution feasibility.**
