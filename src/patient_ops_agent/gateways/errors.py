"""Unified integration error model and fault injection configuration.

Design principle:
    External system raw errors must NOT leak to the Agent layer.
    All external failures are mapped to a small set of domain-level
    IntegrationError subclasses, which the Workflow / Skill policy can
    reason about deterministically.

Error hierarchy:

    IntegrationError (base)
    ├── ExternalTimeout        — request timed out; outcome may be UNKNOWN
    ├── ExternalUnavailable    — service is down or circuit is open
    ├── RateLimited            — upstream returned 429 / rate limit
    ├── Unauthorized           — credentials rejected (not patient-level FORBIDDEN)
    ├── InvalidResponse        — response schema mismatch
    └── BusinessConflict       — e.g. SLOT_VERSION_CONFLICT (mapped from GatewayError)

Relationship to existing GatewayError:
    GatewayError remains the internal exception used by Gateway methods.
    ``map_gateway_error`` converts it to the appropriate IntegrationError
    subclass for higher layers. This avoids having two parallel error
    systems — GatewayError is the transport-level detail; IntegrationError
    is the domain-level abstraction.
"""

from dataclasses import dataclass
from typing import Optional


class IntegrationError(Exception):
    """Base class for all external-system integration failures."""

    def __init__(self, code: str, message: str, retryable: bool = False,
                 outcome: str = "NOT_EXECUTED", circuit: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.outcome = outcome
        self.circuit = circuit

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} (retryable={self.retryable}, outcome={self.outcome})"


class ExternalTimeout(IntegrationError):
    """Request timed out. Outcome is UNKNOWN for write operations."""

    def __init__(self, message: str = "external request timed out", circuit: Optional[str] = None) -> None:
        super().__init__("TIMEOUT", message, retryable=True, outcome="UNKNOWN", circuit=circuit)


class ExternalUnavailable(IntegrationError):
    """Service is down, returned 5xx, or circuit breaker is open."""

    def __init__(self, message: str = "external service unavailable", circuit: Optional[str] = None,
                 outcome: str = "NOT_EXECUTED") -> None:
        super().__init__("UPSTREAM_UNAVAILABLE", message, retryable=True, outcome=outcome, circuit=circuit)


class RateLimited(IntegrationError):
    """Upstream returned 429 or equivalent rate-limit signal."""

    def __init__(self, message: str = "rate limited by upstream", circuit: Optional[str] = None) -> None:
        super().__init__("RATE_LIMITED", message, retryable=True, outcome="NOT_EXECUTED", circuit=circuit)


class Unauthorized(IntegrationError):
    """Credentials or service-level auth rejected (not patient-level FORBIDDEN)."""

    def __init__(self, message: str = "service authentication failed", circuit: Optional[str] = None) -> None:
        super().__init__("UNAUTHENTICATED", message, retryable=False, outcome="NOT_EXECUTED", circuit=circuit)


class InvalidResponse(IntegrationError):
    """Response could not be parsed or did not match expected schema."""

    def __init__(self, message: str = "invalid upstream response", circuit: Optional[str] = None) -> None:
        super().__init__("INVALID_RESPONSE", message, retryable=False, outcome="UNKNOWN", circuit=circuit)


class BusinessConflict(IntegrationError):
    """Upstream returned a business-level conflict (e.g. SLOT_VERSION_CONFLICT)."""

    def __init__(self, code: str, message: str, retryable: bool = False,
                 outcome: str = "NOT_EXECUTED", circuit: Optional[str] = None) -> None:
        super().__init__(code, message, retryable=retryable, outcome=outcome, circuit=circuit)


def map_gateway_error(code: str, message: str, retryable: bool, outcome: str,
                      circuit: Optional[str] = None) -> IntegrationError:
    """Map a transport-level error code to a domain-level IntegrationError.

    This is the single mapping point. The Workflow catches GatewayError,
    calls this function, and receives a typed IntegrationError.
    """
    if code == "TIMEOUT":
        return ExternalTimeout(message, circuit)
    if code in ("UPSTREAM_UNAVAILABLE", "INTERNAL_ERROR"):
        return ExternalUnavailable(message, circuit, outcome)
    if code == "RATE_LIMITED":
        return RateLimited(message, circuit)
    if code == "UNAUTHENTICATED":
        return Unauthorized(message, circuit)
    if code == "INVALID_RESPONSE":
        return InvalidResponse(message, circuit)
    return BusinessConflict(code, message, retryable, outcome, circuit)


@dataclass
class FaultInjectionConfig:
    """Deterministic fault injection for external service simulation.

    Controlled by environment variables:
        MOCK_CLINIC_CORE_LATENCY_MS   — artificial delay (0 = disabled)
        MOCK_CLINIC_CORE_FAILURE_RATE — 0.0 to 1.0 probability of failure
        MOCK_PATIENT_OPS_LATENCY_MS
        MOCK_PATIENT_OPS_FAILURE_RATE

    For deterministic tests, set failure_rate=1.0 and latency_ms=0 and use
    the failure_count mechanism in ClinicCoreData instead of random.

    Random failure is disabled by default. Tests should use the explicit
    fault-injection hooks (timeout_after_commit_once, unavailable_attempts)
    rather than probabilistic config, to avoid CI flakiness.
    """

    clinic_core_latency_ms: int = 0
    clinic_core_failure_rate: float = 0.0
    patient_ops_latency_ms: int = 0
    patient_ops_failure_rate: float = 0.0

    @property
    def clinic_core_faults_enabled(self) -> bool:
        return self.clinic_core_latency_ms > 0 or self.clinic_core_failure_rate > 0

    @property
    def patient_ops_faults_enabled(self) -> bool:
        return self.patient_ops_latency_ms > 0 or self.patient_ops_failure_rate > 0
