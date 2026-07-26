# DailyResearchSnapshot

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Root immutable snapshot for one Decision Time  
> **Owner:** Daily Decision domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Root immutable snapshot for one Decision Time.

    ## Owner and authority

    Owner: Daily Decision domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `decision_date`
- `decision_time`
- `timezone`
- `calendar_identity`
- `universe_identity`
- `eligibility_policy`
- `data_source_manifest`
- `data_freshness`
- `market_context_identity`
- `etf_context_identity`
- `theme_context_identity`
- `capital_context_identity`
- `feature_set_identity`
- `candidate_model_identities`
- `entry_model_identities`
- `exit_model_identities`
- `risk_policy_identity`
- `position_snapshot_identity`
- `experiment_identity`
- `content_hash`
- `created_at`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. All referenced artifacts exist and are available no later than decision_time.
2. Snapshot is append-only and content-addressed.
3. Blocked inputs produce an explicit blocked disposition.

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
