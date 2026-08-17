#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set agent_password="$AGENT_DB_PASSWORD" \
  --set patient_password="$PATIENT_OPS_DB_PASSWORD" \
  --set clinic_password="$CLINIC_CORE_DB_PASSWORD" <<'SQL'
CREATE ROLE agent_app LOGIN PASSWORD :'agent_password';
CREATE ROLE patient_ops_app LOGIN PASSWORD :'patient_password';
CREATE ROLE clinic_core_app LOGIN PASSWORD :'clinic_password';
SQL

psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --file /migrations/001_create_schemas.sql
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --file /migrations/002_grants.sql
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --file /migrations/003_agent_ops_tables.sql
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --file /migrations/004_mock_state_tables.sql
