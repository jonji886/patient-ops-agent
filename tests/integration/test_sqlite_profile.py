"""The local profile must persist a complete workflow without PostgreSQL."""

from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from patient_ops_agent.clock import FixedClock
from patient_ops_agent.domain.models import AgentRun
from patient_ops_agent.gateways import ClinicCoreGateway, PatientOpsGateway
from patient_ops_agent.llm import RuleBasedUnderstandingProvider
from patient_ops_agent.mocks import ClinicCoreData, PatientOpsData, create_clinic_core_app, create_patient_ops_app
from patient_ops_agent.persistence import SQLiteStore
from patient_ops_agent.policy import PolicyEngine
from patient_ops_agent.security import ActorContext, issue_actor_token
from patient_ops_agent.workflow import AgentWorkflow


@pytest.mark.asyncio
async def test_sqlite_profile_persists_agent_and_mock_business_state(tmp_path):
    clock = FixedClock(datetime.fromisoformat("2026-08-14T09:00:00+08:00"))
    agent_url = f"sqlite:///{tmp_path / 'agent.db'}"
    patient_url = f"sqlite:///{tmp_path / 'patient.db'}"
    clinic_url = f"sqlite:///{tmp_path / 'clinic.db'}"
    store = SQLiteStore(agent_url)
    patient_data = PatientOpsData(database_url=patient_url)
    clinic_data = ClinicCoreData(database_url=clinic_url)
    patient_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_patient_ops_app(patient_data)), base_url="http://patient"
    )
    clinic_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_clinic_core_app(clinic_data)), base_url="http://clinic"
    )
    workflow = AgentWorkflow(
        store,
        PatientOpsGateway(patient_client),
        ClinicCoreGateway(clinic_client),
        RuleBasedUnderstandingProvider(clock),
        PolicyEngine(),
        clock,
    )
    actor = ActorContext(
        actor_id="ACTOR-P1001", patient_id="P1001", verification_level="CHANNEL_AUTHENTICATED",
        verified_at=clock.now(),
    )
    conversation = await workflow.create_conversation(actor, "web_simulator")
    run = await workflow.message(conversation.id, actor, "我想预约明天下午洗牙", "TRACE-1")
    slot = next(item for item in run.candidate_slots if item["id"] == "S1001")
    run = await workflow.select_slot(run.id, actor, "S1001", slot["version"], run.state_version, "TRACE-2")
    run = await workflow.confirm(run.id, actor, run.confirmation_id, run.state_version, "TRACE-3")
    run_id, appointment_id = run.id, run.appointment_id
    await patient_client.aclose()
    await clinic_client.aclose()
    store.dispose()

    reopened_store = SQLiteStore(agent_url)
    reopened_clinic = ClinicCoreData(database_url=clinic_url)
    restored = reopened_store.get_run(run_id)
    assert isinstance(restored, AgentRun)
    assert restored.appointment_id == appointment_id
    assert restored.core_business_status.value == "SUCCEEDED"
    assert len(reopened_store.get_trace(run_id)) >= 4
    assert len(reopened_store.list_outbox(run_id)) == 2
    assert reopened_clinic.appointments[appointment_id]["status"] == "CONFIRMED"
    reopened_store.dispose()


def test_main_builds_a_self_contained_sqlite_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path / 'agent.db'}")
    monkeypatch.setenv("PATIENT_OPS_DATABASE_URL", f"sqlite:///{tmp_path / 'patient.db'}")
    monkeypatch.setenv("CLINIC_CORE_DATABASE_URL", f"sqlite:///{tmp_path / 'clinic.db'}")
    monkeypatch.setenv("ACTOR_TOKEN_SIGNING_SECRET", "sqlite-main-secret")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    from patient_ops_agent.main import build_app

    app = build_app()
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"username": "patient", "password": "123456"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}", "X-Request-ID": "sqlite-conversation"}
        conversation = client.post("/api/v1/conversations", json={"channel": "web_simulator"}, headers=headers)
        assert conversation.status_code == 201
        headers["X-Request-ID"] = "sqlite-message"
        response = client.post(
            f"/api/v1/conversations/{conversation.json()['conversation_id']}/messages",
            json={"message": "我想预约2026-08-15下午洗牙"},
            headers=headers,
        )
    assert response.status_code == 202
    assert response.json()["run"]["workflow_step"] == "WAITING_SELECTION"
