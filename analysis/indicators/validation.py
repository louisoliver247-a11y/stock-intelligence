from datetime import UTC, datetime, timedelta

import numpy as np
from pydantic import ValidationError

from market_data.calendar import IST, SECONDS, SessionCalendar
from market_data.providers.models import Candle, CandleObservation, Timeframe


class IndicatorInputError(ValueError):
    """A deterministic rejection code; callers must resolve the input and replay."""


def candle_end(candle: Candle, calendar: SessionCalendar) -> datetime:
    if candle.timeframe != Timeframe.D1 and (
        candle.timeframe not in SECONDS or SECONDS[candle.timeframe] < 60
    ):
        raise IndicatorInputError("UNSUPPORTED_TIMEFRAME")
    try:
        start, end = calendar.bounds(candle.exchange, candle.timestamp, candle.timeframe)
    except ValueError as exc:
        raise IndicatorInputError(str(exc)) from None
    if candle.timestamp != start:
        raise IndicatorInputError("MISALIGNED_CANDLE")
    return end.astimezone(UTC)


def require_contiguous(previous: Candle, current: Candle, calendar: SessionCalendar) -> None:
    previous_day, current_day = (c.timestamp.astimezone(IST).date() for c in (previous, current))
    prior_end = candle_end(previous, calendar)
    if current_day == previous_day:
        if current.timestamp != prior_end:
            raise IndicatorInputError("MISSING_CANDLES")
        return
    if prior_end != calendar.session(previous.exchange, previous_day).closes_at:
        raise IndicatorInputError("MISSING_SESSION_TAIL")
    day = previous_day + timedelta(days=1)
    while day < current_day:
        try:
            session = calendar.session(current.exchange, day)
        except ValueError as exc:
            raise IndicatorInputError(str(exc)) from None
        if session.opens_at is not None:
            raise IndicatorInputError("MISSING_SESSION")
        day += timedelta(days=1)
    session = calendar.session(current.exchange, current_day)
    expected = session.opens_at
    if current.timeframe == Timeframe.D1:
        expected = datetime.combine(current_day, datetime.min.time(), IST)
    if current.timestamp != expected:
        raise IndicatorInputError("MISSING_SESSION_OPEN")


def validate_observation(observation: CandleObservation, calendar: SessionCalendar,
                         as_of: datetime, previous: CandleObservation | None) -> datetime:
    """All checks precede any mutation of incremental indicator state."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise IndicatorInputError("NAIVE_AS_OF")
    candle = observation.candle
    try:
        Candle.model_validate(candle.model_dump())
    except ValidationError:
        raise IndicatorInputError("INVALID_CANDLE") from None
    if observation.known_at.tzinfo is None or observation.known_at.utcoffset() is None:
        raise IndicatorInputError("NAIVE_KNOWN_AT")
    if not candle.is_complete or candle.quality_flags:
        raise IndicatorInputError("UNVALIDATED_CANDLE")
    if not candle.reconciled:
        raise IndicatorInputError("UNRECONCILED_FEED")
    values = np.asarray([float(v) for v in (candle.open, candle.high, candle.low, candle.close)], dtype=np.float64)
    if not np.isfinite(values).all():
        raise IndicatorInputError("NON_FINITE_INPUT")
    # Bound volume to the durable canonical PostgreSQL bigint domain.
    if candle.volume > np.iinfo(np.int64).max:
        raise IndicatorInputError("VOLUME_OUT_OF_RANGE")
    closed_at = candle_end(candle, calendar)
    if observation.known_at < closed_at:
        raise IndicatorInputError("KNOWN_BEFORE_CLOSE")
    if observation.known_at > as_of:
        raise IndicatorInputError("NOT_YET_KNOWN")
    if previous:
        if (candle.instrument_id, candle.exchange, candle.timeframe) != (
            previous.candle.instrument_id, previous.candle.exchange, previous.candle.timeframe
        ):
            raise IndicatorInputError("MIXED_STREAM")
        if candle.timestamp < previous.candle.timestamp:
            raise IndicatorInputError("OUT_OF_ORDER_CANDLE")
        if candle.timestamp == previous.candle.timestamp:
            if observation != previous:
                raise IndicatorInputError("CORRECTION_REQUIRES_REPLAY")
            return closed_at
        require_contiguous(previous.candle, candle, calendar)
    return closed_at
