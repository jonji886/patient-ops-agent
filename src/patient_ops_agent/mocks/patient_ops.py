"""Synthetic Patient Ops Platform service."""

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, Header

from .errors import api_error
from .fixtures import load_fixtures
from .persistence import DocumentStore


class PatientOpsData:
    def __init__(self, fixtures: Optional[Dict[str, Any]] = None, database_url: Optional[str] = None) -> None:
        self.persistence = DocumentStore(database_url, "patient_ops") if database_url else None
        saved = self.persistence.load() if self.persistence else None
        data = saved or fixtures or load_fixtures()
        patients = data["patients"].values() if isinstance(data["patients"], dict) else data["patients"]
        self.patients = {item["id"]: deepcopy(item) for item in patients}
        self.results: Dict[str, Dict[str, Any]] = deepcopy(data.get("results", {}))
        self.operations: Dict[str, Dict[str, Any]] = deepcopy(data.get("operations", {}))
        self.fail_writeback_attempts = 0
        if self.persistence and not saved: self.persist()

    def persist(self) -> None:
        if self.persistence:
            self.persistence.save({"patients": self.patients, "results": self.results,
                                   "operations": self.operations})


def create_patient_ops_app(data: Optional[PatientOpsData] = None) -> FastAPI:
    state = data or PatientOpsData()
    app = FastAPI(title="Patient Ops Platform Mock API", version="0.1.0")
    app.state.data = state

    @app.get("/health")
    async def health(): return {"status": "ok"}

    @app.get("/api/v1/patients/{patient_id}/context")
    async def context(patient_id: str):
        patient = state.patients.get(patient_id)
        if not patient:
            return api_error(404, "PATIENT_NOT_FOUND", "patient not found")
        return {"patient_id": patient["id"], "display_name": patient["display_name"],
                "preferred_channel": patient["preferred_channel"], "status": patient["status"]}

    @app.get("/api/v1/patients/{patient_id}/facts")
    async def facts(patient_id: str):
        patient = state.patients.get(patient_id)
        if not patient: return api_error(404, "PATIENT_NOT_FOUND", "patient not found")
        return [{**item, "patient_id": patient_id} for item in patient["facts"]]

    @app.get("/api/v1/patients/{patient_id}/contact-consents/{channel}")
    async def consent(patient_id: str, channel: str):
        patient = state.patients.get(patient_id)
        if not patient: return api_error(404, "PATIENT_NOT_FOUND", "patient not found")
        item = next((x for x in patient["contact_consents"] if x["channel"] == channel), None)
        return {**item, "patient_id": patient_id} if item else {"patient_id": patient_id, "channel": channel, "allowed": False}

    @app.get("/api/v1/patients/{patient_id}/next-best-actions")
    async def nbas(patient_id: str):
        patient = state.patients.get(patient_id)
        if not patient: return api_error(404, "PATIENT_NOT_FOUND", "patient not found")
        return [{**item, "patient_id": patient_id} for item in patient["next_best_actions"]]

    @app.post("/api/v1/agent-results")
    async def write_result(body: Dict[str, Any], idempotency_key: Optional[str] = Header(None)):
        if not idempotency_key: return api_error(400, "INVALID_REQUEST", "Idempotency-Key is required")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        prior = state.results.get(idempotency_key)
        if prior:
            if prior["hash"] != digest:
                return api_error(409, "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST", "idempotency key conflict")
            return {**prior["response"], "idempotent_replay": True}
        if state.fail_writeback_attempts > 0:
            state.fail_writeback_attempts -= 1
            return api_error(503, "UPSTREAM_UNAVAILABLE", "synthetic writeback failure", True)
        response = {**body, "result_id": f"RES-{uuid4().hex[:8]}", "idempotent_replay": False}
        state.results[idempotency_key] = {"hash": digest, "response": response}
        state.operations[body["operation_id"]] = {"operation_id": body["operation_id"], "status": "SUCCEEDED",
            "outcome": "EXECUTED", "business_id": response["result_id"], "response_snapshot": response}
        state.persist()
        return response

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(operation_id: str):
        return state.operations.get(operation_id) or api_error(404, "APPOINTMENT_NOT_FOUND", "operation not found")

    return app
