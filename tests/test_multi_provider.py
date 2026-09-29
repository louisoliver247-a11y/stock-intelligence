import base64
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.exceptions import ConnectionError

from analysis.indicators.validation import IndicatorInputError, validate_observation
from config.settings import Settings
from market_data.hdfc_sky.provider import HDFCSkyProvider
from market_data.migration_status import migration_heads
from market_data.providers.capabilities import ProviderCapabilities
from market_data.providers.models import CandleObservation
from market_data.providers.registry import ProviderRegistry
from market_data.providers.status import provider_catalog
from market_data.providers.subscriptions import plan_subscriptions
from market_data.resilience import redis_call
from market_data.sharekhan.auth import exchange_request_token
from market_data.sharekhan.http import SharekhanHTTP
from market_data.sharekhan.normalize import normalize_candle, normalize_instrument
from market_data.sharekhan.provider import SharekhanProvider
from market_data.sharekhan.websocket import SharekhanFeed, decode_message
from market_data.upstox.provider import UpstoxProvider


def test_capability_registry_and_fallback():
    registry = ProviderRegistry()
    registry.register('hdfc_sky', HDFCSkyProvider)
    registry.register('sharekhan', lambda: SharekhanProvider(None, None))
    registry.register('upstox', lambda: UpstoxProvider(None, None))
    assert [p.code for p in registry.candidates(['hdfc_sky', 'sharekhan', 'upstox'], 'historical_candles')] == [
        'sharekhan', 'upstox']
    assert not registry.get('sharekhan').capabilities.orders
    assert not registry.get('hdfc_sky').capabilities.historical_candles
    with pytest.raises(ValueError):
        registry.register('upstox', HDFCSkyProvider)
    with pytest.raises(ValueError):
        ProviderCapabilities().supports('invented')


def test_sharekhan_master_identity():
    row = {'scripCode': 1, 'tradingSymbol': 'GOLDSTAR', 'instType': 'SM',
           'isinCode': 'INE405Y01013', 'companyName': 'GOLDSTAR POWER LIMITED',
           'lotSize': 0, 'tickSize': 1, 'expiry': None, 'strike': 0}
    instrument = normalize_instrument(row)
    assert instrument.provider_key == 'NC1'
    assert instrument.lot_size is None and instrument.strike is None
    assert normalize_instrument({**row, 'tradingSymbol': 'RENAMED'}).instrument_id == instrument.instrument_id


def test_sharekhan_history(instrument, calendar, session):
    row = {'open': 100, 'high': 103, 'low': 99, 'close': 102, 'qty': 10,
           'tradeDate': '02/01/2025', 'tradeTime': '09:15:00'}
    c = normalize_candle(row, instrument, '1m', calendar, session.closes_at)
    assert c.provider == 'sharekhan' and c.adjustment == 'unadjusted' and c.is_complete
    assert not normalize_candle(row, instrument, '1m', calendar, session.opens_at).is_complete


def feed_message():
    return json.dumps({'status': 100, 'message': 'feed', 'data': {'exchangeCode': 'NC', 'scripCode': 1,
        'lastUpdatedTime': '02/01/2025 09:16:00', 'ltp': 100, 'qty': 123, 'currentOI': 7,
        'bidPrice': 99, 'bidQty': 10, 'offPrice': 101, 'offQty': 20}})


def test_sharekhan_quote_decode(instrument):
    tick = decode_message(feed_message(), {'NC1': instrument})
    assert tick.provider == 'sharekhan' and tick.price == 100 and tick.open_interest == 7
    assert tick.cumulative_volume == 123 and tick.depth[0].ask_price == 101
    assert decode_message('pong', {}) is None


async def test_sharekhan_reconnect_resubscribe(instrument):
    sent = []
    class Socket:
        async def send(self, message):
            sent.append(json.loads(message))
        def __aiter__(self):
            async def messages():
                yield feed_message()
            return messages()
    class Connection:
        async def __aenter__(self):
            return Socket()
        async def __aexit__(self, *args):
            pass
    feed = SharekhanFeed('test', AsyncMock(return_value='synthetic'), AsyncMock(), AsyncMock(),
        connector=lambda *args, **kwargs: Connection(), sleep=AsyncMock())
    stream = feed.stream([instrument.model_copy(update={'provider_key': 'NC1'})])
    await anext(stream)
    await anext(stream)
    assert len([s for s in sent if s['action'] == 'subscribe']) == 2
    await feed.unsubscribe([instrument.instrument_id])
    assert sent[-1]['action'] == 'unsubscribe' and not feed.requested
    await stream.aclose()


def test_sharekhan_authenticated_token_manipulation():
    secret = 'x' * 32
    cipher = AESGCM(secret.encode())
    token = base64.urlsafe_b64encode(cipher.encrypt(bytes(16), b'request|customer', None)).decode()
    result = exchange_request_token(token, secret)
    assert cipher.decrypt(bytes(16), base64.urlsafe_b64decode(result + '=' * (-len(result) % 4)), None) == b'customer|request'
    with pytest.raises(Exception, match='INVALID_REQUEST_TOKEN'):
        exchange_request_token(token[:-5] + 'AAAAA', secret)


@pytest.mark.parametrize('provider', ['sharekhan', 'hdfc_sky'])
def test_generic_indicator_provenance(provider, candle, calendar, session):
    observation = CandleObservation(candle=candle.model_copy(update={'provider': provider, 'source': 'history'}),
                                    known_at=session.closes_at)
    validate_observation(observation, calendar, session.closes_at, None)
    with pytest.raises(IndicatorInputError, match='UNRECONCILED_FEED'):
        validate_observation(observation.model_copy(update={'candle': observation.candle.model_copy(
            update={'reconciled': False})}), calendar, session.closes_at, None)


async def test_redis_outage_recovery():
    call = AsyncMock(side_effect=[ConnectionError('synthetic'), 'recovered'])
    sleep = AsyncMock()
    assert await redis_call(call, sleep=sleep) is None
    sleep.assert_awaited_once_with(2)
    assert await redis_call(call, sleep=sleep) == 'recovered'


def test_status_never_contains_credentials():
    settings = Settings(sharekhan_api_key='sensitive-key', sharekhan_access_token='sensitive-token')
    payload = json.dumps(provider_catalog(settings))
    assert 'sensitive' not in payload
    assert 'NOT_VERIFIED' in payload
    assert migration_heads() == {'0004'}


async def test_sharekhan_rest_official_shape(instrument, calendar, session):
    paths = []
    def response(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={'status': 200, 'data': [
            {'open': 100, 'high': 103, 'low': 99, 'close': 102, 'qty': 10,
             'tradeDate': '02/01/2025', 'tradeTime': '09:15:00'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        provider = SharekhanProvider(SharekhanHTTP(client, 'test', 'test'), calendar)
        result = await provider.get_historical_candles(instrument.model_copy(update={'provider_key': 'NC1'}),
            '1m', session.session_date, session.session_date, session.closes_at + timedelta(days=1))
    assert len(result) == 1
    assert paths == ['/skapi/services/historical/NC/1/1minute']


def test_subscription_pools_priorities_and_limits(instrument):
    requests = [(2, instrument), (1, instrument.model_copy(update={'instrument_id': 'priority'}))]
    plans = plan_subscriptions('upstox', requests, 1, 2)
    assert plans[0].requested[0].instrument_id == 'priority'
    assert plans[1].connection_id == 'upstox:1'
    with pytest.raises(ValueError, match='CAPACITY'):
        plan_subscriptions('upstox', requests, 1, 1)


def test_provider_status_api_and_search_contract():
    from fastapi.testclient import TestClient

    from api.main import create_app
    app = create_app(Settings(admin_api_key='x' * 32, sharekhan_api_key='never-return-this'))
    with TestClient(app) as client:
        app.state.redis = AsyncMock()
        app.state.redis.get.return_value = None
        app.state.repo.instruments = AsyncMock(return_value=[])
        assert client.get('/api/providers').status_code == 401
        result = client.get('/api/providers', headers={'X-API-Key': 'x' * 32})
        assert result.status_code == 200
        assert [p['provider'] for p in result.json()] == ['upstox', 'sharekhan', 'hdfc_sky']
        assert 'never-return-this' not in result.text
        result = client.get('/api/instruments?q=TEST&limit=50&offset=100&active=false',
                            headers={'X-API-Key': 'x' * 32})
        assert result.status_code == 200
        app.state.repo.instruments.assert_awaited_once_with('TEST', 50, 100, False)


@pytest.mark.parametrize('code,fallback', [('AUTH_REQUIRED', True), ('INVALID_PROVIDER_RESPONSE', False)])
async def test_worker_fallback_only_for_availability(monkeypatch, code, fallback):
    from types import SimpleNamespace

    from market_data.providers.errors import ProviderError
    from market_data.worker import execute
    first = SimpleNamespace(code='sharekhan', capabilities=ProviderCapabilities(instrument_master=True),
        token_supplier=AsyncMock(return_value='test'), http=SimpleNamespace(token=''),
        get_instruments=AsyncMock(side_effect=ProviderError(code)))
    second = SimpleNamespace(code='upstox', capabilities=ProviderCapabilities(instrument_master=True),
        token_supplier=AsyncMock(return_value='test'), http=SimpleNamespace(token=''),
        get_instruments=AsyncMock(return_value=['fixture']))
    registry = ProviderRegistry()
    registry.register('sharekhan', lambda: first)
    registry.register('upstox', lambda: second)
    monkeypatch.setattr('market_data.worker.build_registry', AsyncMock(return_value=registry))
    repo = AsyncMock()
    repo.sync_instruments.return_value = 1
    settings = Settings(default_market_data_provider='sharekhan')
    task = execute({'kind': 'instrument_sync', 'payload': {}}, settings, repo,
                   SimpleNamespace(redis=AsyncMock()), None)
    if fallback:
        assert await task == {'count': 1}
        second.get_instruments.assert_awaited_once()
    else:
        with pytest.raises(ProviderError, match=code):
            await task
        second.get_instruments.assert_not_awaited()

