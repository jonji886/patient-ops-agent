"""DeepSeek JSON-output adapter with strict Pydantic validation."""

import json

import httpx

from patient_ops_agent.models import UnderstandingResult

from .ports import UnderstandingProvider, UnderstandingRequest


class DeepSeekUnderstandingProvider(UnderstandingProvider):
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def understand(self, request: UnderstandingRequest) -> UnderstandingResult:
        schema = UnderstandingResult.model_json_schema()
        system = (
            "你只负责理解患者预约意图，不具备执行权限。严格返回符合以下 JSON Schema 的对象："
            + json.dumps(schema, ensure_ascii=False)
            + "。当前 Run 的已解析预约约束如下；它们仅用于理解追问，不是执行授权："
            + json.dumps(request.current_fields, ensure_ascii=False, default=str)
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": request.message},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return UnderstandingResult.model_validate_json(content)
