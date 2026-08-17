"""Small SQLite/PostgreSQL document store for synthetic mocks."""

import json
from pathlib import Path

from sqlalchemy import create_engine, text


class DocumentStore:
    def __init__(self, database_url: str, schema: str) -> None:
        if schema not in {"clinic_core", "patient_ops"}:
            raise ValueError("invalid schema")
        self.is_sqlite = database_url.startswith("sqlite")
        if self.is_sqlite and database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
            database_path = Path(database_url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            database_url,
            pool_pre_ping=not self.is_sqlite,
            connect_args={"check_same_thread": False, "timeout": 10} if self.is_sqlite else {},
        )
        self.schema = schema
        self.table = f"{schema}_runtime_state" if self.is_sqlite else f"{schema}.runtime_state"
        if self.is_sqlite:
            with self.engine.begin() as conn:
                conn.execute(text(
                    f"CREATE TABLE IF NOT EXISTS {self.table} "
                    "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
                ))

    def load(self):
        with self.engine.connect() as conn:
            row = conn.execute(text(f"SELECT payload FROM {self.table} WHERE id='state'" )).first()
        if not row:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]

    def save(self, payload) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        with self.engine.begin() as conn:
            if self.is_sqlite:
                statement = f"""INSERT INTO {self.table}(id,payload,updated_at)
                    VALUES ('state',:payload,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE
                    SET payload=excluded.payload,updated_at=excluded.updated_at"""
            else:
                statement = f"""INSERT INTO {self.table}(id,payload,updated_at)
                    VALUES ('state',CAST(:payload AS JSONB),now()) ON CONFLICT(id) DO UPDATE
                    SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at"""
            conn.execute(text(statement), {"payload": encoded})
