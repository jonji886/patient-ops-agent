"""Agent-owned domain records.

These models intentionally contain no HTTP, database, or LLM dependencies.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from patient_ops_agent.models import AgentRunStatus, ExecutionOwner, WorkflowStep


class CoreBusinessStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    EXECUTING = "EXECUTING"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SideEffectStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_NEEDS_HUMAN = "FAILED_NEEDS_HUMAN"


class ConfirmationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class ManualTaskStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    RETURNED_TO_AGENT = "RETURNED_TO_AGENT"
    CANCELLED = "CANCELLED"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_NEEDS_HUMAN = "FAILED_NEEDS_HUMAN"


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    channel: str
    actor_id: str
    patient_id: str
    created_at: datetime


class ConversationMessage(BaseModel):
    """A task-scoped message retained with the owning Run's durable payload."""

    model_config = ConfigDict(extra="forbid")
    author: Literal["PATIENT", "OPERATOR"]
    text: str
    created_at: datetime


class AgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    conversation_id: str
    patient_id: str
    actor_id: str
    verification_level: str
    verified_at: datetime
    operation_id: Optional[str] = None
    intent: Optional[str] = None
    run_status: AgentRunStatus = AgentRunStatus.ACTIVE
    workflow_step: WorkflowStep = WorkflowStep.INIT
    execution_owner: ExecutionOwner = ExecutionOwner.AGENT
    state_version: int = 0
    service_item_id: Optional[str] = None
    service_item_name: Optional[str] = None
    clinic_id: Optional[str] = None
    doctor_id: Optional[str] = None
    requested_date: Optional[str] = None
    requested_period: Optional[str] = None
    candidate_slot_ids: List[str] = Field(default_factory=list)
    candidate_slots: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_service_items: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_dates: List[Dict[str, Any]] = Field(default_factory=list)
    selected_slot_id: Optional[str] = None
    selected_slot_version: Optional[int] = None
    appointment_id: Optional[str] = None
    appointment_version: Optional[int] = None
    candidate_appointments: List[Dict[str, Any]] = Field(default_factory=list)
    confirmation_id: Optional[str] = None
    core_business_status: CoreBusinessStatus = CoreBusinessStatus.NOT_STARTED
    writeback_status: SideEffectStatus = SideEffectStatus.NOT_REQUIRED
    notification_status: SideEffectStatus = SideEffectStatus.NOT_REQUIRED
    attempt_count: int = 0
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    manual_task_id: Optional[str] = None
    current_reply: Optional[str] = None
    current_reply_author: Literal["AGENT", "OPERATOR"] = "AGENT"
    conversation_messages: List[ConversationMessage] = Field(default_factory=list)
    suggested_replies: List[Dict[str, str]] = Field(default_factory=list)
    action_required: str = "NONE"
    started_at: datetime
    completed_at: Optional[datetime] = None


class ConfirmationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    run_id: str
    patient_id: str
    action_type: str
    target_id: str
    parameters: Dict[str, Any]
    parameter_hash: str
    resource_version: int
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    confirmed_at: Optional[datetime] = None
    expires_at: datetime


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    trace_id: str
    event: str
    node: Optional[str] = None
    tool_name: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ManualTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    run_id: str
    patient_id: str
    reason_code: str
    status: ManualTaskStatus = ManualTaskStatus.OPEN
    assigned_operator_id: Optional[str] = None
    resolution: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class OutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    run_id: str
    operation_id: str
    event_type: str
    payload: Dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempt_count: int = 0
    next_attempt_at: datetime
    created_at: datetime


class ToolExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    run_id: str
    operation_id: Optional[str] = None
    attempt_no: int
    tool_name: str
    masked_input: Dict[str, Any]
    masked_output: Dict[str, Any]
    status: str
    error_code: Optional[str] = None
    started_at: datetime
    completed_at: datetime
