import asyncio
import logging

from redis.exceptions import RedisError

log = logging.getLogger(__name__)


async def redis_call(operation, *, sleep=asyncio.sleep):
    """Redis is a wakeup/cache layer; DB work can continue during its outage."""
    try:
        return await operation()
    except (RedisError, OSError, TimeoutError):
        log.warning('redis_degraded')
        await sleep(2)
        return None
