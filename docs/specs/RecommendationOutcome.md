# RecommendationOutcome

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Match a frozen prediction/proposal with realized outcomes  
> **Owner:** Review domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Match a frozen prediction/proposal with realized outcomes.

    ## Owner and authority

    Owner: Review domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `prediction_id`
- `proposal_id`
- `target_identity`
- `outcome_status`
- `realized_value`
- `benchmark_value`
- `net_value`
- `mfe`
- `mae`
- `up_first`
- `down_first`
- `observed_at`
- `source_dataset_identity`
- `execution_simulation`
- `manual_trade_link`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. Unavailable outcomes remain unresolved.
2. No fallback from exact 10:30 to close.
3. Theory, simulation and actual results remain separate.

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
