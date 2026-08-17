import pytest

from patient_ops_agent.mocks import ClinicCoreData
from patient_ops_agent.mocks.fixtures import load_fixtures


@pytest.mark.asyncio
async def test_patient_context_contract(sut):
    response = await sut.patient_client.get("/api/v1/patients/P1001/context")
    assert response.status_code == 200
    assert response.json()["patient_id"] == "P1001"


@pytest.mark.asyncio
async def test_missing_patient_is_structured_error(sut):
    response = await sut.patient_client.get("/api/v1/patients/P404/context")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_contact_consent_is_patient_specific(sut):
    p1 = await sut.patient_client.get("/api/v1/patients/P1001/contact-consents/web_simulator")
    p2 = await sut.patient_client.get("/api/v1/patients/P1002/contact-consents/web_simulator")
    assert p1.json()["allowed"] is True
    assert p2.json()["allowed"] is False


@pytest.mark.asyncio
async def test_slot_search_only_returns_available_matching_slots(sut):
    response = await sut.clinic_client.get("/api/v1/slots", params={
        "service_item_id": "SV-CLEANING", "start_date": "2026-08-15", "period": "AFTERNOON"})
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {"S1001", "S1002"}


def test_persisted_synthetic_catalog_only_appends_new_records():
    catalog = load_fixtures()
    saved = {"clinics": catalog["clinics"], "service_items": catalog["service_items"][:2],
             "doctors": catalog["doctors"][:2], "slots": {"S1001": catalog["slots"][0]},
             "appointments": {}, "operations": {}, "idempotency": {}}
    merged = ClinicCoreData._merge_catalog(saved, catalog)
    assert {item["name"] for item in merged["service_items"]} == {"洗牙", "口腔检查", "补牙", "拔牙"}
    assert merged["slots"]["S1001"] == saved["slots"]["S1001"]
    assert "S1006" in merged["slots"]


@pytest.mark.asyncio
async def test_create_requires_idempotency_key(sut):
    response = await sut.clinic_client.post("/api/v1/appointments", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_create_idempotent_replay_returns_same_appointment(sut):
    body = {"operation_id": "OP-1", "patient_id": "P1001", "clinic_id": "C001",
            "service_item_id": "SV-CLEANING", "doctor_id": "D001", "slot_id": "S1001",
            "expected_slot_version": 1}
    first = await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-1"})
    second = await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-1"})
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["appointment_id"] == second.json()["appointment_id"]
    assert second.json()["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_idempotency_key_rejects_different_request(sut):
    body = {"operation_id": "OP-1", "patient_id": "P1001", "clinic_id": "C001",
            "service_item_id": "SV-CLEANING", "doctor_id": "D001", "slot_id": "S1001",
            "expected_slot_version": 1}
    await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-1"})
    body["patient_id"] = "P1002"
    response = await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-1"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"


@pytest.mark.asyncio
async def test_slot_version_conflict_does_not_book(sut):
    body = {"operation_id": "OP-1", "patient_id": "P1001", "clinic_id": "C001",
            "service_item_id": "SV-CLEANING", "doctor_id": "D001", "slot_id": "S1001",
            "expected_slot_version": 99}
    response = await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-1"})
    assert response.status_code == 409
    assert sut.clinic_data.slots["S1001"]["status"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_cancel_forbids_wrong_patient(sut):
    response = await sut.clinic_client.post("/api/v1/appointments/A1001/cancel",
        json={"operation_id": "OP-X", "patient_id": "P1001", "expected_appointment_version": 1},
        headers={"Idempotency-Key": "OP-X"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_operation_result_recovers_committed_create(sut):
    sut.clinic_data.timeout_after_commit_once = True
    body = {"operation_id": "OP-T", "patient_id": "P1001", "clinic_id": "C001",
            "service_item_id": "SV-CLEANING", "doctor_id": "D001", "slot_id": "S1001",
            "expected_slot_version": 1}
    response = await sut.clinic_client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": "OP-T"})
    result = await sut.clinic_client.get("/api/v1/operations/OP-T")
    assert response.status_code == 504
    assert result.json()["outcome"] == "EXECUTED"


@pytest.mark.asyncio
async def test_writeback_is_idempotent(sut):
    body = {"run_id": "RUN-1", "operation_id": "OP-W", "patient_id": "P1001",
            "task_type": "CREATE_APPOINTMENT", "task_status": "SUCCEEDED"}
    first = await sut.patient_client.post("/api/v1/agent-results", json=body, headers={"Idempotency-Key": "OUT-1"})
    second = await sut.patient_client.post("/api/v1/agent-results", json=body, headers={"Idempotency-Key": "OUT-1"})
    assert first.json()["result_id"] == second.json()["result_id"]
    assert second.json()["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_future_appointments_are_scoped_by_patient(sut):
    p1 = await sut.clinic_client.get("/api/v1/patients/P1001/appointments")
    p2 = await sut.clinic_client.get("/api/v1/patients/P1002/appointments")
    assert p1.json() == []
    assert [item["id"] for item in p2.json()] == ["A1001"]
