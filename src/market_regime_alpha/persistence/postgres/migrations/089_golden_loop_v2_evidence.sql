-- Admit the immutable Golden Loop V2 session evaluation and methodology
-- assessment into the existing Historical Corpus/Evidence owners. Existing
-- V1 rows are append-only and are neither rewritten nor deleted.

ALTER TABLE historical_corpus_session_component
    DROP CONSTRAINT historical_corpus_session_component_component_kind_check,
    ADD CONSTRAINT historical_corpus_session_component_component_kind_check
    CHECK (component_kind IN (
        'FEATURE', 'MARKET_REGIME', 'ETF', 'THEME', 'CAPITAL', 'DYNAMIC_POOL',
        'CANDIDATE', 'SIGNAL', 'FORECAST', 'STRATEGY', 'PORTFOLIO', 'OUTCOME',
        'RESEARCH_PANEL', 'RESEARCH_EVALUATION'
    ));

ALTER TABLE historical_research_evidence
    DROP CONSTRAINT historical_research_evidence_evidence_kind_check,
    ADD CONSTRAINT historical_research_evidence_evidence_kind_check
    CHECK (evidence_kind IN (
        'CORPUS_SUMMARY', 'ALPHA_ABLATION', 'STRATEGY_ECONOMICS',
        'PORTFOLIO_PERFORMANCE', 'EXPLORATORY_MODEL',
        'METHODOLOGY_ASSESSMENT'
    ));

COMMENT ON COLUMN historical_corpus_session_component.component_kind IS
'RESEARCH_EVALUATION binds V2 scores and boundary diagnostics to canonical cycle, portfolio and outcome owners; it is not a second Runtime or Portfolio authority.';

COMMENT ON COLUMN historical_research_evidence.evidence_kind IS
'METHODOLOGY_ASSESSMENT records immutable invalidation/supersession lineage without mutating historical Evidence.';
