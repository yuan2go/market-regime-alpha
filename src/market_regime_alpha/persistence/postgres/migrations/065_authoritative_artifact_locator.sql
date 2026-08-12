-- Controlled package recovery must resolve one PostgreSQL locator against the
-- configured global Artifact root.  Historical un-namespaced rows remain
-- immutable but are deliberately not guessed or discovered by directory scan.

ALTER TABLE longitudinal_operational_index
ADD CONSTRAINT longitudinal_operational_artifact_root_locator_check
CHECK (package_locator LIKE 'artifact-root-v1/%') NOT VALID;
