"""Shared business response models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
    APPOINTMENT_NOT_FOUND = "APPOINTMENT_NOT_FOUND"
    SERVICE_ITEM_NOT_FOUND = "SERVICE_ITEM_NOT_FOUND"
    SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
    SLOT_OCCUPIED = "SLOT_OCCUPIED"
    SLOT_VERSION_CONFLICT = "SLOT_VERSION_CONFLICT"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST = (
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    )
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    STATE_VERSION_CONFLICT = "STATE_VERSION_CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Outcome(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    EXECUTED = "EXECUTED"
    UNKNOWN = "UNKNOWN"


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class SlotStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    UNAVAILABLE = "UNAVAILABLE"


class AppointmentStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    retryable: bool
    outcome: Outcome
    correlation_id: Optional[str] = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class OperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status: OperationStatus
    outcome: Outcome
    business_id: Optional[str] = None
    response_snapshot: Optional[Dict[str, Any]] = None


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    clinic_id: str
    doctor_id: str
    service_item_id: str
    start_at: datetime
    end_at: datetime
    status: SlotStatus
    version: int = Field(ge=1)


class Appointment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    patient_id: str
    clinic_id: str
    service_item_id: str
    doctor_id: str
    slot_id: str
    status: AppointmentStatus
    version: int = Field(ge=1)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    clinic_name: Optional[str] = None
    service_item_name: Optional[str] = None
    doctor_name: Optional[str] = None
