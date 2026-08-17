import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:15173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } }],
  webServer: [
    {
      command: "sh -c 'E2E_DB_DIR=$(mktemp -d /tmp/patient-ops-web-e2e.XXXXXX); export PYTHONPATH=src LLM_PROVIDER=fake AGENT_DATABASE_URL=sqlite:///$E2E_DB_DIR/agent.db PATIENT_OPS_DATABASE_URL=sqlite:///$E2E_DB_DIR/patient.db CLINIC_CORE_DATABASE_URL=sqlite:///$E2E_DB_DIR/clinic.db; exec python3 -m uvicorn patient_ops_agent.main:app --host 127.0.0.1 --port 18000'",
      cwd: "..",
      url: "http://127.0.0.1:18000/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "VITE_PORT=15173 VITE_API_TARGET=http://127.0.0.1:18000 npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
