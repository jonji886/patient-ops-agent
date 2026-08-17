from datetime import timedelta

import pytest

from patient_ops_agent.domain.models import (
    AgentRun, ConfirmationRecord, ConfirmationStatus, Conversation, OutboxEvent, OutboxStatus, TraceEvent,
)
from patient_ops_agent.domain.store import InMemoryStore, StateVersionConflict


def test_new_run_starts_at_state_version_zero(sut):
    now = sut.clock.now()
    run = AgentRun(id="RUN-X", conversation_id="CONV-X", patient_id="P1001", actor_id="ACTOR-P1001",
        verification_level="CHANNEL_AUTHENTICATED", verified_at=now, started_at=now)
    assert sut.store.save_run(run).state_version == 0


def test_each_run_save_increments_state_version(sut):
    now = sut.clock.now()
    run = AgentRun(id="RUN-X", conversation_id="CONV-X", patient_id="P1001", actor_id="ACTOR-P1001",
        verification_level="CHANNEL_AUTHENTICATED", verified_at=now, started_at=now)
    run = sut.store.save_run(run)
    run = sut.store.save_run(run, expected_version=0)
    assert run.state_version == 1


def test_stale_repository_write_is_rejected(sut):
    now = sut.clock.now()
    run = AgentRun(id="RUN-X", conversation_id="CONV-X", patient_id="P1001", actor_id="ACTOR-P1001",
        verification_level="CHANNEL_AUTHENTICATED", verified_at=now, started_at=now)
    sut.store.save_run(run)
    with pytest.raises(StateVersionConflict):
        sut.store.save_run(run.model_copy(update={"state_version": 9}), expected_version=9)


def test_repository_returns_defensive_copies(sut):
    conversation = Conversation(id="CONV-X", channel="web_simulator", actor_id="A", patient_id="P1001",
                                created_at=sut.clock.now())
    sut.store.add_conversation(conversation)
    fetched = sut.store.get_conversation("CONV-X")
    fetched.patient_id = "P1002"
    assert sut.store.get_conversation("CONV-X").patient_id == "P1001"


def test_confirmation_status_is_persisted(sut):
    now = sut.clock.now()
    record = ConfirmationRecord(id="C", run_id="R", patient_id="P1001", action_type="CREATE_APPOINTMENT",
        target_id="S", parameters={}, parameter_hash="h", resource_version=1,
        expires_at=now + timedelta(minutes=5))
    sut.store.add_confirmation(record)
    record.status = ConfirmationStatus.INVALIDATED
    sut.store.save_confirmation(record)
    assert sut.store.get_confirmation("C").status is ConfirmationStatus.INVALIDATED


def test_trace_events_keep_append_order(sut):
    for event in ("first", "second"):
        sut.store.add_trace("R", TraceEvent(timestamp=sut.clock.now(), trace_id="T", event=event))
    assert [item.event for item in sut.store.get_trace("R")] == ["first", "second"]


def test_command_result_is_replayable(sut):
    sut.store.save_command_result("request", {"accepted": True})
    assert sut.store.get_command_result("request") == {"accepted": True}


def test_outbox_pending_filter_excludes_succeeded(sut):
    now = sut.clock.now()
    first = OutboxEvent(id="O1", run_id="R", operation_id="OP", event_type="WRITEBACK",
                        payload={}, next_attempt_at=now, created_at=now)
    second = first.model_copy(update={"id": "O2", "event_type": "NOTIFICATION", "status": OutboxStatus.SUCCEEDED})
    sut.store.add_outbox(first); sut.store.add_outbox(second)
    assert [item.id for item in sut.store.pending_outbox()] == ["O1"]
