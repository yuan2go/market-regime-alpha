# ADR-003 — Platform V2 Research Artifact Boundary

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Accepted architecture decision for Platform V2 research contracts and evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** README.md, ../09-Platform-Architecture-V2.md, ../../roadmap/work-packages/WP-PAV2-Platform-Architecture-V2-and-Research-Layer-MVP.md
> **Code Evidence:** `feat/platform-architecture-v2-research-layer@64cacd2`

## Decision status

`ACCEPTED` on 2026-07-30.

## Context

The repository already has authoritative evidence, Universe, Feature,
PredictionRun and daily-decision identities. It also has several research
programs whose dictionaries and reports were designed for a narrower
hypothesis. Moving those structures directly into a new platform flow would
either make exploratory fields canonical by accident or create parallel
versions of existing domain objects.

The historical `daily_research` V1 Artifact and current Phase D Artifact are
separate compatibility identities. Neither is a safe container for a new
Market → Theme → Capital → Candidate research aggregate.

## Decision

1. New Platform V2 Artifacts use `ArtifactEnvelope`, with strict schema,
   content hash, Decision Time, configuration, input lineage, evidence
   authority and non-inflatable research/trading authority.
2. Existing SourceManifest, Universe, Eligibility, Decision Price,
   PredictionRun, model IDs and Feature IDs are referenced rather than
   recreated.
3. MR2A enters through an Adapter into `MarketRegimeSnapshot`; its raw result
   dictionaries do not become a domain contract.
4. B0/B1 enter Candidate Discovery through an Adapter as baseline
   percentiles. Their PredictionRuns, scores and ranks remain unchanged.
5. Research Layer publication uses a new exact-file-set schema and its own
   versioned Reader registry.
6. `DailyLoopRunner` remains unchanged. Offline research orchestration belongs
   to `PlatformResearchRunner`.
7. Signal, Forecast, Decision, Position, Execution, Exit and Evaluation
   ownership seams may be contracted, but this work package implements model
   behavior only for the Research Layer.

## Consequences

Positive:

- every Research output has deterministic configuration and evidence lineage;
- Theme and Capital gates cannot be silently bypassed by legacy scores;
- model assumptions remain distinguishable from observed facts;
- replay recomputes semantic output instead of checking files alone;
- historical Readers and daily runtime identities remain untouched.

Costs and limitations:

- the initial Theme and Capital models are unvalidated assumptions;
- the Research input archive must provide typed theme and symbol observations;
- no LIVE Provider currently materializes a complete ResearchInputBundle;
- a separate future orchestrator is required before this layer joins the
  daily operational path.

## Rejected alternatives

### Add the new snapshots to DailyLoopRunner

Rejected because the Runner already owns source recovery, quality, Universe,
Feature, Prediction, decision publication and settlement.

### Treat B0/B1 as the complete CandidateSet

Rejected because their established responsibility is ranking a frozen
Candidate population, without Theme or Capital semantics.

### Reuse Daily Decision or daily_research V1 packaging

Rejected because it would alter or overload frozen schema identity and Reader
semantics.

### Infer Capital Evolution from future returns

Rejected as target leakage. States must use only observations available by
Decision Time.

## Invariants

- no model score becomes a probability without calibration;
- no CandidateSet becomes a buy list;
- no new contract emits a live order;
- no future outcome enters same-day state inference;
- no successful Artifact raises EXPLORATORY authority;
- no old Artifact schema or identity changes silently.
