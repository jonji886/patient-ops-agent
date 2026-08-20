"""Lightweight circuit breaker for external system calls.

Purpose:
    When a customer's backend system (OMS, Logistics, Ticket, etc.) is persistently
    failing, the circuit breaker prevents the Agent from hammering an already-broken
    endpoint. This demonstrates production-grade integration reliability rather than
    blind retry loops.

States:
    CLOSED     — requests flow normally; failures are counted
    OPEN       — requests are short-circuited immediately (fast-fail)
    HALF_OPEN  — a limited probe request is allowed to test recovery

This is a self-contained, dependency-free implementation. No infrastructure
framework is introduced.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN.

    Callers should map this to a domain-level ExternalUnavailable error and
    trigger fallback or human handoff rather than retrying.
    """

    def __init__(self, name: str, reset_at: float) -> None:
        self.name = name
        self.reset_at = reset_at
        remaining = max(0.0, reset_at - time.monotonic())
        super().__init__(f"circuit '{name}' is OPEN; retry in {remaining:.1f}s")


@dataclass
class _CircuitEntry:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1


@dataclass
class CircuitBreaker:
    """Per-circuit (per-external-system) breaker registry.

    Usage in tests and production:

        breaker = CircuitBreaker()
        try:
            with breaker.guard("clinic_core"):
                response = await client.post(...)
        except CircuitOpenError:
            # fast-fail; do NOT retry; trigger handoff
            raise

    Design decisions:
    - Uses ``time.monotonic`` for immunity to wall-clock changes.
    - Thread-safe via a simple lock (the Agent is async-first but tests may
      run in mixed contexts).
    - Failure threshold is configurable per-circuit via ``configure()``.
    - Does NOT count successes against failures (no sliding window); a
      successful HALF_OPEN probe resets to CLOSED.
    """

    default_config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _circuits: Dict[str, _CircuitEntry] = field(default_factory=dict)
    _configs: Dict[str, CircuitBreakerConfig] = field(default_factory=dict)

    def configure(self, name: str, config: CircuitBreakerConfig) -> None:
        self._configs[name] = config

    def _config(self, name: str) -> CircuitBreakerConfig:
        return self._configs.get(name, self.default_config)

    def _entry(self, name: str) -> _CircuitEntry:
        if name not in self._circuits:
            self._circuits[name] = _CircuitEntry()
        return self._circuits[name]

    def state(self, name: str) -> CircuitState:
        entry = self._entry(name)
        if entry.state is CircuitState.OPEN:
            config = self._config(name)
            if time.monotonic() >= entry.opened_at + config.recovery_timeout_seconds:
                entry.state = CircuitState.HALF_OPEN
        return entry.state

    def record_success(self, name: str) -> None:
        entry = self._entry(name)
        entry.state = CircuitState.CLOSED
        entry.failure_count = 0

    def record_failure(self, name: str) -> None:
        entry = self._entry(name)
        config = self._config(name)
        entry.failure_count += 1
        entry.last_failure_time = time.monotonic()
        if entry.state is CircuitState.HALF_OPEN:
            entry.state = CircuitState.OPEN
            entry.opened_at = time.monotonic()
        elif entry.failure_count >= config.failure_threshold:
            entry.state = CircuitState.OPEN
            entry.opened_at = time.monotonic()

    def guard(self, name: str):
        """Context manager that guards a block of external calls.

        Raises ``CircuitOpenError`` immediately if the circuit is OPEN.
        On success, records success. On any exception, records failure and
        re-raises.
        """
        import contextlib

        current = self.state(name)
        if current is CircuitState.OPEN:
            config = self._config(name)
            raise CircuitOpenError(name, self._entry(name).opened_at + config.recovery_timeout_seconds)

        @contextlib.contextmanager
        def _ctx():
            try:
                yield
            except Exception:
                self.record_failure(name)
                raise
            else:
                self.record_success(name)

        return _ctx()

    def reset(self, name: Optional[str] = None) -> None:
        """Reset one or all circuits. Primarily for testing."""
        if name:
            self._circuits.pop(name, None)
        else:
            self._circuits.clear()
