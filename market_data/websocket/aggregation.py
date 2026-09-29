from datetime import datetime

from market_data.calendar import SessionCalendar
from market_data.providers.models import Candle, Instrument, Tick, Timeframe


class TickAggregator:
    """Bounded one-candle state per instrument; sampled feed candles are always provisional."""

    def __init__(self, calendar: SessionCalendar, timeframe: Timeframe = Timeframe.M1):
        self.calendar, self.timeframe = calendar, timeframe
        self.active: dict[str, Candle] = {}
        self.last: dict[str, Tick] = {}

    def reset(self):
        self.active.clear()
        self.last.clear()

    def update(
        self, tick: Tick, instrument: Instrument, received_at: datetime
    ) -> tuple[Candle | None, str | None]:
        if tick.timestamp > received_at:
            return None, "FUTURE_TICK"
        previous = self.last.get(tick.instrument_id)
        if previous and tick.timestamp < previous.timestamp:
            return None, "OUT_OF_ORDER_TICK"
        if previous == tick:
            return None, "DUPLICATE_TICK"
        try:
            start, _ = self.calendar.bounds(instrument.exchange, tick.timestamp, self.timeframe)
        except ValueError as exc:
            return None, str(exc)
        old = self.active.get(tick.instrument_id)
        flags = {"SAMPLED_FEED", "UNRECONCILED"}
        volume = 0
        # Only consecutive cumulative-volume differences are usable. Never sum LTQ.
        if previous and previous.cumulative_volume is not None and tick.cumulative_volume is not None:
            delta = tick.cumulative_volume - previous.cumulative_volume
            if delta < 0:
                flags.add("VOLUME_RESET")
            elif old and old.timestamp == start and not tick.is_snapshot:
                volume = delta
            else:
                flags.add("VOLUME_BOUNDARY_UNKNOWN")
        else:
            flags.add("VOLUME_BASELINE_UNKNOWN")
        self.last[tick.instrument_id] = tick
        same = old is not None and old.timestamp == start
        c = Candle(
            instrument_id=instrument.instrument_id,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            timeframe=self.timeframe,
            timestamp=start,
            open=old.open if same else tick.price,
            high=max(old.high, tick.price) if same else tick.price,
            low=min(old.low, tick.price) if same else tick.price,
            close=tick.price,
            volume=(old.volume if same else 0) + volume,
            is_complete=False,
            source="sampled_feed",
            provider=tick.provider, reconciled=False,
            quality_flags=tuple(sorted(flags | (set(old.quality_flags) if same else set()))),
        )
        self.active[tick.instrument_id] = c
        return c, None
