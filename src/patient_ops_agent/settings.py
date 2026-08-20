"""Application settings with safe handling of local secrets."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    The default provider is ``fake`` so deterministic tests and the local
    domain slice do not require a DeepSeek key. Real LLM mode must explicitly
    set ``LLM_PROVIDER=deepseek`` and ``DEEPSEEK_MODEL``.
    """

    app_env: Literal["development", "test", "demo", "production"] = "development"
    log_level: str = "INFO"

    # SQLite is the default local-development profile. Docker Compose overrides
    # all three URLs with PostgreSQL URLs for deployment-like verification.
    agent_database_url: str = "sqlite:///./var/patient_ops/agent_ops.db"
    patient_ops_database_url: str = "sqlite:///./var/patient_ops/patient_ops.db"
    clinic_core_database_url: str = "sqlite:///./var/patient_ops/clinic_core.db"

    patient_ops_base_url: str = "http://localhost:8001"
    clinic_core_base_url: str = "http://localhost:8002"

    llm_provider: Literal["fake", "deepseek"] = "fake"
    deepseek_api_key: Optional[SecretStr] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: Optional[str] = None
    llm_timeout_seconds: float = 30.0
    llm_max_attempts: int = 1
    demo_business_clock: Optional[datetime] = datetime.fromisoformat("2026-08-14T09:00:00+08:00")

    confirmation_ttl_seconds: int = 300
    max_retry_attempts: int = 3
    outbox_batch_size: int = 20
    outbox_poll_interval_seconds: float = 1.0
    outbox_lease_seconds: int = 60
    actor_token_signing_secret: SecretStr = SecretStr("change-me-in-development-only")

    # Demo controls are opt-in.  Production profiles never expose the
    # scenario controller, even if an environment accidentally enables it.
    enable_demo_scenarios: bool = False

    # --- Integration reliability ---
    # Gateway-level timeout (seconds) for external system HTTP calls.
    gateway_timeout_seconds: float = 10.0
    # Circuit breaker thresholds per external system.
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_seconds: float = 30.0

    # --- Fault injection (deterministic, off by default) ---
    # These allow demonstrating failure scenarios without random CI flakiness.
    # Set MOCK_*_LATENCY_MS > 0 to simulate slow responses.
    # Set MOCK_*_FAILURE_RATE to 1.0 for deterministic failure (use with
    # the explicit fault hooks in ClinicCoreData for precise test control).
    mock_clinic_core_latency_ms: int = 0
    mock_clinic_core_failure_rate: float = 0.0
    mock_patient_ops_latency_ms: int = 0
    mock_patient_ops_failure_rate: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def validate_llm_configuration(self) -> None:
        """Fail only when real DeepSeek mode is explicitly selected."""

        if self.llm_provider == "deepseek":
            if self.deepseek_api_key is None or not self.deepseek_api_key.get_secret_value():
                raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
            if not self.deepseek_model:
                raise ValueError("DEEPSEEK_MODEL is required when LLM_PROVIDER=deepseek")

    @property
    def uses_sqlite(self) -> bool:
        return self.agent_database_url.startswith("sqlite")

    def validate_storage_configuration(self) -> None:
        urls = (self.agent_database_url, self.patient_ops_database_url, self.clinic_core_database_url)
        sqlite_flags = [url.startswith("sqlite") for url in urls]
        if any(sqlite_flags) and not all(sqlite_flags):
            raise ValueError("all database URLs must use the same SQLite or PostgreSQL profile")
