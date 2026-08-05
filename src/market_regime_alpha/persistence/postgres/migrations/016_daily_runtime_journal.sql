CREATE TABLE daily_runs (
    run_request_id text PRIMARY KEY,
    request_json text NOT NULL CHECK (request_json IS JSON OBJECT),
    daily_run_id text UNIQUE,
    daily_run_identity_json text CHECK (
        daily_run_identity_json IS NULL OR daily_run_identity_json IS JSON OBJECT
    ),
    status text NOT NULL,
    resume_status text,
    failure_reason text,
    version bigint NOT NULL CHECK (version >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE acquisition_stage_receipts (
    run_request_id text NOT NULL,
    stage text NOT NULL,
    receipt_json text NOT NULL CHECK (receipt_json IS JSON OBJECT),
    PRIMARY KEY (run_request_id, stage),
    FOREIGN KEY (run_request_id) REFERENCES daily_runs(run_request_id)
);

CREATE TABLE stage_receipts (
    run_request_id text NOT NULL,
    stage text NOT NULL,
    receipt_json text NOT NULL CHECK (receipt_json IS JSON OBJECT),
    content_hash text NOT NULL,
    PRIMARY KEY (run_request_id, stage),
    FOREIGN KEY (run_request_id) REFERENCES daily_runs(run_request_id)
);
