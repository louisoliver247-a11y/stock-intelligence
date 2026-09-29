from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from market_data.calendar import SessionCalendar
from market_data.providers.models import Candle, DepthLevel, Instrument, Tick, Timeframe


def normalize_instrument(raw: dict) -> Instrument:
    # Stable identity is separated from broker routing keys. NSE equity identity uses ISIN.
    segment = raw["segment"]
    exchange = raw["exchange"]
    identity = f"{segment}:{raw.get('isin') or raw['instrument_key']}"
    return Instrument(
        instrument_id=str(uuid5(NAMESPACE_URL, identity)),
        symbol=raw["trading_symbol"],
        exchange=exchange,
        segment=segment,
        name=raw.get("name", ""),
        isin=raw.get("isin"),
        instrument_type=raw["instrument_type"],
        provider_key=raw["instrument_key"], provider="upstox",
        trading_symbol=raw["trading_symbol"],
    )


def normalize_candle(
    raw: list, instrument: Instrument, timeframe: Timeframe, calendar: SessionCalendar, as_of: datetime
) -> Candle:
    if as_of.tzinfo is None:
        raise ValueError("timezone required")
    ts = datetime.fromisoformat(raw[0])
    if ts.tzinfo is None:
        raise ValueError("NAIVE_PROVIDER_TIMESTAMP")
    flags = []
    try:
        start, end = calendar.bounds(instrument.exchange, ts, timeframe)
        if start != ts:
            flags.append("MISALIGNED_CANDLE")
        complete = end <= as_of and not flags
    except ValueError as exc:
        flags.append(str(exc))
        complete = False
    if ts > as_of:
        raise ValueError("FUTURE_CANDLE")
    return Candle(
        instrument_id=instrument.instrument_id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        timeframe=timeframe,
        timestamp=ts.astimezone(UTC),
        open=raw[1],
        high=raw[2],
        low=raw[3],
        close=raw[4],
        volume=raw[5],
        open_interest=raw[6] if len(raw) > 6 else None,
        is_complete=complete,
        source="upstox_history", provider="upstox",
        provider_instrument_id=instrument.provider_key,
        quality_flags=tuple(flags),
    )


def normalize_feed(payload: dict, instruments: dict[str, Instrument]) -> list[Tick]:
    updates = []
    for key, feed in payload.get("feeds", {}).items():
        if key not in instruments:
            continue
        full = feed.get("fullFeed", {})
        data = full.get("marketFF") or full.get("indexFF") or feed.get("firstLevelWithGreeks") or feed
        ltpc = data.get("ltpc", {})
        if not ltpc.get("ltt") or not ltpc.get("ltp"):
            continue
        depth = tuple(
            DepthLevel(
                bid_price=d.get("bidP", 0),
                bid_quantity=d.get("bidQ", 0),
                ask_price=d.get("askP", 0),
                ask_quantity=d.get("askQ", 0),
            )
            for d in data.get("marketLevel", {}).get("bidAskQuote", [])
        )
        updates.append(
            Tick(
                provider="upstox", source="upstox_feed",
                instrument_id=instruments[key].instrument_id,
                price=ltpc["ltp"],
                timestamp=datetime.fromtimestamp(int(ltpc["ltt"]) / 1000, UTC),
                previous_close=ltpc.get("cp"),
                cumulative_volume=data.get("vtt"),
                depth=depth,
                is_snapshot=payload.get("type", "initial_feed") == "initial_feed",
            )
        )
    return updates
