"""Deterministic authorization for all high-risk writes."""

from dataclasses import dataclass
from datetime import datetime

from patient_ops_agent.domain.models import AgentRun, ConfirmationRecord, ConfirmationStatus
from patient_ops_agent.models import ExecutionOwner


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str


class PolicyEngine:
    def authorize_high_risk(
        self,
        run: AgentRun,
        confirmation: ConfirmationRecord,
        actor_patient_id: str,
        parameter_hash: str,
        resource_owner_patient_id: str,
        now: datetime,
    ) -> PolicyDecision:
        if run.execution_owner is not ExecutionOwner.AGENT:
            return PolicyDecision(False, "EXECUTION_OWNER_NOT_AGENT")
        if run.patient_id != actor_patient_id or resource_owner_patient_id != actor_patient_id:
            return PolicyDecision(False, "FORBIDDEN")
        if run.verification_level != "CHANNEL_AUTHENTICATED":
            return PolicyDecision(False, "UNAUTHENTICATED")
        if confirmation.patient_id != actor_patient_id or confirmation.run_id != run.id:
            return PolicyDecision(False, "FORBIDDEN")
        if confirmation.status is not ConfirmationStatus.CONFIRMED:
            return PolicyDecision(False, "CONFIRMATION_NOT_CONFIRMED")
        if confirmation.expires_at <= now:
            return PolicyDecision(False, "CONFIRMATION_EXPIRED")
        if confirmation.parameter_hash != parameter_hash:
            return PolicyDecision(False, "CONFIRMATION_PARAMETER_MISMATCH")
        return PolicyDecision(True, "ALLOWED")
