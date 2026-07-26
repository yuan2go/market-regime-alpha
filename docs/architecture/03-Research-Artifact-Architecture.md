# Research Artifact Architecture

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical immutable evidence architecture  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/03-Research-Framework.md, ../constitution/07-Validation-Constitution.md, ../research/Research-Artifact-Identity-V3.md  
> **Code Evidence:** src/market_regime_alpha/research/prr_artifact_*, experiment_identity.py, PIT readers/verifiers

## Artifact classes

```text
Source Artifact
Dataset Artifact
Universe / Eligibility Artifact
Feature Materialization
Target Materialization
Experiment Protocol
Prediction Run
Outcome Materialization
Evaluation Run
Daily Decision Snapshot
Codex Evidence Pack
Promotion Decision
```

## Identity payload

Result-affecting identities bind at minimum:

- source hashes and provider products;
- event/availability/retrieval/decision times;
- calendar and universe identities;
- feature/target/model definitions and materializations;
- code revision and configuration hash;
- cost/execution assumptions;
- sample split/partition identity;
- parent model/experiment lineage.

## Reader rule

A stored JSON/Parquet object is not trusted because it exists. A semantic Reader must reconstruct the identity and invariants from content. Test-only success artifacts must remain distinguishable from research evidence.

## Daily artifact rule

Daily recommendations are append-only and immutable. Corrections create a new artifact linked with `supersedes`; they never mutate what the system saw at the original Decision Time.

## Authority

```text
UNQUALIFIED < EXPLORATORY < REHEARSAL < FORMAL_RESEARCH < SHADOW_EVIDENCE < LIVE_OBSERVED
```

This sequence is not automatic. Each transition requires explicit evidence and governance.
