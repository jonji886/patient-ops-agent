import type {
  AdminAuditEvent,
  AdminDashboard,
  AdminRunSummary,
  ApiErrorPayload,
  ConversationResponse,
  DemoScenarioId,
  DemoScenarioStatus,
  DemoAccount,
  LoginResponse,
  ManualTask,
  MessageResponse,
  OperatorTaskContext,
  Run,
  TraceEvent,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code?: string,
  ) {
    super(message);
  }
}

function requestId(): string {
  return crypto.randomUUID();
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  stateVersion?: number,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", requestId());
  if (options.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (stateVersion !== undefined) headers.set("X-State-Version", String(stateVersion));

  const response = await fetch(path, { ...options, headers });
  const payload = (await response.json().catch(() => null)) as T | ApiErrorPayload | null;
  if (!response.ok) {
    const error = payload as ApiErrorPayload | null;
    throw new ApiError(error?.error?.message ?? "请求未能完成，请稍后重试。", error?.error?.code);
  }
  return payload as T;
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function listDemoAccounts(): Promise<DemoAccount[]> {
  return request<DemoAccount[]>("/api/v1/auth/demo-accounts");
}

export function createConversation(token: string): Promise<ConversationResponse> {
  return request<ConversationResponse>(
    "/api/v1/conversations",
    { method: "POST", body: JSON.stringify({ channel: "web_simulator" }) },
    token,
  );
}

export function sendMessage(token: string, conversationId: string, message: string): Promise<MessageResponse> {
  return request<MessageResponse>(
    `/api/v1/conversations/${conversationId}/messages`,
    { method: "POST", body: JSON.stringify({ message }) },
    token,
  );
}

export function selectSlot(token: string, run: Run, slotId: string, slotVersion: number): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/slot-selection`,
    { method: "POST", body: JSON.stringify({ slot_id: slotId, slot_version: slotVersion }) },
    token,
    run.state_version,
  );
}

export function selectServiceItem(token: string, run: Run, serviceItemId: string): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/service-selection`,
    { method: "POST", body: JSON.stringify({ service_item_id: serviceItemId }) },
    token,
    run.state_version,
  );
}

export function selectAvailableDate(token: string, run: Run, date: string): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/date-selection`,
    { method: "POST", body: JSON.stringify({ date }) },
    token,
    run.state_version,
  );
}

export function selectAppointment(token: string, run: Run, appointmentId: string, appointmentVersion: number): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/appointment-selection`,
    { method: "POST", body: JSON.stringify({ appointment_id: appointmentId, appointment_version: appointmentVersion }) },
    token,
    run.state_version,
  );
}

export function confirm(token: string, run: Run): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/confirmations`,
    { method: "POST", body: JSON.stringify({ confirmation_id: run.confirmation_id }) },
    token,
    run.state_version,
  );
}

export function cancelRun(token: string, run: Run): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/cancel`,
    { method: "POST" },
    token,
    run.state_version,
  );
}

export function requestHandoff(token: string, run: Run): Promise<Run> {
  return request<Run>(
    `/api/v1/runs/${run.run_id}/handoff`,
    { method: "POST", body: JSON.stringify({ reason_code: "PATIENT_REQUESTED" }) },
    token,
  );
}

export function getRun(token: string, runId: string): Promise<Run> {
  return request<Run>(`/api/v1/runs/${runId}`, {}, token);
}

export function getTrace(token: string, runId: string): Promise<TraceEvent[]> {
  return request<TraceEvent[]>(`/api/v1/runs/${runId}/trace`, {}, token);
}

export function getDemoScenarioStatus(token: string): Promise<DemoScenarioStatus> {
  return request<DemoScenarioStatus>("/api/v1/demo/scenario", {}, token);
}

export function activateDemoScenario(token: string, scenario: DemoScenarioId): Promise<DemoScenarioStatus> {
  return request<DemoScenarioStatus>("/api/v1/demo/scenario", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  }, token);
}

export function listManualTasks(token: string, status?: ManualTask["status"]): Promise<ManualTask[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<ManualTask[]>(`/api/v1/manual-tasks${query}`, {}, token);
}

export function getManualTaskContext(token: string, taskId: string): Promise<OperatorTaskContext> {
  return request<OperatorTaskContext>(`/api/v1/manual-tasks/${taskId}/context`, {}, token);
}

export function assignManualTask(token: string, taskId: string): Promise<ManualTask> {
  return request<ManualTask>(`/api/v1/manual-tasks/${taskId}/assign`, { method: "POST" }, token);
}

export function resolveManualTask(token: string, taskId: string, resolution: string): Promise<ManualTask> {
  return request<ManualTask>(`/api/v1/manual-tasks/${taskId}/resolve`, {
    method: "POST", body: JSON.stringify({ resolution }),
  }, token);
}

export function sendOperatorReply(token: string, taskId: string, message: string): Promise<Run> {
  return request<Run>(`/api/v1/manual-tasks/${taskId}/messages`, {
    method: "POST", body: JSON.stringify({ message }),
  }, token);
}

export function returnManualTaskToAgent(token: string, taskId: string): Promise<Run> {
  return request<Run>(`/api/v1/manual-tasks/${taskId}/return-to-agent`, { method: "POST" }, token);
}

export function listAdminRuns(token: string): Promise<AdminRunSummary[]> {
  return request<AdminRunSummary[]>("/api/v1/admin/runs", {}, token);
}

export function getAdminDashboard(token: string): Promise<AdminDashboard> {
  return request<AdminDashboard>("/api/v1/admin/dashboard", {}, token);
}

export function getAdminRun(token: string, runId: string): Promise<Run> {
  return request<Run>(`/api/v1/admin/runs/${runId}`, {}, token);
}

export function getAdminTrace(token: string, runId: string): Promise<TraceEvent[]> {
  return request<TraceEvent[]>(`/api/v1/admin/runs/${runId}/trace`, {}, token);
}

export function getAdminAudit(token: string): Promise<AdminAuditEvent[]> {
  return request<AdminAuditEvent[]>("/api/v1/admin/audit", {}, token);
}
