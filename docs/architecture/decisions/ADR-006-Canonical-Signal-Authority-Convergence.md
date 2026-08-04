# ADR-006 — Canonical Signal Authority Convergence

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Accepted architecture decision for canonical Signal production
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../14-Canonical-Signal-Authority-and-Operational-Feature-Handoff.md, ../13-Canonical-Market-Data-and-Feature-Spine.md
> **Code Evidence:** `signals/{candidate_view,input_v3,policies,decimal_model,v3}.py`; `market_data/minute_source.py`; `features/{materialization_run,encoding_v2}.py`

## Context

The prior Feature Spine required Bundle symbols to equal CandidateSet symbols,
while Candidate Discovery logically follows Feature production. Signal Mapping
declared five required factors but configured a minimum of one, daily freshness
used elapsed wall-clock seconds, and V2 converted Decimal inputs to float before
calling the historical Signal engine. A missing Feature Bundle could also
produce a new empty-factor V1 artifact.

Tencent minute data existed only as an overwriteable DuckDB cache, volume lots
were not governed before VWAP, Feature resume had no operational meaning, and
the JSON package repeated enough lineage to make a 100-symbol package unsuitable
for sustained Shadow operation.

## Decision

1. Materialize Features over the complete controlled Universe before Candidate
   selection. Candidate Feature View is a reference projection, not a new data
   authority.
2. Produce only Signal V3 in the canonical runtime. Keep V1/V2 Readers and replay
   unchanged for historical compatibility.
3. Use a Decimal-only `CanonicalSignalModelV2` with an explicit requirement
   policy. The canonical five-factor configuration requires all factors.
4. Evaluate daily freshness by trading-session distance and intraday freshness
   by same-session plus elapsed seconds, always binding the Trading Calendar.
5. Archive exact Tencent response bytes before normalization; the mutable cache
   never becomes canonical authority. Preserve failed attempts and reject
   cumulative conflicts.
6. Normalize volume to shares through a versioned asset rule before VWAP.
7. Replace `resume: bool` with explicit execution modes backed by an independent
   recoverable SQLite Run authority.
8. Make V2 columnar/compressed encoding the production default while preserving
   logical hashes and all V1 Readers/replay.
9. Recompute the complete Market Data → Feature → Candidate View → Signal chain
   in durable replay.
10. Retain unavailable PathForecast sample authority and Entry blocking.

## Consequences

- Candidate Discovery no longer creates an orchestration cycle.
- Signal missingness, denominator, confidence, overheat and freshness semantics
  are versioned and deterministic.
- Physical storage can change without rewriting semantic Artifact identity.
- The public Tencent source remains `EXPLORATORY`; it does not establish formal
  PIT, Alpha, Shadow readiness or trading authority.
- Existing V1/V2 artifacts remain replayable, but normal canonical lifecycle
  execution cannot create new ones.
- Later partial-factor models require a new model identity and H9 evidence.
- H7, H8, H9, Broker and automatic execution remain separate work packages.

## Rejected alternatives

- Candidate-only Feature production: retains the orchestration cycle.
- Treating DuckDB cache rows as source artifacts: permits overwrite and loses
  exact retrieval evidence.
- Clamping negative cumulative deltas to zero: hides source conflicts.
- Keeping the float engine behind a V3 wrapper: breaks Decimal determinism.
- Reusing wall-clock freshness for daily bars: mishandles weekends and holidays.
- Hashing Parquet bytes as model semantics: couples physical encoding to model
  identity and breaks historical replay.
