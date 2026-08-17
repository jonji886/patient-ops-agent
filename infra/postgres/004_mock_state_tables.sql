CREATE TABLE IF NOT EXISTS patient_ops.runtime_state (
  id text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS clinic_core.runtime_state (
  id text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON patient_ops.runtime_state TO patient_ops_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON clinic_core.runtime_state TO clinic_core_app;
