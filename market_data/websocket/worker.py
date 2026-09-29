import asyncio
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis

from api.logging import configure_logging
from config.settings import get_settings
from market_data.db import create_engine
from market_data.jobs import JobQueue
from market_data.providers.factory import ProviderContext, build_registry
from market_data.providers.models import QualityIssue
from market_data.providers.subscriptions import plan_subscriptions
from market_data.repository import MarketRepository
from market_data.resilience import redis_call
from market_data.websocket.aggregation import TickAggregator


async def run():
    configure_logging()
    settings = get_settings()
    engine = create_engine(settings)
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True,
                           socket_connect_timeout=3, socket_timeout=10)
    repo, queue = MarketRepository(engine, settings.provider_preference), JobQueue(engine, redis)
    auth = ProviderContext(engine, redis)

    async def cache_set(key, value, **kwargs):
        await redis_call(lambda: redis.set(key, value, **kwargs))
        if key.startswith('feed:'):
            await redis_call(lambda: redis.set(
                f"provider:{settings.default_market_data_provider}:{key[5:]}", value, **kwargs))

    try:
        if not settings.feed_instrument_ids:
            await cache_set("feed:status", "DISABLED", ex=90)
            return
        instruments = [await repo.mapped_instrument(i, settings.default_market_data_provider) for i in settings.feed_instrument_ids]
        by_id = {i.instrument_id: i for i in instruments}
        aggregator = TickAggregator(await repo.calendar())

        async def reconcile():
            for instrument in instruments:
                if provider.capabilities.intraday_candles:
                    await queue.enqueue("reconcile", {"instrument_id": instrument.instrument_id,
                        "provider": provider.code}, 1,
                        idempotency_key=f"reconcile:{provider.code}:{instrument.instrument_id}")

        async def connected():
            aggregator.reset()
            await cache_set("feed:status", "CONNECTED", ex=90)
            await reconcile()

        async def disconnected():
            aggregator.reset()
            await cache_set("feed:status", "DISCONNECTED", ex=90)
            await repo.persist([], [QualityIssue(code="FEED_DISCONNECTED")])

        async def periodic():
            while True:
                aggregator.calendar = await repo.calendar()
                await reconcile()
                await cache_set("feed:heartbeat", datetime.now(UTC).isoformat(), ex=90)
                await asyncio.sleep(settings.reconcile_seconds)

        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            registry = await build_registry(settings, client, aggregator.calendar, auth, connected, disconnected)
            provider = registry.get(settings.default_market_data_provider)
            if not provider.capabilities.websocket_ticks:
                raise ValueError("LIVE_CAPABILITY_UNAVAILABLE")

            limit = getattr(provider, "subscription_limit", settings.max_subscriptions)
            plans = plan_subscriptions(provider.code, [(settings.feed_priorities.get(i.instrument_id, 2), i)
                for i in instruments], min(limit, settings.max_subscriptions), settings.max_feed_connections)

            async def consume(adapter, plan):
                async for tick in adapter.subscribe_ticks(plan.requested):
                    plan.active.add(tick.instrument_id)
                    plan.resubscribing = False
                    now = datetime.now(UTC)
                    await cache_set("feed:last_received", now.isoformat(), ex=90)
                    await cache_set("feed:status", "CONNECTED", ex=90)
                    candle, issue = aggregator.update(tick, by_id[tick.instrument_id], now)
                    if issue and issue != "DUPLICATE_TICK":
                        await repo.persist(
                            [],
                            [
                                QualityIssue(
                                    code=issue, instrument_id=tick.instrument_id, timestamp=tick.timestamp
                                )
                            ],
                        )
                    if issue not in {"FUTURE_TICK", "OUT_OF_ORDER_TICK", "DUPLICATE_TICK"}:
                        await cache_set(f"quote:{tick.instrument_id}", tick.model_copy(
                            update={"received_at": now, "known_at": now}).model_dump_json(), ex=120)
                    if candle:
                        await cache_set(
                            f"active_candle:{tick.instrument_id}", candle.model_dump_json(), ex=120
                        )

            async with asyncio.TaskGroup() as group:
                group.create_task(periodic())
                for plan in plans:
                    async def connection_up(plan=plan):
                        plan.active.clear()
                        plan.resubscribing = True
                        for item in plan.requested:
                            aggregator.active.pop(item.instrument_id, None)
                            aggregator.last.pop(item.instrument_id, None)
                        await cache_set(f"feed:connection:{plan.connection_id}", "CONNECTED", ex=90)
                        await reconcile()

                    async def connection_down(plan=plan):
                        plan.active.clear()
                        plan.resubscribing = True
                        for item in plan.requested:
                            aggregator.active.pop(item.instrument_id, None)
                            aggregator.last.pop(item.instrument_id, None)
                        await cache_set(f"feed:connection:{plan.connection_id}", "DISCONNECTED", ex=90)
                        await cache_set("feed:status", "DEGRADED", ex=90)
                        await repo.persist([], [QualityIssue(code="FEED_DISCONNECTED",
                            details={"provider": plan.provider, "connection": plan.connection_id})])

                    connection_registry = await build_registry(settings, client, aggregator.calendar,
                                                               auth, connection_up, connection_down)
                    group.create_task(consume(connection_registry.get(provider.code), plan))
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
