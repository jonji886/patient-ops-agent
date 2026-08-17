"""SQL persistence for SQLite development and PostgreSQL deployment.

SQLite is a single-machine development profile. PostgreSQL remains the
deployment profile for real row locks and multi-process worker semantics.
"""

import json
from pathlib import Path
from typing import List, Optional, Type, TypeVar

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from patient_ops_agent.domain.models import (
    AgentRun,
    ConfirmationRecord,
    Conversation,
    ManualTask,
    OutboxEvent,
    ToolExecution,
    TraceEvent,
)
from patient_ops_agent.domain.store import InMemoryStore, StateVersionConflict

T = TypeVar("T")


def _payload(value) -> str:
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json()
    return json.dumps(value, ensure_ascii=False, default=str)


def _model(model: Type[T], value) -> T:
    return model.model_validate_json(value) if isinstance(value, str) else model.model_validate(value)


def _sqlite_path(database_url: str) -> Optional[Path]:
    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        return None
    return Path(database_url.removeprefix("sqlite:///"))


class SqlStore(InMemoryStore):
    """Repository surface shared by the workflow, worker, and API."""

    def __init__(self, database_url: str) -> None:
        path = _sqlite_path(database_url)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
        is_sqlite = database_url.startswith("sqlite")
        self.engine = create_engine(
            database_url,
            pool_pre_ping=not is_sqlite,
            connect_args={"check_same_thread": False, "timeout": 10} if is_sqlite else {},
        )
        self.is_sqlite = self.engine.dialect.name == "sqlite"
        self.prefix = "" if self.is_sqlite else "agent_ops."
        if self.is_sqlite:
            self._create_sqlite_tables()

    def add_conversation(self, value: Conversation) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {self._table('conversations')}(id, actor_id, patient_id, created_at, payload) "
                    f"VALUES (:id,:actor,:patient,:created,{self._json(':payload')})"
                ),
                {"id": value.id, "actor": value.actor_id, "patient": value.patient_id,
                 "created": value.created_at, "payload": _payload(value)},
            )

    def get_conversation(self, value_id: str) -> Optional[Conversation]:
        return self._get("conversations", value_id, Conversation)

    def save_run(self, run: AgentRun, expected_version: Optional[int] = None) -> AgentRun:
        with self.engine.begin() as conn:
            lock = " FOR UPDATE" if not self.is_sqlite else ""
            row = conn.execute(
                text(f"SELECT state_version FROM {self._table('agent_runs')} WHERE id=:id{lock}"),
                {"id": run.id},
            ).first()
            if row is None:
                run.state_version = 0
                conn.execute(
                    text(
                        f"INSERT INTO {self._table('agent_runs')} "
                        f"(id,conversation_id,patient_id,state_version,started_at,payload) "
                        f"VALUES (:id,:conversation,:patient,0,:started,{self._json(':payload')})"
                    ),
                    {"id": run.id, "conversation": run.conversation_id, "patient": run.patient_id,
                     "started": run.started_at, "payload": _payload(run)},
                )
            else:
                current = int(row[0])
                if expected_version is not None and current != expected_version:
                    raise StateVersionConflict(run.id)
                run.state_version = current + 1
                result = conn.execute(
                    text(
                        f"UPDATE {self._table('agent_runs')} SET state_version=:version,"
                        f"payload={self._json(':payload')} WHERE id=:id AND state_version=:current"
                    ),
                    {"id": run.id, "version": run.state_version, "current": current,
                     "payload": _payload(run)},
                )
                if result.rowcount != 1:
                    raise StateVersionConflict(run.id)
        return run.model_copy(deep=True)

    def get_run(self, value_id: str) -> Optional[AgentRun]:
        return self._get("agent_runs", value_id, AgentRun)

    def list_runs(self) -> List[AgentRun]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT payload FROM {self._table('agent_runs')} ORDER BY started_at DESC")
            ).all()
        return [_model(AgentRun, row[0]) for row in rows]

    def latest_run(self, conversation_id: str) -> Optional[AgentRun]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT payload FROM {self._table('agent_runs')} "
                    "WHERE conversation_id=:id ORDER BY started_at DESC LIMIT 1"
                ),
                {"id": conversation_id},
            ).first()
        return _model(AgentRun, row[0]) if row else None

    def add_confirmation(self, value: ConfirmationRecord) -> None:
        self._upsert("confirmations", value.id, value)

    def get_confirmation(self, value_id: str) -> Optional[ConfirmationRecord]:
        return self._get("confirmations", value_id, ConfirmationRecord)

    def save_confirmation(self, value: ConfirmationRecord) -> None:
        self._upsert("confirmations", value.id, value)

    def add_manual_task(self, value: ManualTask) -> None:
        self._upsert("manual_tasks", value.id, value)

    def get_manual_task(self, value_id: str) -> Optional[ManualTask]:
        return self._get("manual_tasks", value_id, ManualTask)

    def save_manual_task(self, value: ManualTask) -> None:
        self._upsert("manual_tasks", value.id, value)

    def add_outbox(self, value: OutboxEvent) -> None:
        self._upsert("outbox_events", value.id, value)

    def save_outbox(self, value: OutboxEvent) -> None:
        self._upsert("outbox_events", value.id, value)

    def save_run_with_outbox(self, run: AgentRun, events: List[OutboxEvent]) -> AgentRun:
        with self.engine.begin() as conn:
            self._update_run_in_transaction(conn, run)
            for event in events:
                conn.execute(
                    text(
                        f"INSERT INTO {self._table('outbox_events')}(id,payload) "
                        f"VALUES (:id,{self._json(':payload')})"
                    ),
                    {"id": event.id, "payload": _payload(event)},
                )
        return run.model_copy(deep=True)

    def save_handoff(self, run: AgentRun, task: ManualTask) -> AgentRun:
        with self.engine.begin() as conn:
            self._update_run_in_transaction(conn, run)
            conn.execute(
                text(
                    f"INSERT INTO {self._table('manual_tasks')}(id,payload) "
                    f"VALUES (:id,{self._json(':payload')})"
                ),
                {"id": task.id, "payload": _payload(task)},
            )
        return run.model_copy(deep=True)

    def save_return_to_agent(self, run: AgentRun, task: ManualTask) -> AgentRun:
        with self.engine.begin() as conn:
            self._update_run_in_transaction(conn, run)
            conn.execute(
                text(
                    f"UPDATE {self._table('manual_tasks')} SET payload={self._json(':payload')} WHERE id=:id"
                ),
                {"id": task.id, "payload": _payload(task)},
            )
        return run.model_copy(deep=True)

    def add_trace(self, run_id: str, value: TraceEvent) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {self._table('trace_events')}(run_id,payload) "
                    f"VALUES (:run,{self._json(':payload')})"
                ),
                {"run": run_id, "payload": _payload(value)},
            )

    def get_trace(self, run_id: str) -> List[TraceEvent]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT payload FROM {self._table('trace_events')} WHERE run_id=:run ORDER BY seq"),
                {"run": run_id},
            ).all()
        return [_model(TraceEvent, row[0]) for row in rows]

    def add_tool_execution(self, value: ToolExecution) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {self._table('tool_executions')}(id,run_id,operation_id,payload) "
                    f"VALUES (:id,:run,:operation,{self._json(':payload')})"
                ),
                {"id": value.id, "run": value.run_id, "operation": value.operation_id,
                 "payload": _payload(value)},
            )

    def list_manual_tasks(self, status: Optional[str] = None) -> List[ManualTask]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT payload FROM {self._table('manual_tasks')}")).all()
        values = [_model(ManualTask, row[0]) for row in rows]
        return [value for value in values if not status or value.status.value == status]

    def pending_outbox(self) -> List[OutboxEvent]:
        return [value for value in self.list_outbox() if value.status.value != "SUCCEEDED"]

    def list_outbox(self, run_id: Optional[str] = None) -> List[OutboxEvent]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT payload FROM {self._table('outbox_events')}")).all()
        values = [_model(OutboxEvent, row[0]) for row in rows]
        return [value for value in values if not run_id or value.run_id == run_id]

    def get_command_result(self, key: str):
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT payload FROM {self._table('command_results')} WHERE key=:key"), {"key": key}
            ).first()
        if not row:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]

    def save_command_result(self, key: str, result: object) -> None:
        with self.engine.begin() as conn:
            if self.is_sqlite:
                statement = (
                    f"INSERT INTO {self._table('command_results')}(key,payload) VALUES (:key,:payload) "
                    "ON CONFLICT(key) DO NOTHING"
                )
            else:
                statement = (
                    f"INSERT INTO {self._table('command_results')}(key,payload) "
                    "VALUES (:key,CAST(:payload AS JSONB)) ON CONFLICT(key) DO NOTHING"
                )
            conn.execute(text(statement), {"key": key, "payload": _payload(result)})

    def dispose(self) -> None:
        self.engine.dispose()

    def _get(self, table: str, value_id: str, model: Type[T]) -> Optional[T]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT payload FROM {self._table(table)} WHERE id=:id"), {"id": value_id}
            ).first()
        return _model(model, row[0]) if row else None

    def _upsert(self, table: str, value_id: str, value) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {self._table(table)}(id,payload) VALUES (:id,{self._json(':payload')}) "
                    "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload"
                ),
                {"id": value_id, "payload": _payload(value)},
            )

    def _update_run_in_transaction(self, conn: Connection, run: AgentRun) -> None:
        current = run.state_version
        run.state_version += 1
        result = conn.execute(
            text(
                f"UPDATE {self._table('agent_runs')} SET state_version=:version,"
                f"payload={self._json(':payload')} WHERE id=:id AND state_version=:current"
            ),
            {"id": run.id, "version": run.state_version, "current": current,
             "payload": _payload(run)},
        )
        if result.rowcount != 1:
            run.state_version = current
            raise StateVersionConflict(run.id)

    def _table(self, name: str) -> str:
        return f"agent_ops_{name}" if self.is_sqlite else f"agent_ops.{name}"

    def _json(self, value: str) -> str:
        return value if self.is_sqlite else f"CAST({value} AS JSONB)"

    def _create_sqlite_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS agent_ops_conversations (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, patient_id TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS agent_ops_agent_runs (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, patient_id TEXT NOT NULL,
                state_version INTEGER NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS agent_runs_conversation_started_idx ON agent_ops_agent_runs(conversation_id, started_at DESC)",
            "CREATE TABLE IF NOT EXISTS agent_ops_confirmations (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS agent_ops_manual_tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS agent_ops_outbox_events (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
            """CREATE TABLE IF NOT EXISTS agent_ops_trace_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, payload TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS agent_ops_tool_executions (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, operation_id TEXT, payload TEXT NOT NULL)""",
            "CREATE TABLE IF NOT EXISTS agent_ops_command_results (key TEXT PRIMARY KEY, payload TEXT NOT NULL)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))


class PostgresStore(SqlStore):
    """Explicit PostgreSQL deployment store."""

    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite"):
            raise ValueError("PostgresStore requires a PostgreSQL database URL")
        super().__init__(database_url)


class SQLiteStore(SqlStore):
    """Single-machine SQLite development store."""

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite"):
            raise ValueError("SQLiteStore requires a sqlite database URL")
        super().__init__(database_url)
