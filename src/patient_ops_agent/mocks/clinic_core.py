"""Clinic Core synthetic service with atomic slot booking and idempotency."""

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime
from threading import RLock
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse

from patient_ops_agent.demo import FailureInjector

from .errors import api_error
from .fixtures import load_fixtures
from .persistence import DocumentStore


class ClinicCoreData:
    def __init__(self, fixtures: Optional[Dict[str, Any]] = None, database_url: Optional[str] = None,
                 failure_injector: Optional[FailureInjector] = None) -> None:
        self.persistence = DocumentStore(database_url, "clinic_core") if database_url else None
        saved = self.persistence.load() if self.persistence else None
        catalog = fixtures or load_fixtures()
        data = self._merge_catalog(saved, catalog) if saved else catalog
        self.lock = RLock()
        self.clinics = deepcopy(data["clinics"])
        self.service_items = deepcopy(data["service_items"])
        self.doctors = deepcopy(data["doctors"])
        slots = data["slots"].values() if isinstance(data["slots"], dict) else data["slots"]
        appointments = data["appointments"].values() if isinstance(data["appointments"], dict) else data["appointments"]
        self.slots = {item["id"]: deepcopy(item) for item in slots}
        self.appointments = {item["id"]: deepcopy(item) for item in appointments}
        self.operations: Dict[str, Dict[str, Any]] = deepcopy(data.get("operations", {}))
        self.idempotency: Dict[str, Dict[str, Any]] = deepcopy(data.get("idempotency", {}))
        self.failure_injector = failure_injector
        self.timeout_after_commit_once = False
        self.unavailable_attempts = 0
        if self.persistence and (not saved or data != saved): self.persist()

    @staticmethod
    def _merge_catalog(saved: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
        """Append newly shipped synthetic catalog records without rewriting runtime state."""

        merged = deepcopy(saved)
        for collection in ("clinics", "service_items", "doctors"):
            existing = {item["id"]: item for item in merged.get(collection, [])}
            for item in catalog.get(collection, []):
                current = existing.get(item["id"])
                if current is None:
                    merged.setdefault(collection, []).append(deepcopy(item))
                    existing[item["id"]] = merged[collection][-1]
                elif collection == "doctors":
                    current["service_item_ids"] = list(dict.fromkeys(
                        [*current.get("service_item_ids", []), *item.get("service_item_ids", [])]
                    ))

        existing_slots = merged.get("slots", {})
        slot_map = existing_slots if isinstance(existing_slots, dict) else {item["id"]: item for item in existing_slots}
        for slot in catalog.get("slots", []):
            slot_map.setdefault(slot["id"], deepcopy(slot))
        merged["slots"] = slot_map
        return merged

    def persist(self) -> None:
        if self.persistence:
            self.persistence.save({"clinics": self.clinics, "service_items": self.service_items,
                "doctors": self.doctors, "slots": self.slots, "appointments": self.appointments,
                "operations": self.operations, "idempotency": self.idempotency})

    @staticmethod
    def request_hash(body: Dict[str, Any]) -> str:
        raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()
        return hashlib.sha256(raw).hexdigest()


def create_clinic_core_app(data: Optional[ClinicCoreData] = None) -> FastAPI:
    state = data or ClinicCoreData()
    app = FastAPI(title="Clinic Core Mock API", version="0.1.0")
    app.state.data = state

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/clinics")
    async def clinics():
        return [item for item in state.clinics if item["status"] == "ACTIVE"]

    @app.get("/api/v1/service-items")
    async def service_items(clinic_id: Optional[str] = None):
        return [item for item in state.service_items if item["status"] == "ACTIVE"]

    @app.get("/api/v1/doctors")
    async def doctors(clinic_id: Optional[str] = None):
        return [item for item in state.doctors if not clinic_id or item["clinic_id"] == clinic_id]

    @app.get("/api/v1/slots")
    async def slots(
        service_item_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        clinic_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        period: Optional[str] = Query(default=None),
    ):
        end = end_date or start_date
        result = []
        for slot in state.slots.values():
            start = datetime.fromisoformat(str(slot["start_at"]))
            hour = start.hour
            matching_period = not period or (
                (period == "MORNING" and hour < 12)
                or (period == "AFTERNOON" and 12 <= hour < 18)
                or (period == "EVENING" and hour >= 18)
            )
            if (
                slot["status"] == "AVAILABLE"
                and slot["service_item_id"] == service_item_id
                and start_date <= start.date() <= end
                and (not clinic_id or slot["clinic_id"] == clinic_id)
                and (not doctor_id or slot["doctor_id"] == doctor_id)
                and matching_period
            ):
                result.append(slot)
        return result

    @app.get("/api/v1/patients/{patient_id}/appointments")
    async def patient_appointments(patient_id: str, future_only: bool = True):
        return [
            _appointment_view(item, state)
            for item in state.appointments.values()
            if item["patient_id"] == patient_id and item["status"] == "CONFIRMED"
        ]

    @app.get("/api/v1/appointments/{appointment_id}")
    async def appointment(appointment_id: str):
        item = state.appointments.get(appointment_id)
        return _appointment_view(item, state) if item else api_error(404, "APPOINTMENT_NOT_FOUND", "appointment not found")

    @app.post("/api/v1/appointments")
    async def create_appointment(body: Dict[str, Any], idempotency_key: Optional[str] = Header(None)):
        if not idempotency_key:
            return api_error(400, "INVALID_REQUEST", "Idempotency-Key is required")
        request_hash = state.request_hash(body)
        with state.lock:
            prior = state.idempotency.get(idempotency_key)
            if prior:
                if prior["request_hash"] != request_hash:
                    return api_error(409, "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST", "idempotency key conflict")
                result = deepcopy(prior["response"])
                result["idempotent_replay"] = True
                return JSONResponse(status_code=200, content=result, headers={"Idempotent-Replay": "true"})
            if state.failure_injector and state.failure_injector.consume("clinic.create_failure"):
                return api_error(503, "UPSTREAM_UNAVAILABLE", "synthetic scenario outage", True)
            if state.unavailable_attempts > 0:
                state.unavailable_attempts -= 1
                return api_error(503, "UPSTREAM_UNAVAILABLE", "synthetic outage", True)
            slot = state.slots.get(body.get("slot_id"))
            if not slot:
                return api_error(404, "SLOT_NOT_FOUND", "slot not found")
            if state.failure_injector and state.failure_injector.consume("clinic.slot_conflict"):
                slot["status"] = "BOOKED"
                slot["version"] += 1
                state.persist()
                return api_error(409, "SLOT_OCCUPIED", "slot was occupied by a concurrent request")
            if slot["status"] != "AVAILABLE":
                return api_error(409, "SLOT_OCCUPIED", "slot is occupied")
            if slot["version"] != body.get("expected_slot_version"):
                return api_error(409, "SLOT_VERSION_CONFLICT", "slot version changed")
            if any(slot[k] != body.get(k) for k in ("clinic_id", "service_item_id", "doctor_id")):
                return api_error(400, "INVALID_REQUEST", "slot parameters do not match")
            appointment_id = f"A-{uuid4().hex[:10].upper()}"
            now = datetime.now().astimezone().isoformat()
            item = {
                "id": appointment_id,
                "patient_id": body["patient_id"],
                "clinic_id": body["clinic_id"],
                "service_item_id": body["service_item_id"],
                "doctor_id": body["doctor_id"],
                "slot_id": body["slot_id"],
                "status": "CONFIRMED",
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            state.appointments[appointment_id] = item
            slot["status"] = "BOOKED"
            slot["version"] += 1
            response = {
                "operation_id": body["operation_id"],
                "appointment_id": appointment_id,
                "status": "CONFIRMED",
                "slot_id": slot["id"],
                "appointment_version": 1,
                "idempotent_replay": False,
            }
            state.idempotency[idempotency_key] = {"request_hash": request_hash, "response": response}
            state.operations[body["operation_id"]] = {
                "operation_id": body["operation_id"], "status": "SUCCEEDED", "outcome": "EXECUTED",
                "business_id": appointment_id, "response_snapshot": response,
            }
            state.persist()
            injected_timeout = state.failure_injector and state.failure_injector.consume("clinic.commit_timeout")
            if state.timeout_after_commit_once or injected_timeout:
                state.timeout_after_commit_once = False
                return api_error(504, "TIMEOUT", "response lost after commit", True, "UNKNOWN")
            return JSONResponse(status_code=201, content=response)

    @app.post("/api/v1/appointments/{appointment_id}/cancel")
    async def cancel_appointment(appointment_id: str, body: Dict[str, Any], idempotency_key: Optional[str] = Header(None)):
        if not idempotency_key:
            return api_error(400, "INVALID_REQUEST", "Idempotency-Key is required")
        request_hash = state.request_hash(body)
        with state.lock:
            prior = state.idempotency.get(idempotency_key)
            if prior:
                if prior["request_hash"] != request_hash:
                    return api_error(409, "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST", "idempotency key conflict")
                result = deepcopy(prior["response"]); result["idempotent_replay"] = True
                return result
            item = state.appointments.get(appointment_id)
            if not item:
                return api_error(404, "APPOINTMENT_NOT_FOUND", "appointment not found")
            if item["patient_id"] != body.get("patient_id"):
                return api_error(403, "FORBIDDEN", "appointment does not belong to patient")
            if item["version"] != body.get("expected_appointment_version"):
                return api_error(409, "STATE_VERSION_CONFLICT", "appointment version changed")
            item["status"] = "CANCELLED"; item["version"] += 1
            item["updated_at"] = datetime.now().astimezone().isoformat()
            response = {"operation_id": body["operation_id"], "appointment_id": appointment_id,
                        "status": "CANCELLED", "appointment_version": item["version"], "idempotent_replay": False}
            state.idempotency[idempotency_key] = {"request_hash": request_hash, "response": response}
            state.operations[body["operation_id"]] = {"operation_id": body["operation_id"], "status": "SUCCEEDED",
                "outcome": "EXECUTED", "business_id": appointment_id, "response_snapshot": response}
            state.persist()
            return response

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(operation_id: str):
        result = state.operations.get(operation_id)
        return result if result else api_error(404, "APPOINTMENT_NOT_FOUND", "operation not found")

    return app


def _appointment_view(item: Dict[str, Any], state: ClinicCoreData) -> Dict[str, Any]:
    result = deepcopy(item)
    slot = state.slots.get(item["slot_id"])
    if slot:
        result["start_at"] = slot["start_at"]
        result["end_at"] = slot["end_at"]
    clinic = next((record for record in state.clinics if record["id"] == item["clinic_id"]), None)
    service_item = next((record for record in state.service_items if record["id"] == item["service_item_id"]), None)
    doctor = next((record for record in state.doctors if record["id"] == item["doctor_id"]), None)
    result["clinic_name"] = clinic["name"] if clinic else None
    result["service_item_name"] = service_item["name"] if service_item else None
    result["doctor_name"] = doctor["name"] if doctor else None
    return result
