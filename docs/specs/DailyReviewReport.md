# DailyReviewReport

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Aggregate daily facts, metrics, failures and proposals  
> **Owner:** Review domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Aggregate daily facts, metrics, failures and proposals.

    ## Owner and authority

    Owner: Review domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `review_date`
- `snapshot_id`
- `data_quality_review`
- `candidate_review`
- `etf_review`
- `theme_review`
- `entry_review`
- `holding_review`
- `exit_review`
- `risk_review`
- `manual_execution_review`
- `failure_attributions`
- `rolling_20d`
- `rolling_60d`
- `codex_proposals`
- `content_hash`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. Facts and hypotheses are separated.
2. Daily report cannot promote or mutate models.

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
