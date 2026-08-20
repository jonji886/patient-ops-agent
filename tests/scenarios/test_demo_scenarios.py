"""Interview-demo scenarios exercise the same HTTP and workflow boundaries as the app."""

import pytest


@pytest.mark.asyncio
async def test_demo_commit_timeout_is_one_shot_and_reconciles(sut):
    armed = await sut.client.post(
        "/api/v1/demo/scenario",
        json={"scenario": "COMMIT_TIMEOUT"},
        headers=sut.headers("demo-arm-timeout"),
    )
    assert armed.status_code == 200
    assert armed.json()["active_scenario"] == "COMMIT_TIMEOUT"

    run = await sut.prepare_creation()
    result = (await sut.confirm(run, "demo-confirm-timeout")).json()

    assert result["core_business_status"] == "SUCCEEDED"
    assert result["attempt_count"] == 1
    assert len([item for item in sut.clinic_data.appointments.values() if item["patient_id"] == "P1001"]) == 1
    events = [event.event for event in sut.store.get_trace(run["run_id"])]
    assert events.index("tool_outcome_unknown") < events.index("business_result_found")
    status = (await sut.client.get("/api/v1/demo/scenario", headers=sut.headers("demo-status-timeout"))).json()
    assert status["active_scenario"] == "NONE"


@pytest.mark.asyncio
async def test_demo_tool_failure_transfers_execution_owner_to_human(sut):
    response = await sut.client.post(
        "/api/v1/demo/scenario",
        json={"scenario": "TOOL_FAILURE_HANDOFF"},
        headers=sut.headers("demo-arm-tool-failure"),
    )
    assert response.status_code == 200

    run = await sut.prepare_creation(slot_id="S1002")
    result = (await sut.confirm(run, "demo-confirm-tool-failure")).json()

    assert result["execution_owner"] == "OPERATOR"
    assert result["run_status"] == "WAITING_HUMAN"
    assert result["manual_task_id"]
    assert len([item for item in sut.store.tool_executions if item.run_id == run["run_id"]]) == 3
    assert (await sut.client.get("/api/v1/demo/scenario", headers=sut.headers("demo-status-tool-failure"))).json()["active_scenario"] == "NONE"

    blocked = await sut.send(run["conversation_id"], "继续自动创建预约", "demo-after-handoff")
    assert blocked.status_code == 202
    assert blocked.json()["run"]["execution_owner"] == "OPERATOR"
    assert len([item for item in sut.store.tool_executions if item.run_id == run["run_id"]]) == 3


@pytest.mark.asyncio
async def test_demo_notification_failure_keeps_business_success(sut):
    response = await sut.client.post(
        "/api/v1/demo/scenario",
        json={"scenario": "NOTIFICATION_FAILURE"},
        headers=sut.headers("demo-arm-notification"),
    )
    assert response.status_code == 200

    run = await sut.prepare_creation(slot_id="S1001")
    result = (await sut.confirm(run, "demo-confirm-notification")).json()
    for _ in range(3):
        for event in sut.store.pending_outbox():
            event.next_attempt_at = sut.clock.now()
            sut.store.save_outbox(event)
        await sut.worker.process_once()
    projected = sut.store.get_run(result["run_id"])

    assert projected.core_business_status.value == "SUCCEEDED"
    assert projected.notification_status.value == "FAILED_NEEDS_HUMAN"
    assert projected.run_status.value == "COMPLETED_WITH_PENDING_SIDE_EFFECTS"
    assert (await sut.client.get("/api/v1/demo/scenario", headers=sut.headers("demo-status-notification"))).json()["active_scenario"] == "NONE"


@pytest.mark.asyncio
async def test_demo_policy_block_uses_real_policy_path_without_tool_execution(sut):
    response = await sut.client.post(
        "/api/v1/demo/scenario",
        json={"scenario": "POLICY_BLOCK"},
        headers=sut.headers("demo-arm-policy"),
    )
    assert response.status_code == 200
    trigger = response.json()["trigger_message"]

    conversation = await sut.conversation("demo-policy-conversation")
    result = (await sut.send(conversation, trigger, "demo-policy-trigger")).json()["run"]
    assert result["run_status"] == "FAILED"
    assert result["last_error_code"] == "FORBIDDEN"
    assert not [item for item in sut.store.tool_executions if item.run_id == result["run_id"]]
    assert any(event.event == "policy_denied" for event in sut.store.get_trace(result["run_id"]))
