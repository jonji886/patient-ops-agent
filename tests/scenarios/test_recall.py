"""Recall scenario tests: Decline, Skip, Handoff, Timeout recovery.

这些测试验证 Recall 闭环的异常路径：
- Case 5: 患者拒绝召回 → recall_status = DECLINED，不继续自动推进
- Case 4: 患者已有预约 → Skip Recall，防止重复触达
- Case 6: 患者要求人工 → execution_owner = OPERATOR
- Case 7: Recall 预约创建 Timeout After Commit → 对账恢复，不重复
"""

import pytest

from patient_ops_agent.domain.models import ConfirmationStatus


@pytest.mark.asyncio
async def test_recall_declined_sets_status_and_terminates(sut):
    """Case 5: 患者拒绝召回 → recall_status = DECLINED，Run 终止。"""
    conversation = await sut.conversation()
    outreach = (await sut.send(conversation, "我想复查洗牙", "msg-recall-outreach")).json()["run"]
    assert outreach["recall_status"] == "OUTREACHED"

    declined = (await sut.send(conversation, "不需要", "msg-recall-decline")).json()["run"]
    assert declined["recall_status"] == "DECLINED"
    assert declined["run_status"] == "COMPLETED"
    assert "跳过本次复查提醒" in declined["current_reply"]
    assert not [item for item in sut.store.tool_executions if item.tool_name == "create_appointment"]
    assert any(event.event == "recall_declined" for event in sut.store.get_trace(declined["run_id"]))


@pytest.mark.asyncio
async def test_recall_skipped_when_patient_has_existing_appointment(sut):
    """Case 4: 患者已有未来有效洗牙预约 → Skip Recall，防止重复触达。"""
    created = (await sut.confirm(await sut.prepare_creation())).json()
    conversation = await sut.conversation("conv-recall-skip")
    run = (await sut.send(conversation, "我想复查洗牙", "msg-recall-skip")).json()["run"]

    assert run["recall_status"] == "SKIPPED"
    assert run["action_required"] == "NONE"
    assert "已有未来的洗牙预约" in run["current_reply"]
    assert run["appointment_id"] is None or run["appointment_id"] != created["appointment_id"]
    assert any(event.event == "recall_skipped_existing_appointment" for event in sut.store.get_trace(run["run_id"]))


@pytest.mark.asyncio
async def test_recall_patient_requests_human_during_outreach(sut):
    """Case 6: 患者在召回触达期间要求人工 → execution_owner = OPERATOR。"""
    conversation = await sut.conversation()
    outreach = (await sut.send(conversation, "我想复查洗牙", "msg-recall-outreach-handoff")).json()["run"]
    assert outreach["recall_status"] == "OUTREACHED"

    handoff = (await sut.send(conversation, "转接人工客服", "msg-recall-handoff")).json()["run"]
    assert handoff["execution_owner"] == "OPERATOR"
    assert handoff["run_status"] == "WAITING_HUMAN"
    assert handoff["manual_task_id"]
    assert not [item for item in sut.store.tool_executions if item.tool_name == "create_appointment"]


@pytest.mark.asyncio
async def test_recall_appointment_timeout_reconciles_without_duplicate(sut):
    """Case 7: Recall 预约创建 Timeout After Commit → 对账恢复，recall_status = CONVERTED，不重复。"""
    conversation = await sut.conversation()
    follow_up = (await sut.send(conversation, "复查洗牙", "msg-recall-timeout")).json()["run"]
    assert follow_up["recall_status"] == "OUTREACHED"

    selected_date = await sut.client.post(
        f"/api/v1/runs/{follow_up['run_id']}/date-selection",
        json={"date": "2026-08-16"},
        headers=sut.headers("recall-timeout-date", follow_up["state_version"]),
    )
    slot_run = selected_date.json()

    selected_slot = await sut.client.post(
        f"/api/v1/runs/{follow_up['run_id']}/slot-selection",
        json={"slot_id": "S1003", "slot_version": slot_run["candidate_slots"][0]["version"]},
        headers=sut.headers("recall-timeout-slot", slot_run["state_version"]),
    )
    confirmation_run = selected_slot.json()

    sut.clinic_data.timeout_after_commit_once = True
    confirmed = (await sut.confirm(confirmation_run, "recall-timeout-confirm")).json()

    assert confirmed["core_business_status"] == "SUCCEEDED"
    assert confirmed["recall_status"] == "CONVERTED"
    assert confirmed["attempt_count"] == 1
    matches = [item for item in sut.clinic_data.appointments.values() if item["patient_id"] == "P1001"]
    assert len(matches) == 1
    events = [event.event for event in sut.store.get_trace(confirmed["run_id"])]
    assert "tool_outcome_unknown" in events
    assert "business_result_found" in events
    assert "recall_converted" in events


@pytest.mark.asyncio
async def test_recall_full_loop_converts_and_writeback_contains_recall_status(sut):
    """Recall 完整闭环：Outreach → Accept → Appointment → Writeback 包含 recall_status=CONVERTED。"""
    conversation = await sut.conversation()
    follow_up = (await sut.send(conversation, "复查洗牙", "msg-recall-full")).json()["run"]
    assert follow_up["recall_status"] == "OUTREACHED"

    selected_date = await sut.client.post(
        f"/api/v1/runs/{follow_up['run_id']}/date-selection",
        json={"date": "2026-08-16"},
        headers=sut.headers("recall-full-date", follow_up["state_version"]),
    )
    slot_run = selected_date.json()

    selected_slot = await sut.client.post(
        f"/api/v1/runs/{follow_up['run_id']}/slot-selection",
        json={"slot_id": "S1003", "slot_version": slot_run["candidate_slots"][0]["version"]},
        headers=sut.headers("recall-full-slot", slot_run["state_version"]),
    )
    confirmation_run = selected_slot.json()

    confirmed = (await sut.confirm(confirmation_run, "recall-full-confirm")).json()
    assert confirmed["core_business_status"] == "SUCCEEDED"
    assert confirmed["recall_status"] == "CONVERTED"

    await sut.worker.process_once()
    writeback_events = [e for e in sut.store.list_outbox(confirmed["run_id"]) if e.event_type == "WRITEBACK"]
    assert writeback_events
    assert writeback_events[0].payload.get("recall_status") == "CONVERTED"
