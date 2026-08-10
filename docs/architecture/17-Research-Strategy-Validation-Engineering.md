# Research and Strategy Validation Engineering

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Engineering architecture below Formal PIT/OOS and Production Governance
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Related Documents:** 16-Phase-A-Correctness-and-Research-Shadow-Operations.md, ../superpowers/specs/2026-08-10-research-strategy-validation-engineering-design.md
> **Code Evidence:** `application/research_validation/**`, `application/strategy_shadow/**`, PostgreSQL migrations 043–045

## Boundary

The implementation adds the validation machines that consume existing owner
Artifacts. It does not create a second Canonical Runtime, State authority,
Outcome authority or Model Governance path.

```text
Canonical Dataset / Feature Bundle / State / Pool / Candidate / Signal / Forecast
→ lineage-preserving Research Panel Enrichment
→ exploratory Ablation and Liquidity/Capacity
→ Historical Sample Registry and independent Calibration
→ locked Train / Validation / Walk-forward / OOS Evaluation
→ Entry Research and Qualification
→ Strategy Shadow Entry / Fill / Position / Holding / Exit / Outcome
→ unified Production Admission projection
```

Every current route remains below trading authority. Shadow Entry, Fill and
Position are named, persisted research objects and never call the real Order,
Fill, Position or Broker repositories.

## Factor and evaluation authority

`factor_extraction.py` copies values from verified canonical owners. It records
raw numeric/text exposure, missingness, gate state, availability and exact
source identity. Normalization and contribution remain empty unless an owner
Artifact supplied them. A missing canonical family becomes an explicit missing
exposure; it is not recomputed. Extraction is bounded by the frozen Shadow
DecisionTime and verifies Dataset, Feature Bundle, Candidate and Signal
lineage. `research-shadow build-enriched-evaluation` publishes both the Panel
and its immutable PostgreSQL-recorded factor sidecar.

The Ablation runtime supports full, family deletion, price/volume controls,
static/dynamic controls and arbitrary factor deletion. IC, Rank IC, Top-K,
spread, hit rate, return, MFE/MAE, turnover, drawdown, overlap and incremental
lift are exploratory outputs only.

Liquidity/Capacity separates observed ADV/amount/turnover/status from assumed
or independently calibrated participation, impact and slippage parameters.

## Sample, calibration and Formal OOS gates

Historical path samples bind Target, Outcome, PIT lineage and availability.
Qualification is monotonic across `UNQUALIFIED`, `PIT_ELIGIBLE`,
`OOS_ELIGIBLE` and `QUALIFIED`; current construction starts at `UNQUALIFIED`
and never derives a sample from the current Signal. PostgreSQL stores each
append-only qualification state, reconstructs the latest Dataset through its
Reader/replay path and exposes only samples strictly available before the
forecast DecisionTime.

Calibration supports Platt/logistic, isotonic and binning with disjoint Fit,
Validation and OOS identities plus Brier, Log Loss, reliability, ECE and
coverage. Fitting produces `calibrated=false`; only separate OOS and explicit
Governance evidence can perform the qualification transition.

Formal Evaluation locks Train, Validation and Locked OOS windows, supports
walk-forward folds, purges overlapping labels, derives embargo from the
existing Outcome Target Protocol, bootstraps confidence intervals, corrects
multiple testing and produces partition-, fold- and sensitivity-specific
regime/liquidity/market-cap/theme slices. Formal OOS requires an existing
satisfied `FormalPITEvidenceArtifact` whose selected facts use PostgreSQL clock
authority, whose availability predates evaluation, whose locked protocol and
Dataset lineage exactly match the evaluation Panel, and whose Locked OOS
partition contains observations. Fixture clocks or an unbound PIT reference
emit engineering evidence and `formal_oos=false`.

## Strategy Shadow and Production Admission

Entry Research models Candidate-only, Candidate+Signal, Candidate+Forecast and
Candidate+Intraday variants. Fit/evaluation cannot unlock Canonical Entry.
Qualification requires Formal OOS, qualified Calibration and explicit
typed evidence from the existing Model Governance decision and its exact
evidence set. A generic validation reference cannot grant qualification.

Strategy Shadow attaches to an existing Continuous Runtime Run/Tick and frozen
Research Shadow Decision. Its CAS journal supports schedule, resume/recovery,
replay, settlement, incident/drift events and daily reports. The controlled
event sequence is Entry, Fill, Position, Holding, Exit and Strategy Outcome;
each event atomically persists its typed immutable Shadow Artifact, and replay
reconstructs the session from the append-only PostgreSQL event journal.
Holding/Exit rules cover fixed time, reversal/deterioration,
trailing/protection and multi-horizon assessment. Sustained proof requires a
separate locked protocol, prospective attestations and typed evidence from the
existing Model Governance authority.

Production Admission assesses Formal PIT, Formal OOS, economic validation,
Calibration, cost/capacity, Entry, Holding/Exit, sustained Strategy Shadow,
operator approval, Auth/RBAC and Broker readiness. Missing any floor produces
`BLOCKED`. Even eleven satisfied, correctly typed floor references produce at
most `ELIGIBLE_FOR_OPERATOR_REVIEW` unless an existing qualified
`PRODUCTION_DECISION` Model Governance decision explicitly carries Production
authorization and operator approval. No generic repository writer can persist
qualification or Production authorization.

## Correctness boundary fixes

Continuous `run-due` now records a durable clock/origin Artifact for its actual
Run/Tick. Prospective Attestation V2 reads this PostgreSQL authority; settlement
CLI clock/origin fields are compatibility inputs and cannot promote evidence.
Missing runtime evidence is durably recorded as `UNKNOWN` and fails the checks.

Operational Universe V2 binds the actual `DailyUniversePolicy` ID, hash and
version. StateSeries consumes that exact identity. V1 Readers and the legacy
metadata-derived fallback remain only for historical Artifacts.

## Current evidence ceiling

```text
REAL_FORMAL_PIT = false
FORMAL_OOS = false
ALPHA_VALIDATED = false
CALIBRATED = false
ENTRY_QUALIFIED = false
HOLDING_EXIT_VALIDATED = false
STRATEGY_SHADOW_PROVEN = false
PRODUCTION_AUTHORIZED = false
```
