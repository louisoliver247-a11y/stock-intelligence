import asyncio
import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from market_data.jobs import JobQueue
from market_data.repository import MarketRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('disposable database required')
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


async def cleanup(engine, ids):
    async with engine.begin() as conn:
        for table in ('provider_candles', 'candle_revisions', 'candles', 'instrument_provider_mappings',
                      'instrument_metadata', 'instruments'):
            for identity in ids:
                await conn.execute(text(f'DELETE FROM {table} WHERE instrument_id=:id'), {'id': identity})


async def test_cross_provider_identity_search_and_provenance(engine, instrument, candle):
    repo = MarketRepository(engine, ['sharekhan', 'upstox'])
    instrument = instrument.model_copy(update={'isin': 'INE000TEST01'})
    sharekhan = instrument.model_copy(update={'instrument_id': 'other-provider', 'provider': 'sharekhan',
        'provider_key': 'NC123', 'symbol': 'DIFFERENT', 'provider_metadata': {'exchange': 'NC'}})
    try:
        await asyncio.gather(repo.sync_instruments([instrument]), repo.sync_instruments([sharekhan]))
        async with engine.connect() as conn:
            ids = (await conn.execute(text("SELECT instrument_id FROM instrument_provider_mappings "
                                           "WHERE provider_instrument_id IN ('NC123','NSE_EQ|TESTISIN')"))).scalars().all()
        assert len(ids) == 2 and len(set(ids)) == 1
        canonical = ids[0]
        mapped = await repo.mapped_instrument(canonical, 'sharekhan')
        assert mapped.provider_key == 'NC123'
        assert len(await repo.instruments('INE000TEST01', 1, 0)) == 1
        assert await repo.instruments('INE000TEST01', 1, 1) == []
        c = candle.model_copy(update={'instrument_id': canonical})
        await repo.persist([c], [])
        async with engine.connect() as conn:
            cutoff = (await conn.execute(text('SELECT clock_timestamp()'))).scalar_one()
        sk = c.model_copy(update={'provider': 'sharekhan', 'source': 'sharekhan_history', 'close': Decimal(101)})
        assert (await repo.persist([sk], []))['corrected'] == 1
        assert (await repo.persist([c.model_copy(update={'close': Decimal(100)})], []))['unchanged'] == 1
        rows = await repo.candles(canonical, '1m', c.timestamp, c.timestamp + timedelta(minutes=1))
        assert rows[0].provider == 'sharekhan' and rows[0].close == 101
        old = await repo.candles_as_of(canonical, '1m', c.timestamp, c.timestamp + timedelta(minutes=1), cutoff)
        assert old[0].candle.provider == 'upstox' and old[0].candle.close == 102
        async with engine.connect() as conn:
            assert (await conn.execute(text('SELECT count(*) FROM provider_candles WHERE instrument_id=:id'),
                                       {'id': canonical})).scalar_one() == 3
    finally:
        await cleanup(engine, [instrument.instrument_id, sharekhan.instrument_id])


async def test_symbol_alone_never_merges(engine, instrument):
    repo = MarketRepository(engine)
    second = instrument.model_copy(update={'instrument_id': 'separate-id', 'provider': 'sharekhan',
                                           'provider_key': 'NC22'})
    try:
        await repo.sync_instruments([instrument, second])
        assert (await repo.mapped_instrument(second.instrument_id, 'sharekhan')).instrument_id != instrument.instrument_id
    finally:
        await cleanup(engine, [instrument.instrument_id, second.instrument_id])


async def test_same_provider_scrips_with_shared_isin_stay_distinct(engine, instrument):
    repo = MarketRepository(engine)
    first = instrument.model_copy(update={
        'instrument_id': 'shared-isin-first', 'provider': 'sharekhan',
        'provider_key': 'NC801', 'isin': 'INE000DUPE01',
    })
    second = first.model_copy(update={
        'instrument_id': 'shared-isin-second', 'provider_key': 'NC802', 'symbol': 'SECOND',
    })
    try:
        assert await repo.sync_instruments([first, second]) == 2
        assert await repo.sync_instruments([second, first]) == 2
        assert (await repo.mapped_instrument(first.instrument_id, 'sharekhan')).provider_key == 'NC801'
        assert (await repo.mapped_instrument(second.instrument_id, 'sharekhan')).provider_key == 'NC802'
        assert len(await repo.instruments('INE000DUPE01')) == 2
    finally:
        await cleanup(engine, [first.instrument_id, second.instrument_id])


async def test_lease_fencing_and_concurrent_deduplication(engine):
    queue = JobQueue(engine, AsyncMock())
    key = 'test:' + uuid4().hex
    ids = []
    try:
        ids = await asyncio.gather(*(queue.enqueue('reconcile', {}, idempotency_key=key) for _ in range(8)))
        assert len(set(ids)) == 1
        claims = await asyncio.gather(queue.claim(), queue.claim())
        assert sum(c is not None for c in claims) == 1
        first = next(c for c in claims if c)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE system_jobs SET started_at=now()-interval '6 minutes' WHERE id=:id"),
                               {'id': first['id']})
        second = await queue.claim()
        assert second['lease_token'] != first['lease_token']
        assert not await queue.finish(first['id'], {'stale': True}, lease_token=first['lease_token'])
        await queue.heartbeat(first['id'], first['lease_token'])
        async with engine.connect() as conn:
            assert str((await conn.execute(text('SELECT lease_token FROM system_jobs WHERE id=:id'),
                                           {'id': first['id']})).scalar_one()) == second['lease_token']
        assert await queue.finish(second['id'], {}, lease_token=second['lease_token'])
        third = await queue.enqueue('reconcile', {}, idempotency_key=key)
        ids.append(third)
        assert third != ids[0]
    finally:
        async with engine.begin() as conn:
            for job_id in set(ids):
                await conn.execute(text('DELETE FROM system_jobs WHERE id=:id'), {'id': job_id})


async def test_sharekhan_auth_encrypted_storage(engine):
    import base64

    import httpx
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from config.settings import Settings
    from market_data.sharekhan.auth import SharekhanAuth
    redis = AsyncMock()
    redis.getdel.return_value = 'browser'
    secret = 's' * 32
    settings = Settings(sharekhan_api_key='synthetic', sharekhan_secret_key=secret,
                        token_encryption_key=Fernet.generate_key().decode())
    auth = SharekhanAuth(settings, engine, redis)
    request_token = base64.urlsafe_b64encode(AESGCM(secret.encode()).encrypt(
        bytes(16), b'request|customer', None)).decode()
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'status': 200, 'data': {'token': 'synthetic-private-token'}}))) as client:
            await auth.finish(request_token, 'state', 'browser', client)
        assert await auth.token() == 'synthetic-private-token'
        async with engine.connect() as conn:
            stored = (await conn.execute(text("SELECT encrypted_token FROM broker_connections "
                                               "WHERE provider='sharekhan'"))).scalar_one()
            assert 'synthetic-private-token' not in stored
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM broker_connections WHERE provider='sharekhan'"))
