import pytest

from patient_ops_agent.llm import FakeUnderstandingProvider, UnderstandingRequest


@pytest.mark.asyncio
async def test_fake_provider_is_deterministic(appointment_understanding):
    provider = FakeUnderstandingProvider(appointment_understanding)

    result = await provider.understand(UnderstandingRequest(message="我想预约明天下午洗牙"))

    assert result == appointment_understanding
    assert len(provider.requests) == 1
    assert provider.requests[0].prompt_version == "understanding-v1"
