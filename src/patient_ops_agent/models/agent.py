"""Agent Run projection models exposed to the API and runtime panel."""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentRunStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_PATIENT = "WAITING_PATIENT"
    RECONCILING = "RECONCILING"
    WAITING_HUMAN = "WAITING_HUMAN"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_PENDING_SIDE_EFFECTS = "COMPLETED_WITH_PENDING_SIDE_EFFECTS"
    FAILED = "FAILED"
    CANCELLED_BY_PATIENT = "CANCELLED_BY_PATIENT"


class ExecutionOwner(str, Enum):
    AGENT = "AGENT"
    OPERATOR = "OPERATOR"


class ActionRequired(str, Enum):
    NONE = "NONE"
    SERVICE_SELECTION = "SERVICE_SELECTION"
    DATE_SELECTION = "DATE_SELECTION"
    SLOT_SELECTION = "SLOT_SELECTION"
    APPOINTMENT_SELECTION = "APPOINTMENT_SELECTION"
    CONFIRMATION = "CONFIRMATION"
    HUMAN = "HUMAN"


class WorkflowStep(str, Enum):
    INIT = "INIT"
    LOADING_PATIENT_CONTEXT = "LOADING_PATIENT_CONTEXT"
    UNDERSTANDING_REQUEST = "UNDERSTANDING_REQUEST"
    COLLECTING_REQUIREMENTS = "COLLECTING_REQUIREMENTS"
    SEARCHING_SLOTS = "SEARCHING_SLOTS"
    WAITING_SELECTION = "WAITING_SELECTION"
    QUERYING_APPOINTMENTS = "QUERYING_APPOINTMENTS"
    WAITING_APPOINTMENT_SELECTION = "WAITING_APPOINTMENT_SELECTION"
    PREPARING_CONFIRMATION = "PREPARING_CONFIRMATION"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    VALIDATING_EXECUTION = "VALIDATING_EXECUTION"
    EXECUTING_CORE_ACTION = "EXECUTING_CORE_ACTION"
    VERIFYING_CORE_RESULT = "VERIFYING_CORE_RESULT"
    RECONCILING_CORE_RESULT = "RECONCILING_CORE_RESULT"
    ENQUEUEING_WRITEBACK = "ENQUEUEING_WRITEBACK"
    ENQUEUEING_NOTIFICATION = "ENQUEUEING_NOTIFICATION"
    NEED_HUMAN = "NEED_HUMAN"
    TERMINAL = "TERMINAL"


class SuggestedReply(BaseModel):
    """A server-authorized reply that the UI may place in the patient's composer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    message: str
    mode: Literal["FILL_COMPOSER"]


class ServiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    duration_minutes: int = Field(ge=1)


class AvailableDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    available_slot_count: int = Field(ge=1)


class RunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    conversation_id: str
    intent: Optional[str] = None
    run_status: AgentRunStatus
    workflow_step: WorkflowStep
    execution_owner: ExecutionOwner
    state_version: int = Field(ge=0)
    current_reply: Optional[str] = None
    service_item_name: Optional[str] = None
    requested_date: Optional[str] = None
    suggested_replies: List[SuggestedReply] = Field(default_factory=list)
    candidate_service_items: List[ServiceOption] = Field(default_factory=list)
    candidate_dates: List[AvailableDate] = Field(default_factory=list)
    action_required: Optional[ActionRequired] = None
    selected_slot_id: Optional[str] = None
    appointment_id: Optional[str] = None
    confirmation_id: Optional[str] = None
    core_business_status: str
    writeback_status: str
    notification_status: str
    manual_task_id: Optional[str] = None
