import os
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from market_data.repository import MarketRepository

pytestmark = pytest.mark.integration


async def test_postgres_idempotency_correction_and_partial_protection(instrument, candle):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; requires migrated disposable PostgreSQL")
    engine = create_async_engine(url)
    repo = MarketRepository(engine)
    try:
        await repo.sync_instruments([instrument])
        assert (await repo.persist([candle], []))["inserted"] == 1
        assert (await repo.persist([candle], []))["unchanged"] == 1
        async with engine.connect() as conn:
            original_cutoff = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
        corrected = candle.model_copy(update={"close": Decimal(101)})
        assert (await repo.persist([corrected], []))["corrected"] == 1
        partial = corrected.model_copy(update={"is_complete": False, "source": "upstox_feed"})
        assert (await repo.persist([partial], []))["unchanged"] == 1
        rows = await repo.candles(
            instrument.instrument_id, "1m", candle.timestamp, candle.timestamp + timedelta(minutes=1)
        )
        assert rows == [corrected]
        original = await repo.candles_as_of(
            instrument.instrument_id, "1m", candle.timestamp, candle.timestamp + timedelta(minutes=1),
            as_of=original_cutoff,
        )
        assert len(original) == 1 and original[0].candle == candle
        async with engine.connect() as conn:
            current_cutoff = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
        current = await repo.candles_as_of(
            instrument.instrument_id, "1m", candle.timestamp, candle.timestamp + timedelta(minutes=1),
            as_of=current_cutoff,
        )
        assert len(current) == 1 and current[0].candle == corrected
        assert current[0].revision == original[0].revision + 1
        async with engine.connect() as conn:
            old = (
                await conn.execute(
                    text("SELECT snapshot FROM candle_revisions WHERE instrument_id=:id"),
                    {"id": instrument.instrument_id},
                )
            ).scalar_one()
            assert Decimal(old["close"]) == 102
    finally:
        async with engine.begin() as conn:
            for table in ["provider_candles", "instrument_provider_mappings", "candle_revisions", "candles", "instrument_metadata", "instruments"]:
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE instrument_id=:id"), {"id": instrument.instrument_id}
                )
        await engine.dispose()
