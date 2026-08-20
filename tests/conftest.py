from dataclasses import dataclass
from datetime import date, datetime

import httpx
import pytest
import pytest_asyncio

from patient_ops_agent.api import create_agent_app
from patient_ops_agent.clock import FixedClock
from patient_ops_agent.demo import DemoScenarioController, FailureInjector
from patient_ops_agent.domain import InMemoryStore
from patient_ops_agent.gateways import ClinicCoreGateway, PatientOpsGateway
from patient_ops_agent.llm import RuleBasedUnderstandingProvider
from patient_ops_agent.mocks import (
    ClinicCoreData,
    PatientOpsData,
    create_clinic_core_app,
    create_patient_ops_app,
)
from patient_ops_agent.models import (
    Intent,
    ProposedAction,
    RequestedPeriod,
    UnderstandingResult,
)
from patient_ops_agent.policy import PolicyEngine
from patient_ops_agent.security import ActorContext, issue_actor_token
from patient_ops_agent.worker import NotificationSender, OutboxWorker
from patient_ops_agent.workflow import AgentWorkflow


@pytest.fixture
def appointment_understanding() -> UnderstandingResult:
    return UnderstandingResult(
        intent=Intent.CREATE_APPOINTMENT,
        service_item_text="洗牙",
        doctor_text="张医生",
        requested_date=date(2026, 8, 15),
        requested_period=RequestedPeriod.AFTERNOON,
        confidence=0.94,
        proposed_action=ProposedAction.SEARCH_SLOTS,
    )


@dataclass
class SystemUnderTest:
    client: httpx.AsyncClient
    clinic_client: httpx.AsyncClient
    patient_client: httpx.AsyncClient
    clinic_data: ClinicCoreData
    patient_data: PatientOpsData
    store: InMemoryStore
    workflow: AgentWorkflow
    worker: OutboxWorker
    notifier: NotificationSender
    demo_controller: DemoScenarioController
    clock: FixedClock
    token: str

    def headers(self, request_id: str, state_version=None):
        result = {"Authorization": f"Bearer {self.token}", "X-Request-ID": request_id}
        if state_version is not None:
            result["X-State-Version"] = str(state_version)
        return result

    async def conversation(self, request_id="conv-1"):
        response = await self.client.post(
            "/api/v1/conversations",
            json={"channel": "web_simulator"},
            headers=self.headers(request_id),
        )
        assert response.status_code == 201
        return response.json()["conversation_id"]

    async def send(self, conversation_id, message, request_id):
        return await self.client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message},
            headers=self.headers(request_id),
        )

    async def prepare_creation(self, slot_id="S1001"):
        conversation = await self.conversation()
        response = await self.send(conversation, "我想预约明天下午洗牙", "msg-1")
        run = response.json()["run"]
        slot = next(item for item in run["candidate_slots"] if item["id"] == slot_id)
        response = await self.client.post(
            f"/api/v1/runs/{run['run_id']}/slot-selection",
            json={"slot_id": slot_id, "slot_version": slot["version"]},
            headers=self.headers("select-1", run["state_version"]),
        )
        assert response.status_code == 200
        return response.json()

    async def confirm(self, run, request_id="confirm-1"):
        return await self.client.post(
            f"/api/v1/runs/{run['run_id']}/confirmations",
            json={"confirmation_id": run["confirmation_id"]},
            headers=self.headers(request_id, run["state_version"]),
        )

    async def select_appointment(self, run, appointment_id, appointment_version, request_id="appointment-selection-1"):
        return await self.client.post(
            f"/api/v1/runs/{run['run_id']}/appointment-selection",
            json={"appointment_id": appointment_id, "appointment_version": appointment_version},
            headers=self.headers(request_id, run["state_version"]),
        )


@pytest_asyncio.fixture
async def sut():
    clock = FixedClock(datetime.fromisoformat("2026-08-14T09:00:00+08:00"))
    store = InMemoryStore()
    clinic_data = ClinicCoreData()
    patient_data = PatientOpsData()
    failure_injector = FailureInjector()
    clinic_data.failure_injector = failure_injector
    clinic_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_clinic_core_app(clinic_data)),
        base_url="http://clinic-core",
    )
    patient_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_patient_ops_app(patient_data)),
        base_url="http://patient-ops",
    )
    workflow = AgentWorkflow(
        store,
        PatientOpsGateway(patient_client),
        ClinicCoreGateway(clinic_client),
        RuleBasedUnderstandingProvider(clock),
        PolicyEngine(),
        clock,
    )
    notifier = NotificationSender(failure_injector)
    worker = OutboxWorker(store, PatientOpsGateway(patient_client), notifier, clock)
    actor = ActorContext(
        actor_id="ACTOR-P1001",
        patient_id="P1001",
        verification_level="CHANNEL_AUTHENTICATED",
        verified_at=clock.now(),
    )
    token = issue_actor_token(actor, "test-secret")
    demo_controller = DemoScenarioController(failure_injector, enabled=True, max_retry_attempts=3)
    app = create_agent_app(workflow, store, clock, "test-secret", demo_controller=demo_controller)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")
    system = SystemUnderTest(
        client, clinic_client, patient_client, clinic_data, patient_data, store,
        workflow, worker, notifier, demo_controller, clock, token,
    )
    yield system
    await client.aclose()
    await clinic_client.aclose()
    await patient_client.aclose()
