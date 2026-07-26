# CapitalContextSnapshot

    > **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification: Market liquidity and capital-flow proxy context  
> **Owner:** Capital Context domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY unless stated below

    ## Purpose

    Market liquidity and capital-flow proxy context.

    ## Owner and authority

    Owner: Capital Context domain. This object is the authoritative record for its bounded purpose only. It does not assume responsibilities owned by adjacent domains.

    ## Inputs

    Identified upstream artifacts, timezone-aware semantic times, exact model/config/code identities and explicit data/evidence status.

    ## Schema V1

    - `decision_time`
- `market_turnover`
- `turnover_change`
- `liquidity_breadth`
- `financing_proxies`
- `etf_flow_proxies`
- `large_trade_proxies`
- `source_manifest`
- `limitations`
- `content_hash`

    ## Identity and versioning

    Result-affecting fields enter the canonical content hash. Schema or semantic changes create a new version. Corrections use `supersedes` and preserve the original.

    ## Time and PIT rules

    All inputs must be defensibly available by the object's Decision/As-Of Time. Future outcomes are stored only after observation and never fed back into original predictions.

    ## Invariants

    1. Every proxy declares its source and semantic limitation.
2. Level-1 snapshots are not called Level-2 order flow.

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
