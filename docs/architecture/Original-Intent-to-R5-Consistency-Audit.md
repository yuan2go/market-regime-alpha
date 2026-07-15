# Original Intent to R5 Consistency Audit

> **Status:** Current implementation-alignment audit before provider-backed R5 rehearsal work
> **Scope:** Preserved original ChatGPT project conversation, Constitution `00–09`, prior R0–R4 consistency audits, current R1 characterization, R5 Research Charter, R5 implementation status, and the controlled multi-date Candidate Discovery vertical slice
> **Authority:** Architecture and implementation interpretation. This document does not override the Constitution.

---

## 1. Audit Question

This audit asks:

> Has the current R5 implementation remained faithful to the user's latest intended A-share research system, or has the controlled Candidate rehearsal drifted into a next-session-close-only system, a fixed-exit overnight strategy, an infrastructure project, or a Candidate model that has lost Market/ETF/Theme context and Position Lifecycle as future owners?

The preserved original conversation is treated as chronological evidence. Later explicit user corrections override earlier assistant formulations.

---

## 2. Latest Preserved User Intent

The original conversation evolved through an important correction.

The earlier narrow formulation was:

```text
T-day late-session entry
        ↓
T+1 morning exit
```

The user explicitly rejected fixed morning exit and clarified that a position should exit when the sell / invalidation logic requires it.

The latest intended system therefore became:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry
        ↓
Repeated Position Lifecycle Evaluation
HOLD / ADD / REDUCE / ROTATE / EXIT
```

The user also retained the practical objective of finding stocks likely to rise or produce a favorable forward opportunity after the decision point.

Therefore Candidate Discovery must eventually represent more than one scalar next-close direction.

The preserved original conversation includes Candidate-oriented outputs such as:

```text
expected_return
expected_mfe
expected_mae
```

and earlier opportunity labels such as:

```text
next_open_return
next_30m_max_return
next_60m_max_return
next_60m_close_return
next_60m_mae
```

These earlier fixed-morning labels are not universal project Exit rules after the user's correction. They remain evidence that the intended Candidate problem includes:

```text
return opportunity
upside excursion
adverse excursion / downside risk
```

rather than only one close-to-close outcome.

---

## 3. Binding Intent Invariants Rechecked

### OI-001 — Candidate Discovery remains the current first new strategic priority

**Result: ALIGNED**

The current R5 implementation is an independent cross-sectional system, not a market-wide loop over `CoscoTimingEngine`.

---

### OI-002 — Candidate Prediction is not a trade action

**Result: ALIGNED**

The current ranking baseline emits Candidate predictions and explicit rejections, not `ENTER`, `HOLD`, `ADD`, `REDUCE`, `ROTATE`, or `EXIT`.

---

### OI-003 — Fixed target horizon is not fixed Exit

**Result: ALIGNED**

The current R5 Charter explicitly states:

```text
Candidate Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

The next-session Target is a research outcome, not a Position Lifecycle clock.

---

### OI-004 — ETF / Theme / Market Context remains upstream and important

**Result: ALIGNED**

The first simple baseline omits these inputs for attribution, but the R5 Charter preserves the intended sequence:

```text
Simple Candidate Baseline
        ↓
+ Market Context
        ↓
+ ETF / Theme Context
        ↓
Controlled Incremental Comparison
```

Their omission from B0 is not an architectural demotion.

---

### OI-005 — Chan, Tuishen-inspired constructs, MACD and similar theories require quantified incremental evidence

**Result: ALIGNED**

The first baseline does not bulk-import Legacy F/R/T/C, Chan, Tuishen, attention, certainty, sell-pressure, flow proxies or dynamic Legacy weights.

---

### OI-006 — Research value must arrive before infrastructure completion

**Result: ALIGNED**

The current project now has a controlled multi-date Candidate research vertical slice rather than only framework contracts.

---

### OI-007 — Legacy remains preserved but non-authoritative for new Candidate architecture

**Result: ALIGNED**

R1 remains active in parallel. New Candidate ranking is not implemented by sorting per-symbol `CoscoTimingEngine` outputs.

---

## 4. Current R5 Document Audit

### 4.1 `R5-Candidate-Discovery-Rehearsal-Charter.md`

**Result: DIRECTIONALLY ALIGNED**

The Charter correctly defines the first R5 question as deliberately narrow and explicitly says it is not:

- a complete trading strategy;
- a universal overnight strategy;
- a fixed next-morning exit rule;
- an Entry policy;
- a Position Lifecycle policy;
- an Exit model;
- an ETF Rotation strategy;
- a production promotion claim.

It also explicitly states that Candidate Discovery is broader than one overnight target and lists future target families including MFE, MAE and expected holding horizon.

### Target-coverage gap found

The Charter currently treats:

```text
next-session MFE
next-session MAE
```

as targets that the first program "may later" materialize.

That wording was acceptable for the fixture-only B0 wiring stage.

It becomes too weak before provider-backed rehearsal work because the original practical objective includes both upside opportunity and adverse excursion, and the future Candidate contract is intended to support:

```text
expected_return
expected_mfe
expected_mae
```

If provider-backed artifacts are built only around one next-session close-return outcome, the implementation may gradually become a close-return-only research system despite broader constitutional language.

### Resolution

Before provider-backed R5 rehearsal is treated as the next major implementation milestone, the minimum R5 opportunity Target set becomes:

```text
1. Next-Session Close Return
2. Next-Session Maximum Favorable Excursion (MFE)
3. Next-Session Maximum Adverse Excursion (MAE)
```

Each remains a separate Target Contract and Target Identity.

They must not be collapsed into one ambiguous `target` column.

The B0 one-feature rank baseline may continue to use close return as its primary evaluation target while MFE/MAE are materialized as separate opportunity/risk outcomes.

This correction does not introduce a fixed Exit rule.

---

### 4.2 `R5-Candidate-Dataset-Builder-Status.md`

**Result: ALIGNED; SCOPE UPDATE REQUIRED**

The document correctly states that the current implementation is:

```text
first controlled multi-date vertical slice implemented
```

and does not claim:

- provider-backed historical Candidate panel;
- formal PIT validation data;
- OOS validation;
- promoted Alpha;
- Entry / Lifecycle / Exit authority;
- live trading authority.

The status document must now record the multi-target opportunity-profile correction before listing provider-backed rehearsal as the next main implementation step.

---

### 4.3 `R1-Legacy-Characterization.md`

**Result: ALIGNED**

R1 remains `ACTIVE` and now correctly records:

- integrated `DividendTStrategy` Golden Behavior cases;
- `trend_snapshot` dual-output characterization;
- `CoscoTimingEngine` stale-data gate characterization;
- remaining `backtest.py`, component-availability, sealed-test and application characterization backlog.

No new Legacy owner has been promoted into the V2 Candidate system.

---

## 5. Current R5 Implementation Audit

### Controlled multi-date panel

**Result: ALIGNED**

The current panel preserves chronological Decision Times and permits PIT Universe identity to change by date.

### Transparent baseline features

**Result: ALIGNED**

The first feature set remains small and lineage-explicit.

### Next-session target materializer

**Result: ALIGNED BUT INCOMPLETE AS AN OPPORTUNITY PROFILE**

The materializer now binds observations to an explicit resolved `next_session_date`, which correctly prevents any arbitrary future date from satisfying "next session".

However, close return alone does not cover the full intended Candidate opportunity profile.

### One-feature rank baseline

**Result: ALIGNED**

The ranker is target-blind, preserves full population accounting through predictions plus explicit rejections, and does not emit Strategy Actions.

### Rehearsal evaluation

**Result: ALIGNED**

The metrics are descriptive and are not represented as formal Alpha or strategy P&L.

---

## 6. Direction-Level Assessment

### Direction-Level Contradiction

```text
NONE FOUND
```

### Material Scope Gap Found

```text
The first provider-backed R5 path would otherwise be centered on one next-session close-return Target while the preserved Candidate objective includes upside excursion and adverse excursion.
```

### Required Correction Before Next Major Data Step

```text
Add separate Target Contracts / Target Materializations for:

Next-Session Close Return
Next-Session MFE
Next-Session MAE
```

The targets must remain identity-distinct and independently evaluable.

---

## 7. Non-Drift Interpretation of the Multi-Target Correction

### MFE does not mean forced profit-taking at the high

MFE is an outcome diagnostic / prediction target.

It does not assume a strategy can execute at the session high.

### MAE is not automatically a stop-loss rule

MAE is an adverse-excursion outcome.

A later Entry, Lifecycle or Exit policy may use validated risk information, but Candidate MAE does not itself create a stop.

### Close Return remains useful

Close Return remains the simplest B0 primary Target for wiring and ranking evaluation.

The correction adds missing opportunity/risk dimensions without invalidating the existing B0 baseline.

### Morning-only opportunity remains a future scoped Target, not the project identity

Earlier original requirements mentioned next-30-minute and next-60-minute opportunity labels.

Those may later become separate scoped Target Contracts when suitable intraday PIT data is available.

They must not restore a universal next-morning Exit rule.

---

## 8. Updated Next Implementation Sequence

The next sequence is now:

```text
Original-Intent-to-R5 Audit
        ↓
Minimum Opportunity Target Bundle
Close Return + MFE + MAE
        ↓
Historical Trading Calendar Resolver
        ↓
Historical PIT Universe Artifact Loader
        ↓
Provider-Backed Rehearsal Market Artifact
        ↓
Multi-Date Candidate Panel
        ↓
B0 / B1 Rehearsal Comparison
        ↓
Immutable R5 Run Artifact
```

Market/ETF/Theme exploratory research and R1 Legacy characterization may continue in parallel.

---

## 9. Guardrails for the Next Stage

1. Do not replace Candidate Discovery with a close-return-only model.
2. Do not collapse Close Return, MFE and MAE into one target identity.
3. Do not interpret MFE as an executable realized return.
4. Do not interpret MAE as an automatic stop-loss policy.
5. Do not convert the next-session horizon into a mandatory holding period.
6. Keep ETF/Theme/Market context available for later controlled incremental comparison.
7. Keep the first baseline simple and target-blind on the feature side.
8. Do not upgrade provider-backed rehearsal data to FORMAL_RESEARCH without the required PIT evidence.
9. Preserve complete Candidate Population accounting.
10. Keep R1 characterization active in parallel.

---

## 10. Audit Conclusion

> **The current R5 implementation remains consistent with the user's latest preserved intent. No direction-level contradiction was found. One material target-coverage gap was found before provider-backed rehearsal work: the controlled implementation currently materializes only next-session close return, while the intended Candidate opportunity profile includes upside and adverse excursion. The project should correct this by adding identity-distinct Close Return, MFE and MAE Target Materializations before proceeding to provider-backed historical rehearsal artifacts.**
