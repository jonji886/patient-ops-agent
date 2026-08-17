"""Composition root for SQLite local development and PostgreSQL deployment."""

import asyncio
from contextlib import asynccontextmanager
import httpx
import uvicorn

from patient_ops_agent.api import create_agent_app
from patient_ops_agent.clock import runtime_clock
from patient_ops_agent.gateways import ClinicCoreGateway, PatientOpsGateway
from patient_ops_agent.llm import DeepSeekUnderstandingProvider, RuleBasedUnderstandingProvider
from patient_ops_agent.policy import PolicyEngine
from patient_ops_agent.mocks import ClinicCoreData, PatientOpsData, create_clinic_core_app, create_patient_ops_app
from patient_ops_agent.persistence import PostgresStore, SQLiteStore
from patient_ops_agent.settings import Settings
from patient_ops_agent.worker import NotificationSender, OutboxWorker
from patient_ops_agent.workflow import AgentWorkflow


def build_app():
    settings = Settings(); settings.validate_llm_configuration(); settings.validate_storage_configuration()
    clock = runtime_clock(settings.uses_sqlite, settings.llm_provider, settings.demo_business_clock)
    if settings.uses_sqlite:
        store = SQLiteStore(settings.agent_database_url)
        patient_data = PatientOpsData(database_url=settings.patient_ops_database_url)
        clinic_data = ClinicCoreData(database_url=settings.clinic_core_database_url)
        patient_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_patient_ops_app(patient_data)), base_url="http://patient-ops-local"
        )
        clinic_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_clinic_core_app(clinic_data)), base_url="http://clinic-core-local"
        )
    else:
        store = PostgresStore(settings.agent_database_url)
        patient_client = httpx.AsyncClient(base_url=settings.patient_ops_base_url, timeout=5)
        clinic_client = httpx.AsyncClient(base_url=settings.clinic_core_base_url, timeout=5)
    provider = (DeepSeekUnderstandingProvider(settings.deepseek_api_key.get_secret_value(), settings.deepseek_model,
        settings.deepseek_base_url, settings.llm_timeout_seconds) if settings.llm_provider == "deepseek"
        else RuleBasedUnderstandingProvider(clock))
    workflow = AgentWorkflow(store, PatientOpsGateway(patient_client), ClinicCoreGateway(clinic_client), provider,
                             PolicyEngine(), clock, settings.confirmation_ttl_seconds, settings.max_retry_attempts)
    worker = None
    if settings.uses_sqlite:
        worker = OutboxWorker(store, PatientOpsGateway(patient_client), NotificationSender(), clock,
                              settings.max_retry_attempts)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        task = None
        if worker:
            async def consume() -> None:
                while not stop.is_set():
                    await worker.process_once()
                    await asyncio.sleep(settings.outbox_poll_interval_seconds)

            task = asyncio.create_task(consume())
        try:
            yield
        finally:
            stop.set()
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await patient_client.aclose()
            await clinic_client.aclose()
            store.dispose()

    app = create_agent_app(workflow, store, clock, settings.actor_token_signing_secret.get_secret_value(), lifespan)
    app.state.patient_client = patient_client
    app.state.clinic_client = clinic_client
    app.state.store = store
    app.state.local_worker = worker
    return app


app = build_app()


def run() -> None:
    uvicorn.run("patient_ops_agent.main:app", host="0.0.0.0", port=8000)
