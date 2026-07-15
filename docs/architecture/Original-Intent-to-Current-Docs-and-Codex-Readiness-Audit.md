# Original Intent to Current Documentation and Codex Readiness Audit

> **Status:** CURRENT AUDIT
> **Date:** 2026-07-15
> **Purpose:** Reconcile the preserved original GPT conversation, Constitution, current R5 documents, latest repository changes and current Codex handoff readiness
> **Authority:** Audit and implementation-readiness guidance. The Constitution remains higher authority.

---

## 1. Sources Re-Read

This audit re-reads and reconciles:

```text
Preserved original GPT conversation
        ↓
Constitution / Strategy Constitution
        ↓
R5 Candidate Discovery documents
        ↓
Xuntou provider decision and data-source role policy
        ↓
latest Candidate-model research program
        ↓
latest B1 code / test commits
        ↓
current Entry / Position Lifecycle / Exit research discussion
```

The preserved original conversation remains the historical evidence for the user's intent.

The Constitution remains the highest normative project authority.

---

## 2. Original Intent Invariants Reconfirmed

### OI-01 — The project is A-share focused

The active market scope remains China A-shares.

### OI-02 — Candidate Discovery is the first current research priority

The project must rank a point-in-time tradable cross-section rather than run one Legacy single-symbol timing engine across all stocks and sort an opaque score.

### OI-03 — Candidate Discovery is not the whole trading decision

```text
Candidate Rank
≠
ENTER
```

### OI-04 — Entry and Exit are independent

The preserved conversation explicitly corrected the earlier fixed next-morning-exit framing.

The project therefore preserves:

```text
Candidate Discovery
        ↓
Entry
        ↓
Position Lifecycle
        ↓
Exit
```

### OI-05 — Exit is not a fixed-clock project law

A fixed next-morning exit may remain one strategy/control arm.

It is not the constitutional definition of Exit.

### OI-06 — Position Lifecycle is first-class

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

are distinct decisions for an existing position.

### OI-07 — ETF / Theme / Market / Capital Context remains important

ETF Rotation is not deleted.

It remains:

```text
upstream context / opportunity-scope research
```

and may later become a direct strategy family.

### OI-08 — Candidate output is richer than one score

The intended forward opportunity profile may include:

```text
Expected Return
Expected MFE
Expected MAE
Expected Holding Horizon
probability / uncertainty when valid
context
reasons
invalidation
```

### OI-09 — MACD / MA / Chan / Tuishen are hypotheses, not automatic authority

They must become identified, measurable Features / Context and pass ablation and OOS validation.

### OI-10 — The project must avoid repeated OHLCV double-counting

Feature lineage, family attribution and incremental evidence remain mandatory.

### OI-11 — Legacy assets are preserved through gradual migration

The intended migration remains:

```text
Legacy Freeze
→ Characterization
→ Compatibility Boundary
→ Selective Extraction
→ Evidence-backed retirement
```

not a big-bang rewrite.

### OI-12 — Xuntou is now the active primary provider

The provider-selection phase is over for the current research program.

### OI-13 — Eastmoney / Tencent remain auxiliary

They may support exploration, diagnostics and explicit gap filling under identified source semantics.

They do not silently replace the primary Xuntou path.

### OI-14 — Strategy/model research is more important than provider breadth

The project should implement only the Xuntou data path required by an identified experiment.

### OI-15 — The practical buy/sell objective is now path-dependent

The user wants to reduce:

```text
buy -> immediate adverse move
sell -> strong favorable continuation
```

The correct research response is not another monolithic score.

It is:

```text
Candidate Ranking
+
Entry Path Model
+
Position Lifecycle
+
Exit Continuation / Stopping Model
```

---

## 3. Current Direction-Level Consistency

### Result

```text
Direction-Level Contradiction: NONE FOUND
```

The current Constitution is consistent with the preserved original intent.

The current project still correctly defines:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry
        ↓
Position Lifecycle
        ↓
Exit
        ↓
Portfolio
        ↓
Execution
        ↓
Research Feedback
```

The project has not drifted back into:

```text
fixed next-morning exit
single-symbol timing as project kernel
one giant buy/sell score
provider-integration-first development
```

---

## 4. Current Documentation Drift Found

### DRIFT-01 — B1 status is stale in active research documents

Repository reality:

```text
B1 transparent composite ranking core code        COMMITTED
B1 tests                                          COMMITTED
latest full-repository verification               NOT CONFIRMED
```

But active documents still contain statements equivalent to:

```text
B1 = NEXT MODEL IMPLEMENTATION
or
B1 = NOT YET IMPLEMENTED
```

Correct current status must be:

```text
B1 CORE IMPLEMENTED
VERIFICATION / INTEGRATION PENDING
```

### DRIFT-02 — Entry / Exit research objective was under-specified

The Constitution already separated Candidate, Entry, Lifecycle and Exit.

However, before the current correction, the lower-level active research program was still dominated by Candidate ranking and next-session opportunity targets.

The project lacked one explicit current document for:

```text
buy-then-fall failure
sell-then-rally failure
Entry path-dependent targets
Exit continuation targets
Post-Exit Regret
Position State
competing-event / time-to-event model ladder
```

This gap is now addressed by:

```text
docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md
```

### DRIFT-03 — Current provider status language still references multiple candidate providers

The current provider decision is now fixed:

```text
Primary Provider = Xuntou / ThinkTrader / XtQuant
```

Older generic-provider wording remains useful as architectural compatibility history, but it must not drive active sequencing.

### DRIFT-04 — Current R5 status predates the newest provider and B1 decisions

The short-form current status must be updated so future agents do not read an older state as current truth.

---

## 5. Documentation Coverage Matrix

| Area | Constitutional Direction | Current Lower-Level Documentation | Readiness |
| --- | --- | --- | --- |
| Project vision | Strong | Complete | READY |
| Core principles | Strong | Complete | READY |
| Architecture boundaries | Strong | Complete enough for incremental work | READY |
| Data / PIT governance | Strong | Strong contracts and rehearsal artifacts | READY FOR REHEARSAL |
| Xuntou provider role | Explicit | Current provider decision exists | READY |
| Public auxiliary source role | Explicit | Current role matrix exists | READY |
| Candidate dataset / panel | Explicit | Implemented contracts | READY FOR TESTED INCREMENTS |
| Candidate targets | Close Return / MFE / MAE | Implemented rehearsal family | READY |
| B0 | Defined | Implemented | READY |
| B1 | Defined | Core implemented; verification pending | PARTIAL |
| B2 / B3 | Research ladder defined | No implementation contract yet | NOT CURRENT BLOCKER |
| Entry research | Constitutional boundary exists | New research program added | SPECIFIED, NOT IMPLEMENTED |
| Entry path Target contract | Required | No code-level contract/materializer yet | MISSING P0 |
| Position State contract | Required | High-level semantics only | MISSING P0 BEFORE EXIT MODEL |
| Exit continuation Target contract | Required | New research program only | MISSING P0 BEFORE EXIT MODEL |
| Exit control-arm specification | Required | Research program names baselines | NEEDS LOWER-LEVEL SPEC |
| Xuntou native adapter | Provider selected | No native field adapter yet | MISSING P0 |
| Provider-backed real rehearsal run | Required | Not available | MISSING P0 EVIDENCE |
| Immutable research run artifact | Roadmap requirement | Not implemented | MISSING P0 BEFORE CLAIMS |
| Chronological / OOS evidence | Required | Protocol exists, no real run evidence | MISSING EVIDENCE |
| Full latest-HEAD quality execution | Required for implementation authority | Not confirmed | MISSING P0 |
| Codex repository instructions | Needed for reliable autonomous implementation | No root `AGENTS.md` found before this audit | MISSING P0 HANDOFF |

---

## 6. What the Project Still Lacks

### P0-A — One authoritative current implementation-status document

It must accurately state:

```text
Xuntou selected as primary provider
Eastmoney / Tencent auxiliary
B1 core implemented, verification pending
Entry/Lifecycle/Exit research program specified
Xuntou native adapter not implemented
real provider-backed run not available
latest full HEAD verification not confirmed
```

### P0-B — Root Agent execution contract

Before Codex is asked to work continuously, the repository needs a root instruction file defining:

```text
document precedence
current authority files
architecture invariants
forbidden shortcuts
quality commands
commit discipline
stop conditions
what Codex may implement without redesign authority
```

### P0-C — B1 verification repair

Known current issue:

```text
an AVAILABLE Target test fixture lacks the required future observed_at evidence
```

The B1 evaluation integration also needs a common structural ranking interface rather than a B0-specific type assumption.

### P0-D — Xuntou native adapter specification and minimal implementation

The project needs a field-level mapping for only the data required by the next experiments:

```text
trading calendar
A-share universe / security master evidence
listing date
historical ST
suspension / status
price limits
daily OHLCV / amount
14:55 Decision-Time observation
next-session OHLC
```

The adapter must not invent:

```text
availability time
historical PIT membership
bar finality
adjustment basis
buyability
```

### P0-E — Entry Path Target code contract

The research program is now defined, but implementation still needs identified contracts for:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
barrier specification identity
horizon identity
observation status
materialization artifact identity
```

### P0-F — Position State code contract

Before Exit can be implemented credibly, the project needs a canonical identified state for an existing position.

Minimum future semantics:

```text
entry reference
current exposure state
MFE / MAE since entry
drawdown from high
holding duration
original thesis reference
current thesis validity
```

### P0-G — Exit Continuation Target code contract

Required labels:

```text
CONTINUE_UP_FIRST
DRAWDOWN_FIRST
TIMEOUT
```

with separate diagnostics for:

```text
Post-Exit Regret
Avoided Drawdown
Late Exit
Profit Giveback
```

### P0-H — Real provider-backed rehearsal evidence

No strategy/model claim should be promoted until the Xuntou path produces reproducible multi-date rehearsal artifacts.

### P0-I — Latest full repository verification

Before increasing implementation authority, run:

```text
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

and preserve the actual result.

---

## 7. Important Missing Documents That Are Not Immediate Blockers

### P1-01 — Xuntou Native Field Mapping Specification

A dedicated lower-level specification should record:

```text
native API / export field
canonical field
source time
availability convention
finality convention
adjustment basis
PIT caveat
permission dependency
```

### P1-02 — Entry Path Target Specification

The current research program gives semantics.

A lower-level implementation specification should freeze:

```text
schema
barrier identity
same-bar ordering rules
price source
intraday high/low ordering limitations
suspension / limit-state handling
missing future observation semantics
```

### P1-03 — Position State Specification

Needed before Lifecycle / Exit implementation expands.

### P1-04 — Exit Continuation and Control-Arm Specification

Needed before comparing:

```text
fixed time
trailing stop
time stop
risk stop
continuation model
```

### P1-05 — Immutable Research Run Artifact Specification

Should bind:

```text
code revision
datasets
universe
features
targets
models
split
metrics
cost assumptions
artifacts
negative results
```

### P1-06 — Xuntou Provider-Backed Experiment Runbook

Should define:

```text
how to obtain data
how to persist source artifacts
how to build REHEARSAL datasets
how to rerun EXP-CAND / EXP-ENTRY / EXP-EXIT
```

### P1-07 — Candidate-to-Entry Interface Specification

The project needs an explicit handoff contract so Candidate scores do not silently become actions.

### P1-08 — Lifecycle Transition Specification

The Strategy Constitution defines actions, but a lower-level state-transition and proposal contract is still needed before production-like lifecycle code.

---

## 8. What Does Not Need to Be Completed Before Codex Starts

The following are not prerequisites for bounded Codex development:

```text
full ETF rotation strategy
full Level-2 integration
full Xuntou API coverage
reinforcement learning
deep-learning order-book model
complete Legacy migration
automatic broker execution
production Alpha promotion
```

Trying to complete these first would violate the current strategy-research priority.

---

## 9. Codex Readiness Decision

### 9.1 Ready for bounded implementation work

```text
YES
```

Codex can now work effectively on narrowly defined packages where:

```text
one owner
one task boundary
one acceptance test set
no architecture redesign
no provider-semantic guessing
no research conclusion invention
```

### 9.2 Not ready for unrestricted autonomous development of the entire project

```text
NO
```

The repository should not yet receive a prompt equivalent to:

```text
"Continue building the whole quant system until complete."
```

Reasons:

```text
B1 verification is not closed
Xuntou native mapping is not implemented
real provider-backed run evidence is absent
Entry path contracts are not implemented
Position State is not implemented
Exit continuation contracts are not implemented
latest full-HEAD tests are not confirmed
```

### 9.3 Correct handoff model

Use:

```text
Design / Research Authority
        ↓
small approved Work Package
        ↓
Codex implementation
        ↓
tests / static checks
        ↓
review against Constitution and task spec
        ↓
commit
        ↓
next Work Package
```

---

## 10. Recommended Codex Work Packages

### WP-0 — Close B1 Verification

Scope:

```text
repair Target observed_at test fixture
introduce a common structural Candidate Ranking evaluation interface
remove B0-specific type workaround
export B1 public API where intended
include B1 in mypy scope
run focused tests
run full repository quality commands when environment permits
```

Stop condition:

```text
Do not change B1 scoring semantics while repairing verification.
```

### WP-1 — Xuntou P0 Native Adapter Specification

Scope:

```text
map only fields needed by EXP-CAND-001 through EXP-CAND-005
record unsupported / ambiguous PIT semantics explicitly
no broad API coverage
```

### WP-2 — Xuntou P0 Native Adapter Implementation

Depends on WP-1.

### WP-3 — Provider-Backed B0 / B1 Rehearsal

Produce reproducible Xuntou REHEARSAL artifacts.

No Alpha claim.

### WP-4 — Entry Path Target Contracts

Implement only:

```text
barrier specification identity
UP_FIRST / DOWN_FIRST / TIMEOUT
materialization state semantics
tests
```

Do not implement a complex predictive model in the same package.

### WP-5 — EXP-ENTRY-001 Baseline

Compare Candidate-only versus Candidate + simple Entry path model.

### WP-6 — Position State Contract

Implement canonical state before Exit modeling.

### WP-7 — Exit Continuation Target Contracts and Control Arms

Implement simple control arms before nonlinear Exit models.

---

## 11. Promotion Rule for Codex Autonomy

Codex may receive broader multi-step implementation authority only after:

```text
root Agent instructions exist
current status is accurate
latest quality commands are executable
work package dependencies are explicit
acceptance tests are named
stop / escalation conditions are explicit
```

Even then, Codex must not independently:

```text
change Constitution
reinterpret project goals
promote Alpha
invent provider PIT semantics
open sealed final-test evidence
replace Entry / Exit independence with one score
add broad Legacy rules to V2
```

---

## 12. Final Audit Conclusion

```text
Original Intent Alignment            PASS
Constitution Alignment               PASS
Xuntou Provider Decision             PASS
Strategy-Research Priority           PASS
Candidate Research Direction         PASS
Entry / Exit Independence            PASS
Path-Dependent Buy/Sell Objective     NOW DOCUMENTED
B1 Status Consistency                NEEDS CURRENT-STATUS UPDATE
Xuntou Native Integration            NOT YET IMPLEMENTED
Real Provider Rehearsal Evidence      NOT AVAILABLE
Codex Bounded Work Readiness          YES
Codex Unrestricted Project Autonomy   NO
```

> **The project is now sufficiently designed for Codex to implement bounded, explicitly specified work packages. It is not yet sufficiently evidenced or operationally constrained for an unrestricted “finish the whole system” loop. The immediate priority is to close B1 verification, freeze the minimum Xuntou native mapping, run provider-backed B0/B1 rehearsal, then implement Entry path targets before expanding into Position Lifecycle and Exit continuation models.**
