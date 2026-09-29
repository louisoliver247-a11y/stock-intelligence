import asyncio
import json
import logging
import random
from uuid import uuid4

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from market_data.upstox.http import ProviderError, UpstoxHTTP
from market_data.upstox.normalize import normalize_feed

log = logging.getLogger(__name__)


def decode_message(raw: bytes) -> dict:
    from market_data.upstox.MarketDataFeed_pb2 import FeedResponse

    message = FeedResponse()
    message.ParseFromString(raw)
    return MessageToDict(message)


class UpstoxFeed:
    def __init__(
        self,
        http: UpstoxHTTP,
        on_connect,
        on_disconnect,
        max_subscriptions=100,
        connector=connect,
        sleep=asyncio.sleep,
        token_supplier=None,
    ):
        self.http, self.on_connect, self.on_disconnect = http, on_connect, on_disconnect
        self.max_subscriptions, self.connector, self.sleep = max_subscriptions, connector, sleep
        self.token_supplier = token_supplier
        self.instruments = {}
        self.socket = None
        self.mode = "full"

    async def send(self, method: str, keys: list[str]):
        if self.socket is not None and keys:
            await self.socket.send(
                json.dumps(
                    {
                        "guid": str(uuid4()),
                        "method": method,
                        "data": {"mode": self.mode, "instrumentKeys": keys},
                    }
                ).encode()
            )

    async def unsubscribe(self, instrument_ids):
        keys = [k for k, i in self.instruments.items() if i.instrument_id in instrument_ids]
        await self.send("unsub", keys)
        for key in keys:
            self.instruments.pop(key, None)

    async def stream(self, instruments, mode="full"):
        if not 0 < len(instruments) <= self.max_subscriptions:
            raise ValueError("subscription count outside configured limit")
        self.instruments = {i.provider_key: i for i in instruments}
        self.mode = mode
        attempt = 0
        while self.instruments:
            try:
                if self.token_supplier:
                    self.http.token = await self.token_supplier()
                auth = await self.http.get("/v3/feed/market-data-feed/authorize")
                url = auth["authorized_redirect_uri"]
                if not url.startswith("wss://"):
                    raise ProviderError("INSECURE_FEED_URL")
                async with self.connector(
                    url, ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024, max_queue=32
                ) as socket:
                    self.socket = socket
                    await self.send("sub", list(self.instruments))
                    await self.on_connect()
                    log.info("feed_connected")
                    async for raw in socket:
                        if not isinstance(raw, bytes):
                            raise ProviderError("NON_BINARY_FEED")
                        for tick in normalize_feed(decode_message(raw), self.instruments):
                            attempt = 0
                            yield tick
                    raise ProviderError("FEED_ENDED")
            except asyncio.CancelledError:
                raise
            except (
                ConnectionClosed,
                OSError,
                TimeoutError,
                ProviderError,
                DecodeError,
                ValueError,
                KeyError,
            ):
                log.warning("feed_disconnected")
                await self.on_disconnect()
                await self.sleep(min(2 ** min(attempt, 6), 60) + random.random())
                attempt += 1
            finally:
                self.socket = None
