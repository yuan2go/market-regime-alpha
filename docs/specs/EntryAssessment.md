# EntryAssessment

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Assess whether and how to open a Candidate  
> **Owner:** Entry domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Assess whether and how to open a Candidate.

    ## Owner and authority

    Owner: Entry domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `snapshot_id`
- `candidate_prediction_id`
- `action`
- `entry_zone`
- `maximum_acceptable_price`
- `invalidation_condition`
- `reference_stop`
- `expected_mfe`
- `expected_mae`
- `risk_reward`
- `entry_reasons`
- `rejection_reasons`
- `model_identity`
- `expires_at`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. Actions are ENTER/WAIT_PULLBACK/WAIT_CONFIRMATION/REJECT/NO_ACTION.
2. Entry Path targets cannot be used before their availability.
3. Risk-reward is an estimate, not guaranteed return.

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
