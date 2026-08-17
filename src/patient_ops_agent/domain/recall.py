"""Deterministic recall eligibility rules.

LLM 不决定患者是否应该被召回。召回资格由确定性代码基于 Patient Facts、
触达许可和已有预约计算。LLM 只负责理解患者回复、日期解析和生成自然语言回复。
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class RecallStatus(str, Enum):
    """召回状态流转，由确定性代码驱动，不可由 LLM 直接修改。"""

    PENDING = "PENDING"
    OUTREACHED = "OUTREACHED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    CONVERTED = "CONVERTED"
    SKIPPED = "SKIPPED"


class RecallEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    SKIP = "SKIP"


@dataclass(frozen=True)
class RecallEligibilityResult:
    """确定性召回资格判定结果。"""

    eligibility: RecallEligibility
    reason_code: str
    recommended_service_item_id: Optional[str] = None
    recommended_service_item_name: Optional[str] = None
    last_cleaning_date: Optional[str] = None
    months_since_last_cleaning: Optional[int] = None
    next_best_action: Optional[str] = None


class RecallEligibilityRule:
    """确定性召回资格规则引擎。

    判定逻辑（全部由确定性代码执行，LLM 不参与）：

    1. 读取 Patient Facts 中的 last_cleaning_date；
    2. 距上次洗牙 >= RECALL_THRESHOLD_MONTHS 个月 → 满足周期条件；
    3. 检查触达许可：不允许触达 → NOT_ELIGIBLE；
    4. 检查已有未来有效预约：存在 → SKIP（防止重复触达）；
    5. 全部通过 → ELIGIBLE，生成 Next Best Action。
    """

    RECALL_THRESHOLD_MONTHS = 5
    RECALL_SERVICE_ITEM_ID = "SV-CLEANING"
    RECALL_SERVICE_ITEM_NAME = "洗牙"
    RECALL_NEXT_BEST_ACTION = "RECOMMEND_DENTAL_CLEANING_REVIEW"

    def evaluate(
        self,
        facts: List[Dict[str, Any]],
        consent: Dict[str, Any],
        existing_appointments: List[Any],
        today: date,
    ) -> RecallEligibilityResult:
        cleaning_fact = next(
            (item for item in facts if item.get("fact_type") == "last_cleaning_date"),
            None,
        )
        if not cleaning_fact or not cleaning_fact.get("value"):
            return RecallEligibilityResult(
                eligibility=RecallEligibility.NOT_ELIGIBLE,
                reason_code="NO_PATIENT_FACTS",
            )

        try:
            last_date = date.fromisoformat(str(cleaning_fact["value"]))
        except (TypeError, ValueError):
            return RecallEligibilityResult(
                eligibility=RecallEligibility.NOT_ELIGIBLE,
                reason_code="INVALID_PATIENT_FACTS",
            )

        months_ago = self._months_between(today, last_date)
        if months_ago < self.RECALL_THRESHOLD_MONTHS:
            return RecallEligibilityResult(
                eligibility=RecallEligibility.NOT_ELIGIBLE,
                reason_code="NOT_YET_DUE",
                last_cleaning_date=last_date.isoformat(),
                months_since_last_cleaning=months_ago,
            )

        if not consent.get("allowed"):
            return RecallEligibilityResult(
                eligibility=RecallEligibility.NOT_ELIGIBLE,
                reason_code="CONTACT_CONSENT_DENIED",
                last_cleaning_date=last_date.isoformat(),
                months_since_last_cleaning=months_ago,
            )

        has_future_appointment = any(
            getattr(apt, "status", None) is not None
            and apt.status.value == "CONFIRMED"
            and getattr(apt, "service_item_id", None) == self.RECALL_SERVICE_ITEM_ID
            for apt in existing_appointments
        )
        if has_future_appointment:
            return RecallEligibilityResult(
                eligibility=RecallEligibility.SKIP,
                reason_code="EXISTING_FUTURE_APPOINTMENT",
                last_cleaning_date=last_date.isoformat(),
                months_since_last_cleaning=months_ago,
            )

        return RecallEligibilityResult(
            eligibility=RecallEligibility.ELIGIBLE,
            reason_code="ELIGIBLE_FOR_RECALL",
            recommended_service_item_id=self.RECALL_SERVICE_ITEM_ID,
            recommended_service_item_name=self.RECALL_SERVICE_ITEM_NAME,
            last_cleaning_date=last_date.isoformat(),
            months_since_last_cleaning=months_ago,
            next_best_action=self.RECALL_NEXT_BEST_ACTION,
        )

    @staticmethod
    def _months_between(later: date, earlier: date) -> int:
        months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
        if later.day < earlier.day:
            months -= 1
        return months
