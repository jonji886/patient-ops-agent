from datetime import timedelta

import pytest

from patient_ops_agent.domain.models import AgentRun, ConfirmationRecord, ConfirmationStatus
from patient_ops_agent.models import ExecutionOwner
from patient_ops_agent.policy import PolicyEngine


def records(sut):
    now = sut.clock.now()
    run = AgentRun(
        id="RUN-1", conversation_id="CONV-1", patient_id="P1001", actor_id="ACTOR-P1001",
        verification_level="CHANNEL_AUTHENTICATED", verified_at=now, started_at=now,
    )
    confirmation = ConfirmationRecord(
        id="CONF-1", run_id=run.id, patient_id="P1001", action_type="CREATE_APPOINTMENT",
        target_id="S1001", parameters={"slot_id": "S1001"}, parameter_hash="hash",
        resource_version=1, status=ConfirmationStatus.CONFIRMED, confirmed_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    return run, confirmation


def test_policy_allows_complete_high_risk_context(sut):
    run, confirmation = records(sut)
    decision = PolicyEngine().authorize_high_risk(run, confirmation, "P1001", "hash", "P1001", sut.clock.now())
    assert decision.allowed
    assert decision.code == "ALLOWED"


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("operator_owner", "EXECUTION_OWNER_NOT_AGENT"),
        ("wrong_actor", "FORBIDDEN"),
        ("wrong_resource_owner", "FORBIDDEN"),
        ("unverified", "UNAUTHENTICATED"),
        ("wrong_confirmation_patient", "FORBIDDEN"),
        ("wrong_run", "FORBIDDEN"),
        ("pending", "CONFIRMATION_NOT_CONFIRMED"),
        ("invalidated", "CONFIRMATION_NOT_CONFIRMED"),
        ("consumed", "CONFIRMATION_NOT_CONFIRMED"),
        ("expired", "CONFIRMATION_EXPIRED"),
        ("hash_mismatch", "CONFIRMATION_PARAMETER_MISMATCH"),
    ],
)
def test_policy_denial_matrix(sut, mutation, expected):
    run, confirmation = records(sut)
    actor = owner = "P1001"
    digest = "hash"
    if mutation == "operator_owner": run.execution_owner = ExecutionOwner.OPERATOR
    elif mutation == "wrong_actor": actor = "P1002"
    elif mutation == "wrong_resource_owner": owner = "P1002"
    elif mutation == "unverified": run.verification_level = "UNVERIFIED"
    elif mutation == "wrong_confirmation_patient": confirmation.patient_id = "P1002"
    elif mutation == "wrong_run": confirmation.run_id = "RUN-2"
    elif mutation == "pending": confirmation.status = ConfirmationStatus.PENDING
    elif mutation == "invalidated": confirmation.status = ConfirmationStatus.INVALIDATED
    elif mutation == "consumed": confirmation.status = ConfirmationStatus.CONSUMED
    elif mutation == "expired": confirmation.expires_at = sut.clock.now() - timedelta(seconds=1)
    elif mutation == "hash_mismatch": digest = "different"
    decision = PolicyEngine().authorize_high_risk(run, confirmation, actor, digest, owner, sut.clock.now())
    assert not decision.allowed
    assert decision.code == expected
