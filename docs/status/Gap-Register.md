# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Current unresolved gap inventory  
> **Baseline:** `main@ab35a32ab857819153b665d5bf72301f7db46ede`  
> **Last Updated:** 2026-08-19  
> **Code Evidence:** `src/market_regime_alpha`, `docs/status/Current-State.md`

Gaps are classified so missing future/external evidence does not block engineering and research that can be completed now.

---

## A. Build or simplify now

These work items do not require waiting for future market sessions or a new external provider.

| Gap | Current problem | Exit condition | Priority |
|---|---|---|---|
| Golden Alpha Proof loop | Many components exist, but the next cycle is not yet governed by one narrow end-to-end proof question | One frozen Strategy/Decision protocol runs Data→Universe→Feature→Ranking→Strategy→Shadow Portfolio→Outcome→Attribution with exact lineage/replay | P0 |
| Transparent quantitative baseline | Existing factor/candidate machinery lacks one canonical simple benchmark for the next Alpha campaign | Frozen baseline reports RankIC, quantiles, Top-K, MFE/MAE, gross/net, turnover and missingness | P0 |
| Candidate coverage / gate diagnosis | Longitudinal evidence showed downstream starvation/all-rejected populations under missing/failing context | Universe→eligibility→ranking→gate counts, reasons, distributions and sensitivity make starvation diagnosable | P0 |
| Factor/context incremental value | Regime/Theme/Capital/Dynamic Pool exist, but current evidence is mixed/negative/not-estimable | Versioned ablation/de-dup/sensitivity accepts or rejects incremental value versus baseline | P0 |
| Candidate / Signal / Forecast responsibility test | Separate artifacts exist, but empirical distinctness is not established | Each layer proves distinct information/policy/consumer value or is simplified/merged | P0/P1 |
| Forecast estimability diagnostics | Forecast fails closed correctly, but `NOT_ESTIMABLE` must direct research instead of threshold relaxation | Diagnostics identify sample/coverage/conditioning/estimator/floor causes for blocked cohorts | P0 |
| Strategy economic translation | Platform can simulate/record actions, but prediction value is not proven as executable net value | Frozen Entry/Holding/Exit/Portfolio protocol reconciles gross→cost→net under applicable A-share constraints | P1 |
| Cost / fillability / capacity research | Existing values remain partly engineering assumptions | Provenance/sensitivity explicit; empirical sources can replace assumptions without silent Strategy identity mutation | P1 |
| Attribution-driven diagnosis | Performance/attribution exists, but next-work selection is not yet centered on layered diagnosis | Data/Universe/Context/Ranking/Signal/Forecast/Entry/Portfolio/Holding/Exit/Cost categories are actionable | P1 |
| Architecture compression | Legacy/compatibility surfaces remain because some replay/qualification consumers exist | Consumer inventory + differential replay permits safe retirement/merge; no parallel writer/runtime | P1 |
| Documentation authority | Former Constitution/static site created duplicate/outdated architecture surfaces | One Canonical Overall Design plus subordinate current/supporting docs | P0 |
| Business observability | Infrastructure metrics are mature; research diagnostics must dominate | Operator can explain no-run/no-candidate/not-estimable/net-negative from one traceable chain | P1 |

---

## B. Engineering can be ready now, but proof requires future evidence

| Gap | Current fact | Evidence required | Priority |
|---|---|---|---|
| Sustained prospective Shadow | Freeze/settle/attestation mechanics exist | Consecutive live-origin trusted-clock decisions and settled outcomes under frozen Model/Strategy versions | P0 |
| Strategy stability | Historical behavior exists; prospective stability does not | Version-scoped future cohorts showing stable ranking/economic behavior and declared failure conditions | P0/P1 |
| Provider/runtime reliability under market windows | Recovery mechanics have historical/local proof | Repeated real decision-window runs with availability, duplicate-call, fence, retry and incident metrics | P1 |
| Model / Strategy drift | Diagnostic infrastructure can be built | Sufficient prospective sample to define/observe drift rather than infer it from fixtures | P1 |
| Operational backup/restore / alert evidence | Mechanics exist locally | Repeated deployed drills meeting declared RPO/RTO and alert expectations | P2 |

Prospective evidence cannot be backfilled after the fact. Start the evidence clock early, even with a baseline model, provided version/evidence labels are truthful.

---

## C. External capability or qualified evidence required

| Gap | Current fact | External exit condition | Priority |
|---|---|---|---|
| Qualified Provider history | Public-provider research data exists but does not satisfy formal source floor | Independently supportable archive/version/revision/availability evidence for required Fact Kinds | P2 |
| Formal PIT evidence | Mechanics exist; qualified source/fact history does not | Complete decision-time-valid facts and qualified source decisions support target/universe claim | P2 |
| Qualified Historical Sample / untouched Locked OOS | Owners/protocols exist; upstream evidence absent | Frozen qualified sample lineage plus first valid untouched OOS consumption under predeclared family | P2 |
| Calibration / formal Strategy qualification | Owners exist; qualified OOS/economic inputs absent | Disjoint calibrated evidence and Strategy economics meet frozen policies | P2 |
| External authenticated identity | RBAC/principal engineering exists; caller identity is not externally authenticated | Trusted external subject binding to durable principals | P3 |
| Broker read/reconciliation/trading | No broker Authority exists by design | Separately approved broker contract/auth/read/reconcile/risk/approval/kill-switch program | P3 / Future |

---

## Evidence-driven routing rules

```text
Candidate count/coverage too small
→ Universe / gate / threshold / ranking diagnostics

Forecast = NOT_ESTIMABLE
→ sample / coverage / conditioning / estimator diagnostics

Gross return negative
→ Factor / Candidate / Target / Horizon research

Gross positive, Net negative
→ Cost / turnover / liquidity / Entry / Portfolio research

Historical positive, Prospective weak
→ leakage / stability / drift / regime / availability diagnosis

Architecture has no real consumer
→ SIMPLIFY / MERGE / RETIRE / DELETE
```

Do not tune a gate, target, horizon or cost assumption merely to turn negative evidence positive. A changed research question creates a new frozen Experiment/Strategy identity.

---

## Explicitly not current blockers

The following are not prerequisites for the Alpha Proof campaign:

- microservices;
- Kafka/event-bus redesign;
- Kubernetes-first deployment;
- generic autonomous agents;
- complex Portfolio optimization;
- automatic broker execution;
- another Authority/Receipt/Qualification framework.

They remain Deferred until a demonstrated requirement exists.