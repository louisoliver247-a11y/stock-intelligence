import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import Settings
from market_data.jobs import JobQueue
from market_data.repository import MarketRepository
from market_data.upstox.auth import BrokerAuth
from market_data.worker import execute

pytestmark = pytest.mark.integration


def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    return url


async def test_job_ingestion_end_to_end(instrument, session):
    url = database_url()
    engine = create_async_engine(url)
    repo = MarketRepository(engine)
    redis = AsyncMock()
    queue = JobQueue(engine, redis)
    job_id = None
    try:
        await repo.sync_instruments([instrument])
        await repo.save_sessions([session])
        settings = Settings(database_url=url, upstox_access_token="test-token")
        auth = BrokerAuth(settings, engine, redis)
        job_id = await queue.enqueue(
            "history",
            {
                "instrument_id": instrument.instrument_id,
                "timeframe": "1m",
                "start": session.session_date.isoformat(),
                "end": session.session_date.isoformat(),
            },
            1,
        )
        job = await queue.claim()
        assert str(job["id"]) == job_id
        assert await queue.claim() is None
        records = [
            [(session.opens_at + timedelta(minutes=i)).isoformat(), 100, 103, 99, 102, 10] for i in range(375)
        ]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"status": "success", "data": {"candles": records}})
            )
        ) as client:
            result = await execute(job, settings, repo, auth, client)
        assert result == {"inserted": 375, "corrected": 0, "unchanged": 0, "issues": 0}
        await queue.finish(job_id, result, lease_token=job["lease_token"])
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT state,attempts FROM system_jobs WHERE id=:id"), {"id": job_id}
                )
            ).one()
            assert row == ("SUCCEEDED", 1)
    finally:
        async with engine.begin() as conn:
            if job_id:
                await conn.execute(text("DELETE FROM system_jobs WHERE id=:id"), {"id": job_id})
            for table in ["provider_candles", "instrument_provider_mappings", "candles", "instrument_metadata", "instruments"]:
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE instrument_id=:id"), {"id": instrument.instrument_id}
                )
            await conn.execute(text("DELETE FROM exchange_sessions WHERE source='synthetic_test'"))
        await engine.dispose()


async def test_encrypted_oauth_token_persistence():
    url = database_url()
    engine = create_async_engine(url)
    redis = AsyncMock()
    redis.getdel.return_value = "test-binding"
    settings = Settings(
        database_url=url,
        token_encryption_key=Fernet.generate_key().decode(),
        upstox_client_id="client",
        upstox_client_secret="secret",
    )
    auth = BrokerAuth(settings, engine, redis)
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"access_token": "synthetic-private-token"})
            )
        ) as client:
            await auth.finish("test-code", "test-state", "test-binding", client)
        assert await auth.token() == "synthetic-private-token"
        async with engine.connect() as conn:
            stored = (
                await conn.execute(
                    text("SELECT encrypted_token FROM broker_connections WHERE provider='upstox'")
                )
            ).scalar()
            assert "synthetic-private-token" not in stored
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM broker_connections WHERE provider='upstox'"))
        await engine.dispose()


async def test_abandoned_job_recovery_and_priority():
    engine = create_async_engine(database_url())
    queue = JobQueue(engine, AsyncMock())
    ids = []
    try:
        low = await queue.enqueue("instrument_sync", {}, 3)
        high = await queue.enqueue("instrument_sync", {}, 1)
        ids = [low, high]
        first = await queue.claim()
        assert str(first["id"]) == high
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE system_jobs SET started_at=:old WHERE id=:id"),
                {"id": high, "old": datetime.now(UTC) - timedelta(minutes=6)},
            )
        retry = await queue.claim()
        assert str(retry["id"]) == high
        await queue.finish(high, {"count": 1}, lease_token=retry["lease_token"])
        assert str((await queue.claim())["id"]) == low
    finally:
        async with engine.begin() as conn:
            for job_id in ids:
                await conn.execute(text("DELETE FROM system_jobs WHERE id=:id"), {"id": job_id})
        await engine.dispose()
