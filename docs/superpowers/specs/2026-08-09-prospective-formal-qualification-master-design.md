# Prospective Research to Formal Qualification — Master Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Current user request, Constitution, Architecture 09–15, existing bounded-context authorities
> **Baseline:** `origin/main@ecbe40ab7a39ba87e460be0c268ffaab2baf4dd0`
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../plans/2026-08-09-prospective-formal-qualification-master.md, ../../status/Current-State.md
> **Code Evidence:** `src/market_regime_alpha`; `tests`; PostgreSQL migrations 001–033
> **Authority ceiling:** Free-data exploratory engineering evidence. No Formal PIT/OOS, qualification, Production, Entry, Order, Fill, Broker, or Position authority.

## Objective and dependency rule

Extend the one Canonical Stateful Free Runtime into a research loop that can
eventually be contradicted by prospective market outcomes and admitted by the
existing Model Governance authority. Work proceeds only in this order:

```text
operational free evidence → exact-window live → prospective Shadow
→ T+1 factual outcome → attribution → exploratory evaluation
→ real Formal PIT → locked OOS → cost/capacity → governance qualification
```

Passing engineering tests never satisfies a later evidence gate. Fixture is not
Live, replay is not prospective, exploratory is not Formal PIT, and a metric is
not a qualification action.

## Verified starting facts

- `CanonicalFreeDataResearchComposition` is the sole executable Continuous
  composition and calls the PostgreSQL State System owner before Controlled,
  Canonical Lifecycle, and Decision System owners.
- Recorded-provider PostgreSQL tests reach a non-empty Stateful
  `RESEARCH_CANDIDATE`, but the complete ETF/Theme/Capital supplemental bundle
  is supplied as a prebuilt test artifact.
- Built-in preparation creates honest missing evidence. It has no operational
  ETF Universe, Theme mapping/membership, or Capital producer.
- The Daily acquisition journal already owns scoped, immutable, restart-safe
  Provider-stage receipts. It is the correct recovery seam for an additional
  static supplemental acquisition; no new Runtime Journal is required.
- Controlled Operation contains a factual T+1 outcome artifact/source archive,
  but no current Summary-scoped PostgreSQL Shadow Session/Outcome authority.
- Existing trade attribution is Fill/Position lifecycle diagnostics, not layer
  attribution for prospective research decisions.
- PostgreSQL Model Governance already separates existence, qualification,
  Champion assignment, purpose-specific selection, and immutable receipts.

## Canonical authority map

| Fact | Sole owner | Reused durable authority |
|---|---|---|
| Provider request/bytes and acquisition recovery | Daily acquisition stage under Canonical Free Runtime | PostgreSQL Daily receipt + immutable source-stage Artifact |
| Free ETF identity/tracking policy and Theme taxonomy semantics | versioned deterministic operational evidence policy | content-addressed policy source bound into SourceManifest |
| ETF/Theme/Capital observations and missingness | Operational Research evidence producer | supplemental evidence Artifact + Reader |
| Market/ETF/Theme/Capital state and Dynamic Pool | WP-STATE-01 | PostgreSQL state/pool rows and real runtime receipt |
| Candidate/Signal/Forecast/Summary | existing bounded contexts | existing immutable artifacts and PostgreSQL receipts |
| future Shadow Session/Decision | Continuous/Decision control boundary | one additive PostgreSQL authority, only after Live gate |
| future T+1 Outcome | factual Outcome bounded context | adapt existing outcome artifact to Summary lineage; one PostgreSQL index |
| future Attribution/Evaluation | Review and Attribution | immutable reports over frozen decisions/outcomes |
| formal evidence and qualification | existing PIT and Model Governance | existing authorities only |

## WP-EVIDENCE-OPS-01 design

The default operational producer uses an explicit, versioned broad-market
research policy and BaoStock prior-session ETF daily history. The policy defines
ETF identity, tracking-index identity, effective Theme taxonomy, mapping
semantics, and bounded membership rules. It is data, not model qualification:
its exact bytes, version, retrieval time and limitations enter the
SourceManifest, while the stage receipt binds the executing code/configuration.
Observations are computed only from acquired ETF bars and the already verified
stock Dataset.

The first policy intentionally represents the operator-approved research
Universe as a broad observable Theme with a declared market ETF proxy. It does
not claim that every stock is an index constituent, that the mapping is Formal
PIT, or that Capital proxies reveal hidden investor intent. Richer industry or
concept Providers may later replace it only through explicit configuration;
there is no fallback.

The producer emits:

- effective policy-bound Theme memberships and ETF↔Theme mapping;
- multi-horizon ETF strength, amount persistence, volatility, drawdown,
  diffusion/liquidity and coverage;
- Theme breadth, relative strength, participation and leader proxies;
- observable Capital amount, persistence, concentration and diffusion proxies;
- exact coverage, missing evidence, `AvailableAt`, `RetrievedAt`, provider
  contract and source identity.

Insufficient history, missing symbols or Provider failure are typed evidence
results or fail-closed acquisition failures. No static observation is generated.
The source stage receipt makes restart reuse successful bytes without another
Provider call.

## Later WP boundaries and Exit Gates

| WP | Engineering scope | Exit Gate evidence |
|---|---|---|
| LIVE-01 | trusted clock, latency/deadline/lease report and runbook | multiple real trading-day 14:54–14:55 runs and replay |
| SHADOW-01 | Summary-scoped immutable session/decision status | consecutive decisions frozen before outcomes, with recovery drills |
| OUTCOME-01 | Summary-linked 09:30/10:00/10:30, MFE/MAE/return facts | same frozen decision settles/replays identically after T+1 availability |
| ATTR-01 | baseline/ablation/grouped layer attribution | each layer can be supported, falsified, downweighted or removed |
| EVAL-01 | exploratory metrics and frozen baselines | `KEEP/REWORK/REJECT/INSUFFICIENT_SAMPLE`; never formal evidence |
| DATA-QUAL-01 | real archive/provider protocol through existing PIT authority | independent real Provider archive satisfies Formal PIT protocol |
| OOS-01 | frozen train/validation/locked-OOS walk-forward protocol | immutable PASSED/FAILED/INCONCLUSIVE OOS evidence |
| COST-01 | A-share execution feasibility, cost and capacity sensitivity | net/capacity-adjusted Alpha remains meaningful under approved assumptions |
| QUAL-01 | consume evidence through existing Model Governance | explicit operator qualification/promotion; never automatic |

## Invariants

- Evidence ceiling is monotone and remains `FREE_DATA_EXPLORATORY / PIT_INCOMPLETE`
  until an independently qualified Provider protocol proves otherwise.
- Every Provider is explicit; no automatic substitution or fallback.
- `decision_frozen_at < outcome_available_at`; corrections never rewrite the
  original decision.
- Research/Shadow never creates Order, Fill, Broker call, or Position mutation.
- Result-affecting policy/configuration is versioned and content-addressed.
- Fatal identity, time, lineage, lease or fence conflicts fail the Tick; ordinary
  evidence insufficiency remains a typed Summary result.

## Rollback and genuine stop conditions

Changes are additive. Disable supplemental acquisition/producer configuration
to return to the existing honest `DATA_INSUFFICIENT` path; immutable artifacts
remain readable. Forward repair publishes a new policy or corrected artifact,
never mutates history.

A missing exact trading window, insufficient consecutive prospective sessions,
unqualified Provider history, unopened locked OOS result, or absent operator
approval is a genuine external Exit-Gate blocker. It blocks evidence promotion,
not truthful engineering or replay work in the current dependency-safe phase.
