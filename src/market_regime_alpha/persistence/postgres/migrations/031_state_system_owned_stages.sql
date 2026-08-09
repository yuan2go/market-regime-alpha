ALTER TABLE state_research_stage_authority
ADD COLUMN stage_status text CHECK (
    stage_status IN ('COMPLETED', 'DATA_INSUFFICIENT')
);
