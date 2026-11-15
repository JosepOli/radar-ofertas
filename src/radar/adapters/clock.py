from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


class SystemClock:
    def __init__(self, tz: str = "Europe/Madrid") -> None:
        self._tz = ZoneInfo(tz)

    def today(self) -> date:
        return datetime.now(self._tz).date()

    def now(self) -> datetime:
        return datetime.now(self._tz)


class FixedClock:
    def __init__(self, day: date, at: datetime | None = None) -> None:
        self._day = day
        self._at = at or datetime.combine(day, time(12), tzinfo=timezone.utc)

    def today(self) -> date:
        return self._day

    def now(self) -> datetime:
        return self._at
