-- Apply after creating the three runtime roles with environment-managed credentials.
-- Expected roles: agent_app, patient_ops_app, clinic_core_app.

GRANT USAGE ON SCHEMA agent_ops TO agent_app;
GRANT USAGE ON SCHEMA patient_ops TO patient_ops_app;
GRANT USAGE ON SCHEMA clinic_core TO clinic_core_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA agent_ops
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agent_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA patient_ops
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO patient_ops_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA clinic_core
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO clinic_core_app;

-- Cross-system direct table access is intentionally absent.
