-- Bind V2 Forecast semantics to Strategy family without mutating V1 identities.

ALTER TABLE strategy_contract
    ADD CONSTRAINT strategy_contract_forecast_semantics_check CHECK (
        (payload_json->>'schema_version' = 'strategy-contract/v1'
            AND NOT (payload_json ? 'forecast_requirement')
            AND family IN ('OVERNIGHT', 'SWING_STATE'))
        OR
        (payload_json->>'schema_version' = 'strategy-contract/v2'
            AND payload_json->>'forecast_requirement' =
                CASE
                    WHEN family = 'CONDITIONAL_PREDICTION'
                    THEN 'FORECAST_REQUIRED'
                    ELSE 'FORECAST_NOT_REQUIRED'
                END)
    );

COMMENT ON CONSTRAINT strategy_contract_forecast_semantics_check
ON strategy_contract IS
'V1 incumbent identities remain unchanged; V2 Conditional Prediction requires Forecast and every other V2 family explicitly does not.';
