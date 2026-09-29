import gzip
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from market_data.historical.ingestion import HistoricalIngestion
from market_data.providers.models import Timeframe
from market_data.upstox.http import ProviderError, UpstoxHTTP
from market_data.upstox.normalize import normalize_feed
from market_data.upstox.provider import UpstoxProvider
from market_data.websocket.feed import UpstoxFeed, decode_message


async def test_history_url_normalization_and_auth(instrument, calendar, session):
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-token"
        assert "intraday/NSE_EQ%7CTESTISIN/minutes/1" in str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"candles": [[session.opens_at.isoformat(), 100, 103, 99, 102, 10, 0]]},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = UpstoxProvider(UpstoxHTTP(client, "test-token"), calendar)
        rows = await provider.get_historical_candles(
            instrument, Timeframe.M1, session.session_date, session.session_date, session.closes_at
        )
    assert rows[0].is_complete and rows[0].instrument_id == instrument.instrument_id


async def test_instrument_gzip_master(calendar):
    raw = [
        {
            "segment": "NSE_EQ",
            "exchange": "NSE",
            "isin": "TEST",
            "instrument_key": "NSE_EQ|TEST",
            "trading_symbol": "TEST",
            "instrument_type": "EQ",
            "name": "Test",
        }
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=gzip.compress(json.dumps(raw).encode()))
        )
    ) as client:
        rows = await UpstoxProvider(UpstoxHTTP(client, ""), calendar).get_instruments()
    assert rows[0].symbol == "TEST" and rows[0].instrument_id != rows[0].provider_key


async def test_retry_429_but_not_auth_error():
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "0"})
            if len(calls) == 1
            else httpx.Response(200, json={"status": "success", "data": {"ok": True}})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await UpstoxHTTP(client, "test").get("/v3/test") == {"ok": True}
    assert len(calls) == 2
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401))) as client:
        with pytest.raises(ProviderError) as exc:
            await UpstoxHTTP(client, "secret-token").get("/v3/test")
        assert exc.value.status == 401 and "secret-token" not in str(exc.value)


def test_official_protobuf_binary_round_trip(instrument, session):
    from market_data.upstox.MarketDataFeed_pb2 import FeedResponse

    message = FeedResponse()
    message.type = 1
    market = message.feeds[instrument.provider_key].fullFeed.marketFF
    market.ltpc.ltp = 101
    market.ltpc.ltt = int(session.opens_at.timestamp() * 1000)
    market.vtt = 500
    level = market.marketLevel.bidAskQuote.add()
    level.bidP, level.askP, level.bidQ, level.askQ = 100, 102, 20, 30
    ticks = normalize_feed(decode_message(message.SerializeToString()), {instrument.provider_key: instrument})
    assert ticks[0].price == 101 and ticks[0].cumulative_volume == 500
    assert ticks[0].depth[0].ask_quantity == 30 and not ticks[0].is_snapshot


async def test_feed_reauthorizes_and_resubscribes(instrument, session):
    from market_data.upstox.MarketDataFeed_pb2 import FeedResponse

    message = FeedResponse()
    message.type = 1
    message.feeds[instrument.provider_key].ltpc.ltp = 100
    message.feeds[instrument.provider_key].ltpc.ltt = int(session.opens_at.timestamp() * 1000)
    sent = []

    class Socket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, raw):
            sent.append(raw)

        def __aiter__(self):
            return self.messages()

        async def messages(self):
            yield message.SerializeToString()

    http = AsyncMock()
    http.get.return_value = {"authorized_redirect_uri": "wss://example.test/feed"}
    connected, disconnected = AsyncMock(), AsyncMock()
    feed = UpstoxFeed(http, connected, disconnected, connector=lambda *a, **kw: Socket(), sleep=AsyncMock())
    stream = feed.stream([instrument])
    assert (await anext(stream)).price == 100
    assert (await anext(stream)).price == 100
    assert http.get.await_count == 2 and connected.await_count == 2 and disconnected.await_count == 1
    assert all(isinstance(s, bytes) and json.loads(s)["method"] == "sub" for s in sent)
    await feed.unsubscribe([instrument.instrument_id])
    assert json.loads(sent[-1])["method"] == "unsub"
    await stream.aclose()


async def test_history_chunking(instrument, calendar, session):
    provider, repo = AsyncMock(), AsyncMock()
    provider.get_historical_candles.return_value = []
    repo.persist.return_value = {"inserted": 0, "corrected": 0, "unchanged": 0, "issues": 0}
    await HistoricalIngestion(provider, repo, calendar, 2).ingest(
        instrument,
        Timeframe.D1,
        session.session_date,
        session.session_date + timedelta(days=4),
        session.closes_at + timedelta(days=5),
    )
    assert provider.get_historical_candles.await_count == 3
    ranges = [(call.args[2], call.args[3]) for call in provider.get_historical_candles.call_args_list]
    assert ranges[0][1] + timedelta(days=1) == ranges[1][0]


async def test_invalid_provider_candle_rejects_batch(instrument, calendar, session):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"candles": [[session.opens_at.isoformat(), 0, 1, 1, 1, 10]]},
                },
            )
        )
    ) as client:
        with pytest.raises(ProviderError, match="INVALID_CANDLE_RESPONSE"):
            await UpstoxProvider(UpstoxHTTP(client, "test"), calendar).get_historical_candles(
                instrument, Timeframe.M1, session.session_date, session.session_date, session.closes_at
            )
