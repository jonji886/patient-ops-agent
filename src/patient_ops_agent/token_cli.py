"""Issue a short-lived synthetic patient token for local demos."""

from patient_ops_agent.clock import runtime_clock
from patient_ops_agent.security import ActorContext, issue_actor_token
from patient_ops_agent.settings import Settings


def run() -> None:
    settings = Settings()
    context = ActorContext(actor_id="ACTOR-P1001", patient_id="P1001",
        verification_level="CHANNEL_AUTHENTICATED",
        verified_at=runtime_clock(settings.uses_sqlite, settings.llm_provider, settings.demo_business_clock).now())
    print(issue_actor_token(context, settings.actor_token_signing_secret.get_secret_value()))
