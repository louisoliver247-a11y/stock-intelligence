from collections import defaultdict
from datetime import datetime, timedelta

from market_data.calendar import SECONDS, SessionCalendar
from market_data.providers.models import Candle, Timeframe


def aggregate_minutes(
    candles: list[Candle], timeframe: Timeframe, calendar: SessionCalendar, as_of: datetime
) -> list[Candle]:
    """Session-anchored resampling. Missing/partial inputs never become complete output."""
    if timeframe not in SECONDS or SECONDS[timeframe] < 60:
        raise ValueError("minute aggregation supports intraday minute/hour timeframes")
    if as_of.tzinfo is None:
        raise ValueError("timezone required")
    groups = defaultdict(list)
    seen = set()
    for c in sorted(candles, key=lambda item: item.timestamp):
        if c.timeframe != Timeframe.M1:
            raise ValueError("only canonical minute candles may be aggregated")
        key = (c.instrument_id, c.timestamp)
        if key in seen:
            raise ValueError("duplicate input candle")
        seen.add(key)
        if c.timestamp + timedelta(minutes=1) > as_of:
            continue
        minute_start, _ = calendar.bounds(c.exchange, c.timestamp, Timeframe.M1)
        if minute_start != c.timestamp:
            raise ValueError("misaligned minute input")
        start, end = calendar.bounds(c.exchange, c.timestamp, timeframe)
        groups[c.instrument_id, start, end].append(c)
    results = []
    for (_, start, end), group in groups.items():
        expected = int((end - start).total_seconds() / 60)
        flags = set(flag for c in group for flag in c.quality_flags)
        if len(group) != expected or group[0].timestamp != start:
            flags.add("MISSING_INPUTS")
        if any(not c.is_complete for c in group):
            flags.add("PARTIAL_INPUT")
        if end > as_of:
            flags.add("OPEN_INTERVAL")
        results.append(
            Candle(
                instrument_id=group[0].instrument_id,
                symbol=group[0].symbol,
                exchange=group[0].exchange,
                timeframe=timeframe,
                timestamp=start,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
                open_interest=group[-1].open_interest,
                is_complete=not flags,
                source="derived_1m",
                provider=group[0].provider if len({c.provider for c in group}) == 1 else "mixed",
                reconciled=all(c.reconciled for c in group),
                adjustment=group[0].adjustment if len({c.adjustment for c in group}) == 1 else "mixed",
                quality_flags=tuple(sorted(flags)),
            )
        )
    return sorted(results, key=lambda c: (c.instrument_id, c.timestamp))
