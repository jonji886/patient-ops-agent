CREATE TABLE IF NOT EXISTS agent_ops.conversations (
  id text PRIMARY KEY, actor_id text NOT NULL, patient_id text NOT NULL,
  created_at timestamptz NOT NULL, payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_ops.agent_runs (
  id text PRIMARY KEY, conversation_id text NOT NULL REFERENCES agent_ops.conversations(id),
  patient_id text NOT NULL, state_version integer NOT NULL,
  started_at timestamptz NOT NULL, payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_runs_conversation_started_idx
  ON agent_ops.agent_runs(conversation_id, started_at DESC);
CREATE TABLE IF NOT EXISTS agent_ops.confirmations (id text PRIMARY KEY, payload jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS agent_ops.manual_tasks (id text PRIMARY KEY, payload jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS agent_ops.outbox_events (id text PRIMARY KEY, payload jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS agent_ops.trace_events (
  seq bigserial PRIMARY KEY, run_id text NOT NULL REFERENCES agent_ops.agent_runs(id), payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_ops.tool_executions (
  id text PRIMARY KEY, run_id text NOT NULL REFERENCES agent_ops.agent_runs(id),
  operation_id text, payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_ops.command_results (key text PRIMARY KEY, payload jsonb NOT NULL);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agent_ops TO agent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA agent_ops TO agent_app;
