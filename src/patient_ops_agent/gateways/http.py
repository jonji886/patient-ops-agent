"""Validated HTTP gateways. Workflow code never builds HTTP requests."""

from typing import Any, Dict, List, Optional

import httpx

from patient_ops_agent.models import Appointment, OperationResult, Slot


class GatewayError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, outcome: str = "NOT_EXECUTED") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.outcome = outcome


def _raise(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        detail = response.json()["error"]
        raise GatewayError(detail["code"], detail["message"], detail["retryable"], detail["outcome"])
    except (KeyError, TypeError, ValueError):
        raise GatewayError("UPSTREAM_UNAVAILABLE", f"invalid upstream response: {response.status_code}", True)


class PatientOpsGateway:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def context(self, patient_id: str) -> Dict[str, Any]:
        response = await self.client.get(f"/api/v1/patients/{patient_id}/context")
        _raise(response); return response.json()

    async def consent(self, patient_id: str, channel: str) -> Dict[str, Any]:
        response = await self.client.get(f"/api/v1/patients/{patient_id}/contact-consents/{channel}")
        _raise(response); return response.json()

    async def writeback(self, payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/agent-results", json=payload, headers={"Idempotency-Key": key})
        _raise(response); return response.json()


class ClinicCoreGateway:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def clinics(self) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/clinics"); _raise(response); return response.json()

    async def service_items(self) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/service-items"); _raise(response); return response.json()

    async def doctors(self, clinic_id: Optional[str] = None) -> List[Dict[str, Any]]:
        response = await self.client.get("/api/v1/doctors", params={"clinic_id": clinic_id} if clinic_id else None)
        _raise(response); return response.json()

    async def search_slots(self, **params: Any) -> List[Slot]:
        response = await self.client.get("/api/v1/slots", params={k: v for k, v in params.items() if v is not None})
        _raise(response); return [Slot.model_validate(item) for item in response.json()]

    async def patient_appointments(self, patient_id: str) -> List[Appointment]:
        response = await self.client.get(f"/api/v1/patients/{patient_id}/appointments", params={"future_only": True})
        _raise(response); return [Appointment.model_validate(item) for item in response.json()]

    async def appointment(self, appointment_id: str) -> Appointment:
        response = await self.client.get(f"/api/v1/appointments/{appointment_id}")
        _raise(response); return Appointment.model_validate(response.json())

    async def create_appointment(self, payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        response = await self.client.post("/api/v1/appointments", json=payload, headers={"Idempotency-Key": key})
        _raise(response); return response.json()

    async def cancel_appointment(self, appointment_id: str, payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        response = await self.client.post(f"/api/v1/appointments/{appointment_id}/cancel", json=payload,
                                          headers={"Idempotency-Key": key})
        _raise(response); return response.json()

    async def operation(self, operation_id: str) -> OperationResult:
        response = await self.client.get(f"/api/v1/operations/{operation_id}")
        _raise(response); return OperationResult.model_validate(response.json())
