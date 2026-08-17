"""Synthetic demo authentication and signed actor tokens for the channel simulator."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict

from patient_ops_agent.mocks.fixtures import load_fixtures


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    patient_id: Optional[str] = None
    verification_level: Literal["CHANNEL_AUTHENTICATED"]
    verified_at: datetime
    role: Literal["PATIENT", "OPERATOR", "ADMIN"] = "PATIENT"
    display_name: Optional[str] = None


class DemoAuthenticator:
    """Authenticates fixture-only accounts without handling real patient identity data."""

    def __init__(self, accounts: Optional[Dict[str, Dict[str, str]]] = None):
        if accounts is None:
            fixtures = load_fixtures()
            accounts = {account["username"]: account for account in fixtures.get("demo_accounts", [])}
        self._accounts = accounts

    def authenticate(self, username: str, password: str, verified_at: datetime) -> Optional[ActorContext]:
        account = self._accounts.get(username)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if not account or not hmac.compare_digest(account["password_sha256"], password_hash):
            return None
        return ActorContext(
            actor_id=account["actor_id"],
            verification_level="CHANNEL_AUTHENTICATED",
            verified_at=verified_at,
            patient_id=account.get("patient_id"),
            role=account.get("role", "PATIENT"),
            display_name=account.get("display_name"),
        )

    def list_demo_accounts(self) -> list[Dict[str, str]]:
        """Return public fixture metadata only; credentials remain server-side."""

        return [
            {
                "username": account["username"],
                "display_name": account.get("display_name", account["username"]),
                "actor_role": account.get("role", "PATIENT"),
            }
            for account in self._accounts.values()
        ]


def issue_actor_token(context: ActorContext, secret: str) -> str:
    payload = context.model_dump_json().encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_actor_token(token: str, secret: str, now: datetime, max_age_seconds: int = 86400) -> ActorContext:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        padding = "=" * (-len(encoded) % 4)
        context = ActorContext.model_validate(json.loads(base64.urlsafe_b64decode(encoded + padding)))
    except Exception as exc:
        raise ValueError("invalid actor token") from exc
    age = (now - context.verified_at).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("expired actor token")
    return context
