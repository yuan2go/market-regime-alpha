# CandidateRecommendation

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Structured presentation of a CandidatePrediction  
> **Owner:** Candidate/Application domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Structured presentation of a CandidatePrediction.

    ## Owner and authority

    Owner: Candidate/Application domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `snapshot_id`
- `symbol`
- `instrument_type`
- `rank`
- `score`
- `score_components`
- `selection_reasons`
- `risk_reasons`
- `industry`
- `themes`
- `related_etfs`
- `expected_horizon`
- `target_identity`
- `model_identity`
- `data_quality`
- `evidence_level`
- `expires_at`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. Candidate rank is not Entry or trade action.
2. Reasons derive from structured evidence.
3. Complete prediction ledger remains authoritative.

    ## Validation and failure behavior

    Validate required references, type/range constraints, identity compatibility, freshness, population coverage and authority ceiling. Missing mandatory evidence fails closed with an explicit status; it never fabricates a default value.

    ## Example status

    ```text
    AVAILABLE | NOT_YET_OBSERVED | INSUFFICIENT_EVIDENCE | DATA_BLOCKED | INVALID
    ```

    ## Non-goals

    No automatic order, no silent data promotion, no mutable overwrite, no Alpha or probability claim without evidence.

    ## Migration

    Phase D introduces this canonical contract. Legacy fields may be exposed through an adapter only after characterization tests prove semantic compatibility.
