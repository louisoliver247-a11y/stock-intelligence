from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market_data.providers.models import ExchangeSession, Timeframe

IST = ZoneInfo("Asia/Kolkata")
SECONDS = {
    Timeframe.S1: 1,
    Timeframe.S5: 5,
    Timeframe.S15: 15,
    Timeframe.S30: 30,
    Timeframe.M1: 60,
    Timeframe.M3: 180,
    Timeframe.M5: 300,
    Timeframe.M10: 600,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
}


class SessionCalendar:
    def __init__(self, sessions: list[ExchangeSession]):
        self.sessions = {(s.exchange, s.session_date): s for s in sessions}

    def session(self, exchange: str, day: date) -> ExchangeSession:
        try:
            return self.sessions[exchange, day]
        except KeyError as exc:
            raise ValueError("UNKNOWN_SESSION") from exc

    def bounds(self, exchange: str, ts: datetime, timeframe: Timeframe) -> tuple[datetime, datetime]:
        if ts.tzinfo is None:
            raise ValueError("timezone required")
        local = ts.astimezone(IST)
        session = self.session(exchange, local.date())
        if session.opens_at is None:
            raise ValueError("NON_TRADING_DAY")
        if timeframe == Timeframe.D1:
            return local.replace(hour=0, minute=0, second=0, microsecond=0), session.closes_at
        if timeframe not in SECONDS:
            raise ValueError("calendar-period aggregation requires daily candles")
        if not session.opens_at <= ts < session.closes_at:
            raise ValueError("OUTSIDE_SESSION")
        step = SECONDS[timeframe]
        start = session.opens_at + timedelta(
            seconds=int((ts - session.opens_at).total_seconds()) // step * step
        )
        return start, min(start + timedelta(seconds=step), session.closes_at)

    def expected_minutes(self, exchange: str, start: date, end: date) -> list[datetime]:
        result = []
        day = start
        while day <= end:
            session = self.session(exchange, day)
            cursor = session.opens_at
            while cursor is not None and cursor < session.closes_at:
                result.append(cursor)
                cursor += timedelta(minutes=1)
            day += timedelta(days=1)
        return result
