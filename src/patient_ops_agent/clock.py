"""Injectable business clock."""

from datetime import datetime
from typing import Optional, Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


DEFAULT_DEMO_BUSINESS_CLOCK = datetime.fromisoformat("2026-08-14T09:00:00+08:00")


def runtime_clock(uses_sqlite: bool, llm_provider: str, demo_business_clock: Optional[datetime]) -> Clock:
    """Use a stable clock only for the local deterministic synthetic demo."""

    if uses_sqlite and llm_provider == "fake":
        return FixedClock(demo_business_clock or DEFAULT_DEMO_BUSINESS_CLOCK)
    return SystemClock()
