"""Thread-safe deterministic repository used by tests and local composition.

The application only depends on this repository surface. The PostgreSQL adapter
implements the same methods for deployed services.
"""

from copy import deepcopy
from threading import RLock
from typing import Dict, List, Optional

from .models import (
    AgentRun,
    ConfirmationRecord,
    Conversation,
    ManualTask,
    OutboxEvent,
    ToolExecution,
    TraceEvent,
)


class StateVersionConflict(Exception):
    pass


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self.conversations: Dict[str, Conversation] = {}
        self.runs: Dict[str, AgentRun] = {}
        self.confirmations: Dict[str, ConfirmationRecord] = {}
        self.manual_tasks: Dict[str, ManualTask] = {}
        self.outbox: Dict[str, OutboxEvent] = {}
        self.traces: Dict[str, List[TraceEvent]] = {}
        self.tool_executions: List[ToolExecution] = []
        self.command_results: Dict[str, object] = {}

    def add_conversation(self, conversation: Conversation) -> None:
        with self._lock:
            self.conversations[conversation.id] = deepcopy(conversation)

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with self._lock:
            value = self.conversations.get(conversation_id)
            return deepcopy(value)

    def save_run(self, run: AgentRun, expected_version: Optional[int] = None) -> AgentRun:
        with self._lock:
            current = self.runs.get(run.id)
            if expected_version is not None and current and current.state_version != expected_version:
                raise StateVersionConflict(run.id)
            value = run.model_copy(deep=True)
            value.state_version = (current.state_version + 1) if current else 0
            run.state_version = value.state_version
            self.runs[run.id] = value
            return deepcopy(value)

    def get_run(self, run_id: str) -> Optional[AgentRun]:
        with self._lock:
            value = self.runs.get(run_id)
            return deepcopy(value)

    def list_runs(self) -> List[AgentRun]:
        with self._lock:
            return deepcopy(sorted(self.runs.values(), key=lambda item: item.started_at, reverse=True))

    def latest_run(self, conversation_id: str) -> Optional[AgentRun]:
        with self._lock:
            values = [r for r in self.runs.values() if r.conversation_id == conversation_id]
            return deepcopy(max(values, key=lambda item: item.started_at)) if values else None

    def add_confirmation(self, record: ConfirmationRecord) -> None:
        with self._lock:
            self.confirmations[record.id] = deepcopy(record)

    def get_confirmation(self, confirmation_id: str) -> Optional[ConfirmationRecord]:
        with self._lock:
            return deepcopy(self.confirmations.get(confirmation_id))

    def save_confirmation(self, record: ConfirmationRecord) -> None:
        with self._lock:
            self.confirmations[record.id] = deepcopy(record)

    def add_trace(self, run_id: str, event: TraceEvent) -> None:
        with self._lock:
            self.traces.setdefault(run_id, []).append(deepcopy(event))

    def get_trace(self, run_id: str) -> List[TraceEvent]:
        with self._lock:
            return deepcopy(self.traces.get(run_id, []))

    def add_tool_execution(self, execution: ToolExecution) -> None:
        with self._lock:
            self.tool_executions.append(deepcopy(execution))

    def add_manual_task(self, task: ManualTask) -> None:
        with self._lock:
            self.manual_tasks[task.id] = deepcopy(task)

    def get_manual_task(self, task_id: str) -> Optional[ManualTask]:
        with self._lock:
            return deepcopy(self.manual_tasks.get(task_id))

    def save_manual_task(self, task: ManualTask) -> None:
        with self._lock:
            self.manual_tasks[task.id] = deepcopy(task)

    def list_manual_tasks(self, status: Optional[str] = None) -> List[ManualTask]:
        with self._lock:
            values = list(self.manual_tasks.values())
            if status:
                values = [item for item in values if item.status.value == status]
            return deepcopy(values)

    def add_outbox(self, event: OutboxEvent) -> None:
        with self._lock:
            self.outbox[event.id] = deepcopy(event)

    def save_run_with_outbox(self, run: AgentRun, events: List[OutboxEvent]) -> AgentRun:
        with self._lock:
            for event in events:
                self.outbox[event.id] = deepcopy(event)
            return self.save_run(run, expected_version=run.state_version)

    def save_handoff(self, run: AgentRun, task: ManualTask) -> AgentRun:
        with self._lock:
            self.manual_tasks[task.id] = deepcopy(task)
            return self.save_run(run, expected_version=run.state_version)

    def save_return_to_agent(self, run: AgentRun, task: ManualTask) -> AgentRun:
        with self._lock:
            self.manual_tasks[task.id] = deepcopy(task)
            return self.save_run(run, expected_version=run.state_version)

    def save_outbox(self, event: OutboxEvent) -> None:
        with self._lock:
            self.outbox[event.id] = deepcopy(event)

    def pending_outbox(self) -> List[OutboxEvent]:
        with self._lock:
            return deepcopy([e for e in self.outbox.values() if e.status.value != "SUCCEEDED"])

    def list_outbox(self, run_id: Optional[str] = None) -> List[OutboxEvent]:
        with self._lock:
            values = list(self.outbox.values())
            if run_id:
                values = [value for value in values if value.run_id == run_id]
            return deepcopy(values)

    def get_command_result(self, key: str):
        with self._lock:
            return deepcopy(self.command_results.get(key))

    def save_command_result(self, key: str, result: object) -> None:
        with self._lock:
            self.command_results[key] = deepcopy(result)
