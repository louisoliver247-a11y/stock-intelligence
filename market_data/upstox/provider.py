import gzip
import json
from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

import httpx

from market_data.calendar import IST, SessionCalendar
from market_data.providers.capabilities import ProviderCapabilities
from market_data.providers.models import Candle, Instrument, Quote, Tick, Timeframe
from market_data.upstox.http import ProviderError, UpstoxHTTP
from market_data.upstox.normalize import normalize_candle, normalize_instrument


class UpstoxProvider:
    code = "upstox"
    subscription_limit = 1500
    capabilities = ProviderCapabilities(
        instrument_master=True, historical_candles=True, intraday_candles=True,
        quotes=True, ltp=True, websocket_quotes=True, websocket_ticks=True,
        market_depth=True, open_interest=True,
    )
    def __init__(self, http: UpstoxHTTP, calendar: SessionCalendar, feed=None):
        self.http, self.calendar, self.feed = http, calendar, feed

    async def get_instruments(self) -> list[Instrument]:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        try:
            response = await self.http.client.get(url)
            response.raise_for_status()
            body = response.content
            records = json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)
            # V1 universe: cash equities and indices. Derivative master needs expiry identity handling.
            instruments = [
                normalize_instrument(r) for r in records if r.get("segment") in {"NSE_EQ", "NSE_INDEX"}
            ]
            if not instruments or len({i.instrument_id for i in instruments}) != len(instruments):
                raise ValueError()
            return instruments
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
            raise ProviderError("INVALID_INSTRUMENT_MASTER") from None

    async def get_historical_candles(
        self, instrument: Instrument, timeframe: Timeframe, start: date, end: date, as_of: datetime
    ) -> list[Candle]:
        if timeframe not in {Timeframe.M1, Timeframe.D1}:
            raise ValueError("ingest canonical 1m or 1d, derive other intervals")
        if start > end:
            raise ValueError("invalid date range")
        unit = "minutes" if timeframe == Timeframe.M1 else "days"
        key = quote(instrument.provider_key, safe="")
        today = as_of.astimezone(IST).date()
        historical_end = min(end, today - timedelta(days=1)) if timeframe == Timeframe.M1 else end
        rows = []
        if start <= historical_end:
            data = await self.http.get(f"/v3/historical-candle/{key}/{unit}/1/{historical_end}/{start}")
            rows = self._candles(data, instrument, timeframe, as_of)
        if timeframe == Timeframe.M1 and start <= today <= end:
            rows.extend(await self.get_intraday_candles(instrument, as_of))
        return rows

    async def get_intraday_candles(self, instrument: Instrument, as_of: datetime) -> list[Candle]:
        key = quote(instrument.provider_key, safe="")
        data = await self.http.get(f"/v3/historical-candle/intraday/{key}/minutes/1")
        return self._candles(data, instrument, Timeframe.M1, as_of)

    def _candles(
        self, data: dict, instrument: Instrument, timeframe: Timeframe, as_of: datetime
    ) -> list[Candle]:
        try:
            return sorted(
                [
                    normalize_candle(row, instrument, timeframe, self.calendar, as_of)
                    for row in data["candles"]
                ],
                key=lambda c: c.timestamp,
            )
        except (ValueError, KeyError, IndexError, TypeError):
            # Reject the entire response atomically; ingestion records a durable failure.
            raise ProviderError("INVALID_CANDLE_RESPONSE") from None

    async def get_quote(self, instrument: Instrument) -> Quote:
        data = await self.http.get("/v2/market-quote/quotes", {"instrument_key": instrument.provider_key})
        try:
            record = next(v for v in data.values() if v.get("instrument_token") == instrument.provider_key)
            ts = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            return Quote(
                source="upstox", provider="upstox",
                instrument_id=instrument.instrument_id,
                price=record["last_price"],
                timestamp=ts,
                previous_close=record.get("ohlc", {}).get("close"),
                cumulative_volume=record.get("volume"),
            )
        except (StopIteration, ValueError, KeyError, TypeError):
            raise ProviderError("INVALID_QUOTE_RESPONSE") from None

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        return (await self.get_quote(instrument)).price

    def subscribe_quotes(self, instruments: Sequence[Instrument]) -> AsyncIterator[Quote]:
        return self._stream(instruments, "ltpc")

    def subscribe_ticks(self, instruments: Sequence[Instrument]) -> AsyncIterator[Tick]:
        return self._stream(instruments, "full")

    def subscribe_market_depth(self, instruments: Sequence[Instrument]) -> AsyncIterator[Quote]:
        return self._stream(instruments, "full")

    def _stream(self, instruments, mode):
        if self.feed is None:
            raise RuntimeError("feed transport was not configured")
        return self.feed.stream(instruments, mode)

    async def unsubscribe(self, instrument_ids: Sequence[str]) -> None:
        if self.feed:
            await self.feed.unsubscribe(instrument_ids)
