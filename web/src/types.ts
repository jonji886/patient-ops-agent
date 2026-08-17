export type RunStatus =
  | "ACTIVE"
  | "WAITING_PATIENT"
  | "RECONCILING"
  | "WAITING_HUMAN"
  | "COMPLETED"
  | "COMPLETED_WITH_PENDING_SIDE_EFFECTS"
  | "FAILED"
  | "CANCELLED_BY_PATIENT";

export type ActionRequired =
  | "NONE"
  | "SERVICE_SELECTION"
  | "DATE_SELECTION"
  | "SLOT_SELECTION"
  | "APPOINTMENT_SELECTION"
  | "CONFIRMATION"
  | "HUMAN";

export interface Slot {
  id: string;
  clinic_id: string;
  service_item_id: string;
  doctor_id: string;
  start_at: string;
  end_at: string;
  status: string;
  version: number;
}

export interface Appointment {
  id: string;
  patient_id: string;
  clinic_id: string;
  service_item_id: string;
  doctor_id: string;
  slot_id: string;
  status: string;
  version: number;
  start_at?: string | null;
  end_at?: string | null;
  clinic_name?: string | null;
  service_item_name?: string | null;
  doctor_name?: string | null;
}

export interface Run {
  run_id: string;
  conversation_id: string;
  operation_id: string | null;
  intent: string | null;
  run_status: RunStatus;
  workflow_step: string;
  execution_owner: "AGENT" | "OPERATOR";
  state_version: number;
  current_reply: string | null;
  service_item_name: string | null;
  requested_date: string | null;
  current_reply_author: "AGENT" | "OPERATOR";
  suggested_replies: SuggestedReply[];
  candidate_service_items: ServiceOption[];
  candidate_dates: AvailableDate[];
  action_required: ActionRequired | null;
  selected_slot_id: string | null;
  appointment_id: string | null;
  confirmation_id: string | null;
  core_business_status: string;
  writeback_status: string;
  notification_status: string;
  manual_task_id: string | null;
  candidate_slots: Slot[];
  candidate_appointments: Appointment[];
  attempt_count: number;
  last_error_code: string | null;
  masked_patient_id?: string;
}

export interface ServiceOption {
  id: string;
  name: string;
  duration_minutes: number;
}

export interface AvailableDate {
  date: string;
  available_slot_count: number;
}

export interface SuggestedReply {
  id: string;
  label: string;
  message: string;
  mode: "FILL_COMPOSER";
}

export interface TraceEvent {
  timestamp: string;
  trace_id: string;
  event: string;
  node: string | null;
  tool_name: string | null;
  status: string | null;
  duration_ms: number | null;
  details: Record<string, unknown>;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
  display_name: string;
  actor_role: ActorRole;
}

export type ActorRole = "PATIENT" | "OPERATOR" | "ADMIN";

export interface DemoAccount {
  username: string;
  display_name: string;
  actor_role: ActorRole;
}

export interface ManualTask {
  task_id: string;
  run_id: string;
  reason_code: string;
  status: "OPEN" | "ASSIGNED" | "RESOLVED" | "RETURNED_TO_AGENT" | "CANCELLED";
  assigned_operator_id: string | null;
  resolution: string | null;
}

export interface OperatorTaskContext {
  task: ManualTask;
  run: Run;
  messages: ConversationMessage[];
  trace: TraceEvent[];
}

export interface ConversationMessage {
  author: "PATIENT" | "OPERATOR";
  text: string;
  created_at: string;
}

export interface AdminRunSummary {
  run_id: string;
  masked_patient_id: string;
  intent: string | null;
  run_status: RunStatus;
  workflow_step: string;
  execution_owner: "AGENT" | "OPERATOR";
  manual_task_id: string | null;
  last_error_code: string | null;
  started_at: string;
}

export interface AdminAuditEvent extends TraceEvent {
  run_id: string;
  masked_patient_id: string;
}

export interface AdminMetricBucket {
  key: string;
  count: number;
}

export interface AdminDailyTrend {
  date: string;
  total_runs: number;
  successful_appointments: number;
  waiting_human: number;
}

export interface AdminActionItem {
  kind: "HUMAN_HANDOFF" | "FAILED_RUN" | "PENDING_SIDE_EFFECT" | "SECURITY_INCIDENT" | "SYSTEM_HEALTHY";
  severity: "success" | "warning" | "danger";
  count: number;
  run_ids: string[];
}

export interface AdminDashboard {
  generated_at: string;
  metrics: {
    total_runs: number;
    successful_appointments: number;
    appointment_completion_rate: number | null;
    waiting_patient: number;
    waiting_human: number;
    pending_side_effects: number;
    failed_runs: number;
    security_incidents: number;
  };
  status_distribution: AdminMetricBucket[];
  intent_distribution: AdminMetricBucket[];
  funnel: AdminMetricBucket[];
  daily_trend: AdminDailyTrend[];
  error_distribution: AdminMetricBucket[];
  action_items: AdminActionItem[];
}

export interface ConversationResponse {
  conversation_id: string;
  channel: string;
  created_at: string;
}

export interface MessageResponse {
  run_id: string;
  accepted: boolean;
  run: Run;
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
}
