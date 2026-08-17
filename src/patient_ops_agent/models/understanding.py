"""Structured result produced by an LLM provider or its test double."""

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Intent(str, Enum):
    CREATE_APPOINTMENT = "CREATE_APPOINTMENT"
    QUERY_SLOT_AVAILABILITY = "QUERY_SLOT_AVAILABILITY"
    QUERY_APPOINTMENT = "QUERY_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    CANCEL_CURRENT_RUN = "CANCEL_CURRENT_RUN"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    FOLLOW_UP = "FOLLOW_UP"
    GENERAL_QUESTION = "GENERAL_QUESTION"
    UNKNOWN = "UNKNOWN"


class RequestedPeriod(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"


class ProposedAction(str, Enum):
    COLLECT_REQUIREMENTS = "COLLECT_REQUIREMENTS"
    SEARCH_SLOTS = "SEARCH_SLOTS"
    SEARCH_ALTERNATIVE_SLOTS = "SEARCH_ALTERNATIVE_SLOTS"
    QUERY_APPOINTMENTS = "QUERY_APPOINTMENTS"
    RESOLVE_APPOINTMENT = "RESOLVE_APPOINTMENT"
    REQUEST_CONFIRMATION = "REQUEST_CONFIRMATION"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    RECOMMEND_SERVICE = "RECOMMEND_SERVICE"
    NONE = "NONE"


class UnderstandingResult(BaseModel):
    """Only a candidate interpretation; it never authorizes a Tool call."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    service_item_text: Optional[str] = None
    clinic_text: Optional[str] = None
    doctor_text: Optional[str] = None
    requested_date: Optional[date] = None
    requested_period: Optional[RequestedPeriod] = None
    ambiguities: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    proposed_action: ProposedAction
