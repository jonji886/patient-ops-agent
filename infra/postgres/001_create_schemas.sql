-- Apply with a migration role. This script intentionally does not contain passwords.
-- Runtime roles must be created by the deployment environment or a secret-aware setup step.

CREATE SCHEMA IF NOT EXISTS agent_ops;
CREATE SCHEMA IF NOT EXISTS patient_ops;
CREATE SCHEMA IF NOT EXISTS clinic_core;

REVOKE ALL ON SCHEMA agent_ops FROM PUBLIC;
REVOKE ALL ON SCHEMA patient_ops FROM PUBLIC;
REVOKE ALL ON SCHEMA clinic_core FROM PUBLIC;

COMMENT ON SCHEMA agent_ops IS 'Agent Run, workflow, audit, outbox and manual task data';
COMMENT ON SCHEMA patient_ops IS 'Synthetic Patient Ops Platform data';
COMMENT ON SCHEMA clinic_core IS 'Synthetic Clinic Core data';
