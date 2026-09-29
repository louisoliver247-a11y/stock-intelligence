import asyncio
import logging
from contextlib import suppress
from datetime import UTC, date, datetime

import httpx
from redis.asyncio import Redis

from api.logging import configure_logging
from config.settings import get_settings
from market_data.db import create_engine
from market_data.historical.ingestion import HistoricalIngestion, validate_batch
from market_data.jobs import JobQueue
from market_data.providers.errors import ProviderError
from market_data.providers.factory import ProviderContext, authorize, build_registry
from market_data.providers.models import Timeframe
from market_data.repository import MarketRepository
from market_data.resilience import redis_call

log = logging.getLogger(__name__)


async def execute(job, settings, repo, auth, client):
    calendar = await repo.calendar()
    payload = job["payload"]
    registry = await build_registry(settings, client, calendar, auth)
    capability = {"instrument_sync": "instrument_master", "history": "historical_candles",
                  "reconcile": "intraday_candles"}.get(job["kind"])
    if not capability:
        raise ProviderError("UNKNOWN_JOB_KIND")
    preference = ([payload["provider"]] if payload.get("provider") else
                  [settings.default_market_data_provider, *settings.provider_preference])
    candidates = registry.candidates(preference, capability)
    if not candidates:
        raise ProviderError("CAPABILITY_UNAVAILABLE")
    last_error = None
    for provider in candidates:
        try:
            await authorize(provider)
            result = await execute_provider(job, settings, repo, calendar, provider)
            await redis_call(lambda: auth.redis.set(f"provider:{provider.code}:rest_status", "SUCCEEDED", ex=86400))
            await redis_call(lambda: auth.redis.set(f"provider:{provider.code}:last_error", "", ex=86400))
            return result
        except (ProviderError, LookupError) as exc:
            last_error = exc
            code = exc.code if isinstance(exc, ProviderError) else "PROVIDER_MAPPING_NOT_FOUND"
            await redis_call(lambda: auth.redis.set(f"provider:{provider.code}:last_error", code, ex=86400))
            # Invalid payloads must be investigated, never concealed by fallback.
            if isinstance(exc, ProviderError) and code not in {
                "BROKER_NOT_CONNECTED", "AUTH_REQUIRED", "UPSTREAM_UNREACHABLE",
                "PROVIDER_TEMPORARILY_UNAVAILABLE", "UPSTREAM_HTTP_ERROR",
            }:
                raise
            log.warning("provider_fallback", extra={"provider": provider.code, "category": code})
    raise last_error


async def execute_provider(job, settings, repo, calendar, provider):
    payload = job["payload"]
    if job["kind"] == "instrument_sync":
        return {"count": await repo.sync_instruments(await provider.get_instruments())}
    instrument = await repo.mapped_instrument(payload["instrument_id"], provider.code)
    as_of = datetime.now(UTC)
    if job["kind"] == "history":
        return await HistoricalIngestion(
            provider,
            repo,
            calendar,
            settings.history_chunk_days,
            settings.volume_baseline_period,
            settings.abnormal_volume_multiple,
        ).ingest(
            instrument,
            Timeframe(payload["timeframe"]),
            date.fromisoformat(payload["start"]),
            date.fromisoformat(payload["end"]),
            as_of,
        )
    if job["kind"] == "reconcile":
        from market_data.calendar import IST

        candles = await provider.get_intraday_candles(instrument, as_of)
        today = as_of.astimezone(IST).date()
        valid, issues = validate_batch(
            candles,
            instrument,
            Timeframe.M1,
            calendar,
            today,
            today,
            as_of,
            settings.volume_baseline_period,
            settings.abnormal_volume_multiple,
        )
        return await repo.persist(valid, issues)
    raise ValueError("UNKNOWN_JOB_KIND")


async def run():
    configure_logging()
    settings = get_settings()
    engine = create_engine(settings)
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True,
                           socket_connect_timeout=3, socket_timeout=10)
    queue, repo = JobQueue(engine, redis), MarketRepository(engine, settings.provider_preference)
    auth = ProviderContext(engine, redis)

    async def heartbeat(job_id, token):
        while True:
            await queue.heartbeat(job_id, token)
            await redis_call(lambda: redis.set("worker:heartbeat", datetime.now(UTC).isoformat(), ex=90))
            await asyncio.sleep(30)

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            while True:
                await redis_call(lambda: redis.set("worker:heartbeat", datetime.now(UTC).isoformat(), ex=90))
                job = await queue.claim()
                if not job:
                    await redis_call(lambda: redis.brpop(["jobs:1", "jobs:2", "jobs:3"], timeout=5))
                    continue
                lease = asyncio.create_task(heartbeat(job["id"], job["lease_token"]))
                try:
                    result = await execute(job, settings, repo, auth, client)
                    await queue.finish(job["id"], result, lease_token=job["lease_token"])
                    log.info("ingestion_job_succeeded")
                except Exception as exc:
                    code = exc.code if isinstance(exc, ProviderError) else "INGESTION_FAILED"
                    await queue.finish(job["id"], error=code, lease_token=job["lease_token"])
                    log.error("ingestion_job_failed")
                finally:
                    lease.cancel()
                    with suppress(asyncio.CancelledError):
                        await lease
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
