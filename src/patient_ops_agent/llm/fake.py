"""Deterministic provider used by unit and workflow tests."""

from patient_ops_agent.models import UnderstandingResult

from .ports import UnderstandingProvider, UnderstandingRequest


class FakeUnderstandingProvider(UnderstandingProvider):
    def __init__(self, result: UnderstandingResult) -> None:
        self.result = result
        self.requests = []

    async def understand(self, request: UnderstandingRequest) -> UnderstandingResult:
        self.requests.append(request)
        return self.result
