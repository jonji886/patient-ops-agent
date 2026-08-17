from datetime import date

import pytest

from patient_ops_agent.llm import RuleBasedUnderstandingProvider, UnderstandingRequest
from patient_ops_agent.models import Intent


CASES = [
    ("我想预约明天下午洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("明天上午预约口腔检查", "CREATE_APPOINTMENT", "口腔检查", date(2026, 8, 15)),
    ("后天上午找李医生洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 16)),
    ("8月15日下午想约洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("2026-08-15上午口腔检查", "CREATE_APPOINTMENT", "口腔检查", date(2026, 8, 15)),
    ("我想看牙", "CREATE_APPOINTMENT", None, None),
    ("帮我挂号", "CREATE_APPOINTMENT", None, None),
    ("预约张医生", "CREATE_APPOINTMENT", None, None),
    ("今天洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 14)),
    ("明天早上洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("明天午后洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("明天晚上洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("查预约", "QUERY_APPOINTMENT", None, None),
    ("查询预约", "QUERY_APPOINTMENT", None, None),
    ("查询我未来的预约", "QUERY_APPOINTMENT", None, None),
    ("我的预约", "QUERY_APPOINTMENT", None, None),
    ("预约记录", "QUERY_APPOINTMENT", None, None),
    ("帮我取消预约", "CANCEL_APPOINTMENT", None, None),
    ("我想取消我的预约", "CANCEL_APPOINTMENT", None, None),
    ("我要退约", "CANCEL_APPOINTMENT", None, None),
    ("把预约取消掉", "CANCEL_APPOINTMENT", None, None),
    ("算了", "CANCEL_CURRENT_RUN", None, None),
    ("不约了", "CANCEL_CURRENT_RUN", None, None),
    ("停止流程", "CANCEL_CURRENT_RUN", None, None),
    ("我要人工", "REQUEST_HUMAN", None, None),
    ("转接客服", "REQUEST_HUMAN", None, None),
    ("找客服", "REQUEST_HUMAN", None, None),
    ("你好", "UNKNOWN", None, None),
    ("谢谢", "UNKNOWN", None, None),
    ("天气怎么样", "UNKNOWN", None, None),
    ("徐汇门诊明天下午洗牙", "CREATE_APPOINTMENT", "洗牙", date(2026, 8, 15)),
    ("后天早晨口腔检查", "CREATE_APPOINTMENT", "口腔检查", date(2026, 8, 16)),
    ("有哪些日期可约", "QUERY_SLOT_AVAILABILITY", None, None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message,intent,service,requested_date", CASES)
async def test_golden_understanding_cases(sut, message, intent, service, requested_date):
    provider = RuleBasedUnderstandingProvider(sut.clock)
    result = await provider.understand(UnderstandingRequest(message=message))
    assert result.intent is Intent(intent)
    assert result.service_item_text == service
    assert result.requested_date == requested_date
    assert result.proposed_action.value not in {"CREATE_APPOINTMENT", "CANCEL_APPOINTMENT"}
