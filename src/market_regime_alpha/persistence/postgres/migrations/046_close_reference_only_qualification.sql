DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM research_validation_artifact
        WHERE qualified
           OR production_authorized
           OR evidence_authority NOT IN (
               'EXPLORATORY', 'ENGINEERING_ONLY', 'BLOCKED'
           )
    ) THEN
        RAISE EXCEPTION
            'reference-only Research Validation authority rows must be reconciled before migration 046';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM historical_path_sample_record
        WHERE qualification <> 'UNQUALIFIED'
    ) THEN
        RAISE EXCEPTION
            'Historical Sample qualification rows require an owner-resolution migration';
    END IF;
END
$$;

ALTER TABLE research_validation_artifact
    ADD CONSTRAINT research_validation_artifact_no_qualification_without_owner
    CHECK (
        NOT qualified
        AND NOT production_authorized
        AND evidence_authority IN (
            'EXPLORATORY', 'ENGINEERING_ONLY', 'BLOCKED'
        )
    );

ALTER TABLE historical_path_sample_record
    ADD CONSTRAINT historical_path_sample_record_unqualified_until_owner_resolved
    CHECK (qualification = 'UNQUALIFIED');
