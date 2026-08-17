"""Provider boundary; concrete LLM SDKs must remain behind this port."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from patient_ops_agent.models import UnderstandingResult


@dataclass(frozen=True)
class UnderstandingRequest:
    message: str
    current_fields: Mapping[str, object] = field(default_factory=dict)
    prompt_version: str = "understanding-v1"


class UnderstandingProvider(Protocol):
    async def understand(self, request: UnderstandingRequest) -> UnderstandingResult:
        """Return a candidate interpretation; never execute a business Tool."""
