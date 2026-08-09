# Free-Data Research and Shadow Runtime Convergence Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** User-approved implementation design for the 2026-08-09 runtime convergence work
> **Baseline:** `origin/main@fee02f68d3d3e4745ec25920f022a2436e4ae08a`
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../plans/2026-08-09-free-data-research-shadow-runtime-convergence.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `fee02f68d3d3e4745ec25920f022a2436e4ae08a`; `src/market_regime_alpha`; `tests`
> **Authority ceiling:** Free-data exploratory engineering evidence only; no Entry, Order, Fill, Broker, or Position mutation authority

## 1. Objective

Converge the existing FreeData, Continuous Research, Controlled Operation,
State System, Model Governance, Canonical Lifecycle, and Decision System
mechanics into one executable PostgreSQL-authoritative runtime that can consume
the declared BaoStock/Tencent free-data profile and always reaches an immutable
Research or Shadow Daily Summary when the runtime itself remains healthy.

Missing ETF, Theme, Capital, Candidate, Signal, or Forecast evidence is a
research result. It is not a reason for the Tick or Summary to disappear.
Production remains independently fail-closed.

## 2. Audited starting facts

- `ContinuousResearchTickRunner` already owns Tick admission, leases, fencing,
  provider Attempts, Evidence commits, material-change decisions, child
  references, restart, and replay.
- `continuous-research` exposes Journal administration but does not construct a
  provider, child composition, Tick runner, and scheduler into an executable
  due-Tick command.
- `ExistingResearchServiceComposition` is exercised only with test delegates.
  There is no production composition root.
- `FreeDataOperationService` already composes the real DailyLoop and Controlled
  services, but its single `prepare()` call freezes history, same-day status,
  and DecisionTime quote together. The request also rejects creation before
  DecisionTime.
- `ControlledDecisionTimeOperationRunner` already owns the actual Dataset,
  Feature, Market/Theme/Capital research, Candidate, Tencent minute, Signal,
  Forecast, and Canonical child work. Re-running those stages through parallel
  Continuous children would duplicate authority.
- `StateSystemRuntimeDelegate` has durable mechanics and an ordered protocol,
  but production stage services are not composed. ETF, operational Theme
  membership, and Capital evidence are not available in the built-in free-data
  bundle.
- `DecisionSystemRuntimeService` selects Signal and Forecast with a hard-coded
  `RuntimePurpose.PRODUCTION_DECISION` before Summary creation. It also requires
  Manual Account/Reconciliation before its current Summary, so it cannot be the
  Research/Shadow endpoint.
- Controlled model implementations are selected by caller-supplied runtime
  configuration. A manifest records them, but the Registry does not admit the
  actual Market/Theme/Capital/Candidate/Signal/Forecast invocation.

## 3. Considered approaches

### 3.1 Patch only the Decision gate

Map `PRODUCTION_DECISION` to a caller purpose and keep the existing account
summary. This is small but still requires a Manual Account, leaves Continuous
non-executable, and does not solve duplicated child authority. Rejected.

### 3.2 Build new State and research pipelines under Continuous

Implement every State stage from scratch and replace Controlled Operation.
This can match the desired diagram literally but creates a parallel research
pipeline and discards tested acquisition, Feature, minute, replay, and
Canonical mechanics. Rejected.

### 3.3 Compose existing owners and add only missing contracts

Keep Continuous as the sole all-day owner and Controlled Operation as the sole
DecisionTime research execution service. Add a small authority-mode contract,
a Registry admission layer around the actual configured models, explicit State
stage projections (including typed missing stages), and an account-neutral
Research/Shadow Summary in DecisionSystem. The Continuous composition root
invokes the bounded services once and records their exact outputs as its child
lineage. Selected.

## 4. Runtime authority modes

`RuntimeAuthorityMode` has exactly `RESEARCH`, `SHADOW`, and `PRODUCTION`.
It maps to Model Governance without aliases:

| Runtime mode | Registry purpose | Data admitted | Trading authority |
|---|---|---|---|
| `RESEARCH` | `RESEARCH` | explicit exploratory and PIT-incomplete eligibility allowed by the selected policy | none |
| `SHADOW` | `SHADOW` | explicit exploratory and PIT-incomplete eligibility allowed by the selected policy | none |
| `PRODUCTION` | `PRODUCTION_DECISION` | existing strict formal eligibility and complete qualification floor | fail closed unless authorized |

The mode is part of the Continuous command, Tick command, child request,
selection request, Summary identity, runtime receipt, report, and replay
fingerprint. Historical V1 Continuous commands remain readable as `RESEARCH`
because their existing authority ceiling explicitly blocks Entry and Broker.

`PRODUCTION` keeps the existing account/reconciliation/portfolio/risk path and
requires `production_authorized=true`. Research and Shadow never interpret that
boolean as their admission criterion; they require a selected receipt for their
own purpose. A rejected Research/Shadow selection becomes Summary outcome
`MODEL_NOT_QUALIFIED_FOR_MODE`, not a missing Summary.

## 5. Canonical free-data profile

The only built-in default is:

```text
BaoStock: prior-session daily history + exact-date basic/trading status
Tencent: DecisionTime quote + candidate minute evidence
```

There is no provider fallback. Provider profile identity, provider IDs,
products, request hashes, raw/stage Artifact identities, SourceManifest,
retrieval/availability semantics, and limitations are bound to Evidence and
Summary lineage. AKShare and Tushare remain explicitly selected
`FREE_DATA_EXPLORATORY` extensions and cannot inherit the default profile ID.

BaoStock or Tencent acquisition failure records a failed Provider Attempt and
does not call another provider. Late or future evidence is rejected before it
can become current Evidence.

## 6. Executable composition

The `continuous-research run-due` entry constructs one composition root:

```text
PostgreSQL RepositoryFactory
  -> Continuous schedule and Tick runner (sole all-day owner)
  -> staged BaoStock/Tencent acquisition
  -> existing FreeData/Controlled preparation and DecisionTime execution
  -> Registry admission for each actually executed configured model
  -> explicit State stage evidence projection
  -> account-neutral Research/Shadow Daily Summary
  -> existing Production Decision path only in PRODUCTION mode
```

The composition calls each bounded service once. Continuous child references
are views over existing durable receipts and immutable Artifacts; they do not
copy domain state or invoke a second Dataset, Feature, Candidate, Signal, or
Forecast implementation.

The executable input manifest binds the FreeData request, runtime
configuration, model runtime lineages, artifact root, and provider profile.
The CLI accepts an explicit PostgreSQL URL and never falls back to SQLite.

## 7. Stage result semantics

Every research stage has one immutable `ResearchStageEvidence` with status:

- `COMPLETED`
- `DATA_INSUFFICIENT`
- `MODEL_NOT_QUALIFIED_FOR_MODE`

The stages are Observation, Market Regime, ETF Rotation, Theme Rotation,
Capital, Dynamic Pool, Candidate, Signal, and Forecast. Each binds input/output
Artifact IDs and hashes, `available_at`, `DataEligibility`, Evidence ceiling,
model-selection receipt when a model ran or was requested, missing evidence,
and reason codes.

ETF, Theme, or Capital absence produces a stage-level `DATA_INSUFFICIENT`.
Dynamic Pool and downstream stages consume that state and remain explicitly
insufficient; they do not synthesize memberships, flows, forecasts, or
candidates.

Only PostgreSQL integrity/corruption, identity/hash mismatch, future-data
violation, invalid DecisionTime, stale fencing, unrecoverable lineage conflict,
or an equivalent authority failure may prevent normal Summary publication.

## 8. Research and Shadow Daily Summary

`ResearchDailySummary` is owned by the existing DecisionSystem bounded context
but is account-neutral. It binds:

- runtime mode, Continuous run/Tick, and DecisionTime;
- provider profile and Provider contract references;
- SourceManifest, Dataset, Feature Bundle;
- every State stage receipt and Dynamic Pool result;
- Candidate, Signal, and Forecast references;
- all Model Selection receipts;
- runtime/model/configuration identities;
- DataEligibility, Evidence ceiling, missing evidence, and reason codes.

Outcomes are `NO_ACTION`, `WATCH`, `RESEARCH_CANDIDATE`,
`DATA_INSUFFICIENT`, and `MODEL_NOT_QUALIFIED_FOR_MODE`.

One original terminal Summary exists for a mode, trading date, and runtime
configuration. Corrections are new immutable revisions that reference the
original or previous revision. Summary construction has no dependency on
Manual Account, Portfolio, Risk, Opportunity, Order, Fill, Broker, or Position.

SHADOW uses the same Summary contract plus explicit prospective-observation
status and safety declarations. It creates no simulated Broker or Portfolio.
The frozen Summary and lineage are sufficient for a later T+1 outcome to bind
MFE, MAE, and returns.

## 9. Model Governance

Before each actually configured Market Regime, Theme Rotation, Capital,
Candidate, Signal, or Forecast model executes, the composition:

1. resolves the Champion for the exact mode/purpose and slot;
2. requests selection with exact Dataset/Universe/Feature/config/code lineage;
3. persists the accepted or rejected receipt;
4. verifies selected model/version/configuration against the bounded executable
   catalog;
5. executes only an accepted selected model.

ETF Rotation without ETF evidence is a missing-evidence projection and does
not pretend that a model ran. Dynamic Pool gates and evidence-ceiling joins are
deterministic policies, not predictive models, and therefore use immutable
configuration receipts rather than Model Registry assignments.

A rejected Research/Shadow selection is preserved in Summary. A rejected
Production selection blocks the Production path. No caller-declared
qualification is trusted.

## 10. Idempotency, recovery, and replay

Continuous retains its existing lease, fencing, CAS, provider Attempt,
Evidence Commit, material-change decision, and child-reference mechanics.
`NO_MATERIAL_CHANGE` reuses the prior child and Summary identities.

The composition records an immutable execution receipt after each bounded
service output. On restart it reloads and validates existing outputs before
executing missing work. A stale worker cannot save a stage or Summary.

Replay reads the stored command, mode, provider/source lineage, stage evidence,
selection receipts, and Summary. It performs no network access and compares
the deterministic Summary identity and stage fingerprints. Historical
selection is replayed from its receipt revision, not from current assignments.

## 11. Safety and evidence ceiling

The Evidence ceiling is a monotone meet over every input. Free-data runs remain
`FREE_DATA_EXPLORATORY` / `PIT_INCOMPLETE` or weaker. No downstream stage may
write `FORMAL_PIT` or `FORMAL_RESEARCH` unless all exact upstream authorities
support it.

Research and Shadow receipts always declare:

```text
NO_ORDER
NO_FILL
NO_BROKER
NO_POSITION_MUTATION_FROM_SHADOW
ENTRY_BLOCKED
```

The composition has no dependency on an Order, Fill, Broker, or Position write
port.

## 12. Verification and stop conditions

Focused PostgreSQL tests cover mode mapping and selection, Summary reachability,
missing-stage propagation, provider failure/no fallback, late/future evidence,
no-material-change reuse, stale fencing, restart/resume, deterministic replay,
and Shadow safety. The repository-wide quality gate is the user-specified `uv`
command set.

Live Provider evidence is reported separately from engineering evidence. If a
real session rehearsal is not observed, the result is
`ENGINEERING_RUNTIME_PROVEN` plus `LIVE_FREE_DATA_RUNTIME_NOT_YET_OBSERVED`.

Genuine stop conditions are PostgreSQL unavailability that cannot be repaired
locally, an external Provider outage for live rehearsal, or evidence that the
required behavior cannot be implemented without violating the authority
ceiling. Ordinary implementation defects are not stop conditions.
