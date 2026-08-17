"""Deterministic Chinese understanding provider for CI and local demos."""

import re
from datetime import date, timedelta
from typing import Optional

from patient_ops_agent.clock import Clock
from patient_ops_agent.models import (
    Intent,
    ProposedAction,
    RequestedPeriod,
    UnderstandingResult,
)

from .ports import UnderstandingProvider, UnderstandingRequest


class RuleBasedUnderstandingProvider(UnderstandingProvider):
    """A deliberately limited fallback; authority remains in the workflow."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    async def understand(self, request: UnderstandingRequest) -> UnderstandingResult:
        text = request.message.strip()
        intent = self._intent(text)
        service = next((s for s in ("洗牙", "口腔检查") if s in text), None)
        doctor_match = re.search(r"([\u4e00-\u9fff]{1,4}医生)", text)
        clinic = "合成徐汇门诊" if "徐汇" in text else None
        requested_date = self._date(text)
        period = self._period(text)
        missing = []
        if intent is Intent.CREATE_APPOINTMENT:
            if not service:
                missing.append("service_item")
            if not requested_date:
                missing.append("requested_date")
        action = self._action(intent, missing)
        return UnderstandingResult(
            intent=intent,
            service_item_text=service,
            clinic_text=clinic,
            doctor_text=doctor_match.group(1) if doctor_match else None,
            requested_date=requested_date,
            requested_period=period,
            ambiguities=missing,
            confidence=0.99 if intent is not Intent.UNKNOWN else 0.3,
            proposed_action=action,
        )

    def _intent(self, text: str) -> Intent:
        if any(word in text for word in ("人工", "客服", "转接")):
            return Intent.REQUEST_HUMAN
        if any(word in text for word in ("复查", "随访", "回访", "复诊", "该洗牙了", "建议洗牙")):
            return Intent.FOLLOW_UP
        if any(phrase in text for phrase in ("有哪些日期可约", "哪些日期可约", "还有什么时间", "哪些时间可约", "看看可约", "还有号源", "换一天", "换个日期")):
            return Intent.QUERY_SLOT_AVAILABILITY
        if any(word in text for word in ("算了", "不约了", "停止流程")):
            return Intent.CANCEL_CURRENT_RUN
        if (("取消" in text and "预约" in text)
                or any(word in text for word in ("退约", "取消掉"))):
            return Intent.CANCEL_APPOINTMENT
        if ((any(word in text for word in ("查询", "查看")) and "预约" in text)
                or any(word in text for word in ("查预约", "我的预约", "预约记录"))):
            return Intent.QUERY_APPOINTMENT
        if any(word in text for word in ("预约", "想约", "挂号", "看牙", "洗牙", "口腔检查")):
            return Intent.CREATE_APPOINTMENT
        return Intent.UNKNOWN

    def _date(self, text: str) -> Optional[date]:
        today = self.clock.now().date()
        if "后天" in text:
            return today + timedelta(days=2)
        if "明天" in text:
            return today + timedelta(days=1)
        if "今天" in text:
            return today
        match = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})日?", text)
        if match:
            return date(*(int(part) for part in match.groups()))
        match = re.search(r"(\d{1,2})月(\d{1,2})日?", text)
        if match:
            return date(today.year, int(match.group(1)), int(match.group(2)))
        return None

    @staticmethod
    def _period(text: str) -> Optional[RequestedPeriod]:
        if any(word in text for word in ("上午", "早上", "早晨")):
            return RequestedPeriod.MORNING
        if any(word in text for word in ("下午", "午后")):
            return RequestedPeriod.AFTERNOON
        if any(word in text for word in ("晚上", "傍晚")):
            return RequestedPeriod.EVENING
        return None

    @staticmethod
    def _action(intent: Intent, missing: list) -> ProposedAction:
        if intent is Intent.REQUEST_HUMAN:
            return ProposedAction.REQUEST_HUMAN
        if intent in (Intent.QUERY_APPOINTMENT, Intent.CANCEL_APPOINTMENT):
            return ProposedAction.QUERY_APPOINTMENTS
        if intent is Intent.QUERY_SLOT_AVAILABILITY:
            return ProposedAction.SEARCH_ALTERNATIVE_SLOTS
        if intent is Intent.CREATE_APPOINTMENT:
            return ProposedAction.COLLECT_REQUIREMENTS if missing else ProposedAction.SEARCH_SLOTS
        if intent is Intent.FOLLOW_UP:
            return ProposedAction.RECOMMEND_SERVICE
        return ProposedAction.NONE
