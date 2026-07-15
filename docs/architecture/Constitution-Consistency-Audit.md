# Constitution Consistency Audit

> **Status:** R0 closeout audit
> **Scope:** Original project intent, Constitution Volumes `00–09`, current Legacy architecture, and the transition into R1/R2 implementation
> **Authority:** Implementation interpretation and R0 closeout record. This document does not create a new Constitution volume and does not override `docs/constitution/00–09`.

---

## 1. Audit Question

The audit asks:

> Has the project drifted away from the original practical research objective while expanding into an Alpha Research Operating System, and are there any cross-volume semantic inconsistencies that could cause implementation drift?

The original practical direction reconstructed from the project conversation history is:

```text
Market / ETF / Theme / Capital Direction
        ↓
Find the strongest or potentially strengthening opportunity set
        ↓
Select individual stocks with attractive next-stage / next-session upside potential
        ↓
Independent Entry decision
        ↓
Repeated Position Lifecycle evaluation
HOLD / ADD / REDUCE / ROTATE / EXIT
        ↓
Re-enter the discovery loop
```

Important evolution of that original direction:

1. The project began with ETF/sector/theme rotation as an upstream way to detect capital direction and narrow opportunities.
2. The next layer was stock selection: combine market hot spots, capital behavior, price-volume evidence, MACD, Chan-derived structure, Tuishen-inspired constructs and other factors to identify stocks with attractive future upside probability or expected path.
3. The original late-session-entry / next-morning-exit idea was explicitly revised. Fixed next-morning exit became a strategy-specific baseline, not the universal project exit rule.
4. Position management became a repeated decision problem: `HOLD / ADD / REDUCE / ROTATE / EXIT`.
5. Entry and Exit became independent research systems.
6. The project later adopted the Alpha Research Operating System framing to make those research programs verifiable, reviewable and extensible. The Research OS is the container for the practical research mission; it is not a replacement for it.

---

## 2. Audit Result

### 2.1 Direction-level result

**No direction-level drift was found.**

Volumes `00–09` consistently preserve the following original objectives:

- A-share focus;
- Market Regime, ETF and Theme information as upstream context or research programs;
- Candidate Discovery as the current first strategic new research priority;
- stock-level opportunity ranking rather than only single-symbol timing;
- independent Entry;
- repeated Position Lifecycle management;
- independent Exit and invalidation logic;
- fixed-time exit as a baseline or strategy-specific policy only;
- quantitative treatment of MACD, moving averages, volume-price, Chan and Tuishen-inspired ideas;
- professional/PIT-capable data as necessary for higher-authority claims, without making one vendor the architecture;
- research before automatic capital deployment;
- preservation and selective migration of Legacy knowledge rather than a rewrite.

### 2.2 Critical implementation warning

The Alpha Research Operating System framing must not become an excuse for infrastructure-only work.

The implementation interpretation is therefore:

```text
Research OS
is the governance and architecture that enables the original research loop.

It is not a reason to postpone Candidate Discovery until every future platform component is complete.
```

The two-track roadmap remains binding:

```text
Track A — Platform and Evidence Spine
+
Track B — Research Value Delivery
```

Candidate rehearsal and baseline research must start as soon as the minimum trustworthy spine exists.

### 2.3 ETF / Theme interpretation

Candidate Discovery being the first implementation priority does **not** mean ETF, Theme or Market Regime research is unimportant or permanently downstream.

The canonical distinction is:

```text
Final research/decision architecture:
Market / ETF / Theme Context
        ↓
Candidate Discovery

Implementation and attribution sequence:
Minimal Candidate Baseline
        ↓
Add ETF / Theme / Market Regime context through controlled comparison
```

Exploratory ETF, Theme and Market Regime research may run in parallel before R9. R9 is the stage for canonical integration and authority, not the earliest date on which research may begin.

---

## 3. Cross-Volume Consistency Findings

The audit found five non-directional semantic or documentation residues. They do not change the project destination, but implementation must follow the canonical interpretation below.

### C-001 — Pre-Data-Constitution eligibility vocabulary in Architecture

**Location:** `02-Architecture-Blueprint.md`

Earlier architecture examples use phrases such as:

```text
formal candidate
sealed-test eligible
production eligible
```

These predate the final canonical model.

**Canonical implementation:**

```text
Data Eligibility:
UNQUALIFIED / EXPLORATORY / REHEARSAL / FORMAL_RESEARCH

Sample Role:
DEVELOPMENT / TRAIN / VALIDATION / CALIBRATION /
OOS_TEST / SEALED_TEST / SHADOW_OBSERVATION

Evidence Level:
E0 ... E6

Authority State:
SHADOW / PROMOTED_FOR_SCOPE / DEGRADED /
QUARANTINED / RETIRED
```

No R2 API may create a second global eligibility ontology from the older wording.

**Resolution status:** Resolved by canonical interpretation from `04`, `07` and `09`; implementation must use the canonical four-dimensional model.

---

### C-002 — Unqualified `confidence` wording

**Locations:** earlier Architecture, Factor and Strategy wording.

The word `confidence` can mean:

- model score;
- calibrated probability;
- uncertainty estimate;
- evidence strength;
- subjective analyst confidence.

**Canonical implementation:** new contracts must use the precise semantic type. Do not create a generic platform-wide `confidence: float` field.

Use, as applicable:

```text
model_score
rank_score
calibrated_probability
uncertainty
probability_calibration_status
evidence_level
```

**Resolution status:** Resolved by `09-Glossary`; R2 will not introduce a generic confidence type.

---

### C-003 — Mixed workflow/authority examples in early Validation wording

**Location:** `07-Validation-Constitution.md`, early Authority Decision examples.

An earlier example list includes names that can be interpreted as workflow decisions, evidence states and authority states together.

**Canonical implementation:** keep the dimensions separate:

```text
Review Outcome:
PASS / CONDITIONAL_PASS / REVISE / FAIL / QUARANTINE

Evidence Level:
E0 ... E6

Authority State:
SHADOW / PROMOTED_FOR_SCOPE / DEGRADED /
QUARANTINED / RETIRED
```

`E6 — PROMOTION_CANDIDATE` is an Evidence Level, not a generic status value.

**Resolution status:** Resolved by `07` later sections and `09`; R2 registries must not use one mixed status enum.

---

### C-004 — `NO_ACTION` grouped with availability/error semantics in Roadmap R2

**Location:** `08-Roadmap.md`, R2 initial semantic list.

`NO_ACTION` is not a Data Availability Status.

**Canonical implementation:** separate:

```text
Availability / validity semantics:
MISSING
UNAVAILABLE
STALE
INVALID
UNSUPPORTED
BLOCKED

Strategy Action:
NO_ACTION
```

A missing or blocked input may lead to `NO_ACTION`, but the two belong to different owners and must not share one enum.

**Resolution status:** Resolved for implementation; R2 code must encode separate types.

---

### C-005 — Formatting defect in Architecture Legacy migration section

**Location:** `02-Architecture-Blueprint.md`, `point_hit_rate.py` migration note.

A Markdown bold marker is not closed correctly.

**Impact:** formatting only; no semantic effect.

**Resolution status:** Non-blocking documentation cleanup. It must not delay R1/R2 and may be corrected during the next safe full-document edit.

---

## 4. Original Intent to Constitution Traceability

| Original practical objective | Constitutional location | Audit result |
|---|---|---|
| Use market/ETF/theme/capital direction to narrow opportunities | `00`, `05`, `06`, `08`, `09` | Preserved |
| Select stocks likely to have attractive next-stage upside | Candidate Discovery in `00`, `03`, `05`, `06`, `07`, `08` | Preserved and made cross-sectional |
| Late-session / next-session research | examples and research programs in `00`, `03`, `06`, `07` | Preserved as scoped research, not project identity |
| Do not force next-morning exit | `00`, `06`, `07`, `08` | Preserved |
| Hold / add / reduce / rotate / exit after entry | `00`, `06`, `07`, `08`, `09` | Preserved |
| Combine MACD / MA / volume / Chan / Tuishen | `05`, `06`, `07` | Preserved, with lineage and validation requirements |
| Track capital flow | `04`, `05`, `09` | Preserved, real/proxy semantics separated |
| Use professional data where needed | `00`, `04`, `08` | Preserved, no single-vendor lock-in |
| Validate and iterate rather than trust one backtest | `01`, `03`, `07` | Strengthened |
| Preserve current working Legacy system | `00`, `02`, `08`, `09` | Preserved through Strangler migration |

---

## 5. R0 Exit Decision

R0 may close when this audit record and repository identity alignment are committed.

The R0 exit decision is:

```text
Direction-Level Contradiction: NONE FOUND
Canonical Vocabulary: FROZEN BY 09-GLOSSARY
Legacy Freeze: ACTIVE
Known Semantic Residues: DOCUMENTED AND CANONICALLY RESOLVED FOR IMPLEMENTATION
Next Stage: R1 / R2 CONTROLLED OVERLAP
```

R1 characterization may continue while the minimal R2 kernel is built.

---

## 6. Binding Implementation Constraints for R1/R2

1. Do not add new platform-wide responsibilities to `CoscoTimingEngine` or the Legacy backtest God Object.
2. Do not implement Candidate Discovery as a market-wide loop over a symbol-specific timing score.
3. Do not create a second action vocabulary.
4. Do not create a second Experiment Identity ontology.
5. Do not use one mixed enum for Data Eligibility, Sample Role, Evidence Level and Authority State.
6. Do not use generic `confidence` in a new platform-wide contract.
7. Do not put `NO_ACTION` in a data-availability enum.
8. Do not rename `dividend_t` as a substitute for architecture migration.
9. Preserve Legacy behavior before destructive extraction.
10. Build the smallest R2 identity/time/research-contract spine that directly enables the next Candidate research step.
11. Keep ETF/Theme/Market Regime research available as parallel research programs; do not make them mandatory hard gates for the first Candidate baseline.
12. Do not wait for perfect future data before building a clearly labeled exploratory/rehearsal Candidate pipeline.

---

## 7. Closeout Principle

> **The project has not drifted from its original research mission. The Research Operating System is valid only insofar as it makes the original market-context → opportunity-discovery → entry → lifecycle → exit loop more measurable, testable and improvable. R1/R2 implementation must now prove that by producing a minimal trustworthy spine without delaying research value.**
