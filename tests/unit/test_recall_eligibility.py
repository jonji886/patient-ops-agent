"""Unit tests for deterministic Recall eligibility rules.

Recall 资格完全由确定性代码判定，LLM 不参与。这些测试验证：
- Case 1: 满足召回条件 → ELIGIBLE
- Case 2: 距上次洗牙不足周期 → NOT_ELIGIBLE
- Case 3: 没有 Patient Facts → NOT_ELIGIBLE（Graceful Degradation）
- Case 4: 已有未来有效预约 → SKIP
- Case 5: 触达许可被拒 → NOT_ELIGIBLE
- Case 6: 无效事实数据 → NOT_ELIGIBLE
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

import pytest

from patient_ops_agent.domain.recall import (
    RecallEligibility,
    RecallEligibilityRule,
)


class FakeStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


@dataclass
class FakeAppointment:
    service_item_id: str
    status: FakeStatus = FakeStatus.CONFIRMED


@pytest.fixture
def rule():
    return RecallEligibilityRule()


@pytest.fixture
def today():
    return date(2026, 8, 14)


def test_eligible_when_last_cleaning_over_threshold(rule, today):
    """Case 1: 距上次洗牙 >= 5 个月 → ELIGIBLE，生成 NBA。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-02-10"}]
    consent = {"allowed": True}
    result = rule.evaluate(facts, consent, [], today)

    assert result.eligibility is RecallEligibility.ELIGIBLE
    assert result.reason_code == "ELIGIBLE_FOR_RECALL"
    assert result.recommended_service_item_id == "SV-CLEANING"
    assert result.recommended_service_item_name == "洗牙"
    assert result.next_best_action == "RECOMMEND_DENTAL_CLEANING_REVIEW"
    assert result.months_since_last_cleaning == 6


def test_not_eligible_when_within_threshold(rule, today):
    """Case 2: 距上次洗牙不足 5 个月 → NOT_ELIGIBLE。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-08-01"}]
    consent = {"allowed": True}
    result = rule.evaluate(facts, consent, [], today)

    assert result.eligibility is RecallEligibility.NOT_ELIGIBLE
    assert result.reason_code == "NOT_YET_DUE"
    assert result.months_since_last_cleaning == 0


def test_not_eligible_when_no_facts(rule, today):
    """Case 3: 没有 Patient Facts → NOT_ELIGIBLE（Graceful Degradation）。"""
    result = rule.evaluate([], {"allowed": True}, [], today)

    assert result.eligibility is RecallEligibility.NOT_ELIGIBLE
    assert result.reason_code == "NO_PATIENT_FACTS"
    assert result.recommended_service_item_id is None


def test_skip_when_existing_future_appointment(rule, today):
    """Case 4: 已有未来有效洗牙预约 → SKIP（防止重复触达）。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-01-10"}]
    consent = {"allowed": True}
    appointments = [FakeAppointment(service_item_id="SV-CLEANING")]
    result = rule.evaluate(facts, consent, appointments, today)

    assert result.eligibility is RecallEligibility.SKIP
    assert result.reason_code == "EXISTING_FUTURE_APPOINTMENT"
    assert result.months_since_last_cleaning == 7


def test_not_eligible_when_consent_denied(rule, today):
    """Case 5: 触达许可被拒 → NOT_ELIGIBLE，不得发送召回。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-01-10"}]
    consent = {"allowed": False}
    result = rule.evaluate(facts, consent, [], today)

    assert result.eligibility is RecallEligibility.NOT_ELIGIBLE
    assert result.reason_code == "CONTACT_CONSENT_DENIED"


def test_not_eligible_when_invalid_fact_value(rule, today):
    """Case 6: 事实数据格式无效 → NOT_ELIGIBLE，不凭 LLM 猜测。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "not-a-date"}]
    consent = {"allowed": True}
    result = rule.evaluate(facts, consent, [], today)

    assert result.eligibility is RecallEligibility.NOT_ELIGIBLE
    assert result.reason_code == "INVALID_PATIENT_FACTS"


def test_skip_does_not_trigger_for_cancelled_appointment(rule, today):
    """已取消的预约不应阻止召回。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-01-10"}]
    consent = {"allowed": True}
    appointments = [FakeAppointment(service_item_id="SV-CLEANING", status=FakeStatus.CANCELLED)]
    result = rule.evaluate(facts, consent, appointments, today)

    assert result.eligibility is RecallEligibility.ELIGIBLE


def test_skip_does_not_trigger_for_different_service(rule, today):
    """不同服务的预约不应阻止洗牙召回。"""
    facts = [{"fact_type": "last_cleaning_date", "value": "2026-01-10"}]
    consent = {"allowed": True}
    appointments = [FakeAppointment(service_item_id="SV-CHECKUP")]
    result = rule.evaluate(facts, consent, appointments, today)

    assert result.eligibility is RecallEligibility.ELIGIBLE
