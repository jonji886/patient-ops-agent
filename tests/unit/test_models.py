from datetime import date

import pytest
from pydantic import ValidationError

from patient_ops_agent.models import (
    Appointment,
    AppointmentStatus,
    ErrorCode,
    ErrorDetail,
    Intent,
    Outcome,
    ProposedAction,
    RequestedPeriod,
    Slot,
    SlotStatus,
    UnderstandingResult,
)


def test_understanding_result_accepts_structured_appointment_request():
    result = UnderstandingResult(
        intent=Intent.CREATE_APPOINTMENT,
        service_item_text="洗牙",
        requested_date=date(2026, 8, 15),
        requested_period=RequestedPeriod.AFTERNOON,
        confidence=0.94,
        proposed_action=ProposedAction.SEARCH_SLOTS,
    )

    assert result.intent is Intent.CREATE_APPOINTMENT
    assert result.requested_date == date(2026, 8, 15)


def test_understanding_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        UnderstandingResult(
            intent="CREATE_APPOINTMENT",
            confidence=0.9,
            proposed_action="SEARCH_SLOTS",
            model_decided_permission="ALLOW",
        )


def test_understanding_result_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        UnderstandingResult(
            intent="CREATE_APPOINTMENT",
            confidence=1.1,
            proposed_action="SEARCH_SLOTS",
        )


def test_slot_and_appointment_have_separate_status_enums():
    slot = Slot(
        id="S1001",
        clinic_id="C001",
        doctor_id="D001",
        service_item_id="SV-CLEANING",
        start_at="2026-08-15T14:00:00+08:00",
        end_at="2026-08-15T15:00:00+08:00",
        status="AVAILABLE",
        version=1,
    )
    appointment = Appointment(
        id="A1001",
        patient_id="P1001",
        clinic_id="C001",
        service_item_id="SV-CLEANING",
        doctor_id="D001",
        slot_id="S1001",
        status="CONFIRMED",
        version=1,
    )

    assert slot.status is SlotStatus.AVAILABLE
    assert appointment.status is AppointmentStatus.CONFIRMED


def test_error_detail_carries_outcome_and_retryability():
    error = ErrorDetail(
        code=ErrorCode.SLOT_VERSION_CONFLICT,
        message="slot changed",
        retryable=False,
        outcome=Outcome.NOT_EXECUTED,
    )

    assert error.code is ErrorCode.SLOT_VERSION_CONFLICT
    assert error.outcome is Outcome.NOT_EXECUTED
