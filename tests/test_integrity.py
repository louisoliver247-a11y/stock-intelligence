from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from market_data.aggregation import aggregate_minutes
from market_data.calendar import IST
from market_data.historical.ingestion import validate_batch
from market_data.providers.models import Candle, Tick, Timeframe
from market_data.upstox.normalize import normalize_candle
from market_data.websocket.aggregation import TickAggregator


def test_reject_invalid_price_range_and_timezone(candle):
    for change in [
        {"open": 0},
        {"high": 98},
        {"low": 104},
        {"volume": -1},
        {"close": "NaN"},
        {"timestamp": datetime(2025, 1, 2)},
        {"quality_flags": ["BAD"], "is_complete": True},
    ]:
        with pytest.raises(ValidationError):
            Candle.model_validate({**candle.model_dump(), **change})


def test_partial_candle_not_known_before_close(instrument, calendar, session):
    raw = [session.opens_at.isoformat(), 100, 103, 99, 102, 10, 0]
    early = normalize_candle(
        raw, instrument, Timeframe.M1, calendar, session.opens_at + timedelta(seconds=59)
    )
    later = normalize_candle(raw, instrument, Timeframe.M1, calendar, session.opens_at + timedelta(minutes=1))
    assert not early.is_complete
    assert later.is_complete
    with pytest.raises(ValueError, match="FUTURE_CANDLE"):
        normalize_candle(raw, instrument, Timeframe.M1, calendar, session.opens_at - timedelta(seconds=1))


def test_unknown_holiday_and_misaligned_sessions(instrument, calendar, session):
    for timestamp, flag in [
        ("2025-01-03T09:15:00+05:30", "NON_TRADING_DAY"),
        ("2025-01-04T09:15:00+05:30", "UNKNOWN_SESSION"),
        ("2025-01-02T09:15:05+05:30", "MISALIGNED_CANDLE"),
        ("2025-01-02T16:00:00+05:30", "OUTSIDE_SESSION"),
    ]:
        c = normalize_candle(
            [timestamp, 1, 1, 1, 1, 0], instrument, Timeframe.M1, calendar, datetime(2025, 1, 5, tzinfo=IST)
        )
        assert flag in c.quality_flags and not c.is_complete


def test_daily_complete_only_after_session_close(instrument, calendar, session):
    raw = ["2025-01-02T00:00:00+05:30", 100, 103, 99, 102, 10]
    assert not normalize_candle(raw, instrument, Timeframe.D1, calendar, session.opens_at).is_complete
    assert normalize_candle(raw, instrument, Timeframe.D1, calendar, session.closes_at).is_complete


@pytest.mark.parametrize(
    "timeframe,minutes",
    [
        (Timeframe.M3, 3),
        (Timeframe.M5, 5),
        (Timeframe.M10, 10),
        (Timeframe.M15, 15),
        (Timeframe.M30, 30),
        (Timeframe.H1, 60),
        (Timeframe.H4, 240),
    ],
)
def test_session_anchored_aggregation(candle, calendar, timeframe, minutes):
    rows = [
        candle.model_copy(
            update={"timestamp": candle.timestamp + timedelta(minutes=i), "close": Decimal(101 + i % 2)}
        )
        for i in range(minutes)
    ]
    result = aggregate_minutes(rows, timeframe, calendar, candle.timestamp + timedelta(minutes=minutes))[0]
    assert result.timestamp == candle.timestamp
    assert result.volume == 10 * minutes
    assert result.open == 100 and result.close == rows[-1].close and result.high == 103 and result.low == 99
    assert result.is_complete


def test_aggregation_no_lookahead_or_gap_filling(candle, calendar):
    rows = [
        candle.model_copy(update={"timestamp": candle.timestamp + timedelta(minutes=i)}) for i in range(5)
    ]
    before_close = aggregate_minutes(rows, Timeframe.M5, calendar, candle.timestamp + timedelta(minutes=4))[0]
    assert not before_close.is_complete and before_close.volume == 40
    missing = aggregate_minutes(
        rows[:2] + rows[3:], Timeframe.M5, calendar, candle.timestamp + timedelta(minutes=5)
    )[0]
    assert not missing.is_complete and "MISSING_INPUTS" in missing.quality_flags
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_minutes(rows + rows[:1], Timeframe.M5, calendar, candle.timestamp + timedelta(minutes=5))


def test_final_short_hour_is_clipped_to_session(candle, calendar, session):
    start = session.opens_at + timedelta(hours=6)
    rows = [candle.model_copy(update={"timestamp": start + timedelta(minutes=i)}) for i in range(15)]
    result = aggregate_minutes(rows, Timeframe.H1, calendar, session.closes_at)[0]
    assert result.is_complete and result.volume == 150


def test_conflicting_duplicates_are_quarantined(candle, instrument, calendar, session):
    conflict = candle.model_copy(update={"close": Decimal(101)})
    rows, issues = validate_batch(
        [candle, conflict],
        instrument,
        Timeframe.M1,
        calendar,
        session.session_date,
        session.session_date,
        session.closes_at,
    )
    assert rows == []
    assert {i.code for i in issues} == {"CONFLICTING_DUPLICATE", "MISSING_CANDLES"}
    assert len(next(i for i in issues if i.code == "MISSING_CANDLES").details["timestamps"]) == 375


def test_exact_duplicate_is_idempotent(candle, instrument, calendar, session):
    rows, issues = validate_batch(
        [candle, candle],
        instrument,
        Timeframe.M1,
        calendar,
        session.session_date,
        session.session_date,
        session.opens_at + timedelta(minutes=1),
    )
    assert len(rows) == 1 and [i.code for i in issues] == ["DUPLICATE_CANDLE"]


def test_tick_order_volume_baseline_and_reconnect(instrument, calendar, session):
    engine = TickAggregator(calendar)
    first = Tick(
        instrument_id=instrument.instrument_id,
        timestamp=session.opens_at,
        price=100,
        cumulative_volume=10000,
        is_snapshot=True,
    )
    c, issue = engine.update(first, instrument, session.closes_at)
    assert issue is None and c.volume == 0 and not c.is_complete
    next_tick = first.model_copy(
        update={
            "timestamp": first.timestamp + timedelta(seconds=1),
            "price": Decimal(102),
            "cumulative_volume": 10010,
            "is_snapshot": False,
        }
    )
    c, _ = engine.update(next_tick, instrument, session.closes_at)
    assert c.volume == 10 and c.close == 102 and c.open == 100
    assert engine.update(first, instrument, session.closes_at)[1] == "OUT_OF_ORDER_TICK"
    assert engine.update(next_tick, instrument, session.closes_at)[1] == "DUPLICATE_TICK"
    engine.reset()
    c, _ = engine.update(next_tick, instrument, session.closes_at)
    assert c.volume == 0 and "VOLUME_BASELINE_UNKNOWN" in c.quality_flags


@pytest.mark.parametrize("tf", [Timeframe.S1, Timeframe.S5, Timeframe.S15, Timeframe.S30])
def test_second_buckets_provisional(instrument, calendar, session, tf):
    engine = TickAggregator(calendar, tf)
    tick = Tick(
        instrument_id=instrument.instrument_id, timestamp=session.opens_at + timedelta(seconds=16), price=100
    )
    c, _ = engine.update(tick, instrument, session.closes_at)
    assert not c.is_complete and c.timeframe == tf and c.timestamp <= tick.timestamp


def test_abnormal_volume_uses_only_prior_data(candle, instrument, calendar, session):
    rows = [
        candle.model_copy(
            update={"timestamp": candle.timestamp + timedelta(minutes=i), "volume": 10000 if i == 20 else 10}
        )
        for i in range(22)
    ]
    prefix, _ = validate_batch(
        rows[:21],
        instrument,
        Timeframe.M1,
        calendar,
        session.session_date,
        session.session_date,
        session.opens_at + timedelta(minutes=21),
    )
    full, issues = validate_batch(
        rows,
        instrument,
        Timeframe.M1,
        calendar,
        session.session_date,
        session.session_date,
        session.opens_at + timedelta(minutes=22),
    )
    assert prefix == full[:21]
    assert not full[20].is_complete and full[21].is_complete
    assert any(i.code == "ABNORMAL_VOLUME" for i in issues)


def test_misaligned_minute_cannot_complete_aggregate(candle, calendar):
    bad = candle.model_copy(update={"timestamp": candle.timestamp + timedelta(seconds=5)})
    with pytest.raises(ValueError, match="misaligned"):
        aggregate_minutes([bad], Timeframe.M1, calendar, candle.timestamp + timedelta(minutes=2))
