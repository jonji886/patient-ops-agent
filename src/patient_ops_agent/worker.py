"""Transactional-outbox consumer semantics for writeback and notification."""

import asyncio
from datetime import timedelta
from typing import Dict

from patient_ops_agent.clock import Clock
from patient_ops_agent.domain.models import OutboxStatus, SideEffectStatus
from patient_ops_agent.domain.store import InMemoryStore
from patient_ops_agent.gateways import GatewayError, PatientOpsGateway
from patient_ops_agent.models import AgentRunStatus


class NotificationSender:
    def __init__(self) -> None:
        self.messages = []
        self.fail_attempts = 0

    async def send(self, payload: Dict[str, object], event_id: str) -> None:
        if self.fail_attempts > 0:
            self.fail_attempts -= 1
            raise GatewayError("UPSTREAM_UNAVAILABLE", "synthetic notification failure", True)
        if not any(item["event_id"] == event_id for item in self.messages):
            self.messages.append({"event_id": event_id, "payload": payload})


class OutboxWorker:
    def __init__(self, store: InMemoryStore, patient_ops: PatientOpsGateway, notifier: NotificationSender,
                 clock: Clock, max_attempts: int = 3) -> None:
        self.store = store
        self.patient_ops = patient_ops
        self.notifier = notifier
        self.clock = clock
        self.max_attempts = max_attempts

    async def process_once(self) -> int:
        processed = 0
        for event in self.store.pending_outbox():
            if event.next_attempt_at > self.clock.now():
                continue
            event.attempt_count += 1
            try:
                if event.event_type == "WRITEBACK":
                    await self.patient_ops.writeback(event.payload, event.id)
                else:
                    await self.notifier.send(event.payload, event.id)
                event.status = OutboxStatus.SUCCEEDED
            except GatewayError:
                if event.attempt_count >= self.max_attempts:
                    event.status = OutboxStatus.FAILED_NEEDS_HUMAN
                else:
                    event.status = OutboxStatus.RETRY_SCHEDULED
                    event.next_attempt_at = self.clock.now() + timedelta(seconds=2 ** event.attempt_count)
            self.store.save_outbox(event)
            self._project(event.run_id)
            processed += 1
        return processed

    def _project(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        events = self.store.list_outbox(run_id)
        for event in events:
            status = SideEffectStatus(event.status.value)
            if event.event_type == "WRITEBACK": run.writeback_status = status
            else: run.notification_status = status
        if all(event.status is OutboxStatus.SUCCEEDED for event in events):
            run.run_status = AgentRunStatus.COMPLETED
        else:
            run.run_status = AgentRunStatus.COMPLETED_WITH_PENDING_SIDE_EFFECTS
        self.store.save_run(run, expected_version=run.state_version)


def run() -> None:
    from patient_ops_agent.clock import SystemClock
    from patient_ops_agent.gateways import PatientOpsGateway
    from patient_ops_agent.persistence import PostgresStore
    from patient_ops_agent.settings import Settings
    import httpx

    async def serve() -> None:
        settings = Settings()
        settings.validate_storage_configuration()
        if settings.uses_sqlite:
            raise RuntimeError("SQLite local mode runs the Outbox Worker inside patient-ops-agent")
        client = httpx.AsyncClient(base_url=settings.patient_ops_base_url, timeout=5)
        worker = OutboxWorker(PostgresStore(settings.agent_database_url), PatientOpsGateway(client),
                              NotificationSender(), SystemClock(), settings.max_retry_attempts)
        try:
            while True:
                await worker.process_once()
                await asyncio.sleep(settings.outbox_poll_interval_seconds)
        finally:
            await client.aclose()

    asyncio.run(serve())
