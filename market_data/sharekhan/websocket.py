import asyncio
import json
import logging
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from market_data.providers.errors import ProviderError
from market_data.sharekhan.normalize import normalize_quote

log = logging.getLogger(__name__)


def decode_message(message, instruments):
    if message == 'pong':
        return None
    try:
        body = json.loads(message)
        if body.get('status') != 100:
            raise ValueError()
        if body.get('message') != 'feed':
            return None
        row = body['data']
        key = str(row['exchangeCode']) + str(row['scripCode'])
        if key not in instruments:
            return None
        return normalize_quote(row, instruments[key])
    except (ValueError, KeyError, TypeError):
        raise ProviderError('INVALID_FEED_MESSAGE') from None


class SharekhanFeed:
    def __init__(self, api_key, token_supplier, connected, disconnected, limit=100,
                 connector=connect, sleep=asyncio.sleep):
        self.api_key, self.token_supplier = api_key, token_supplier
        self.connected, self.disconnected = connected, disconnected
        self.limit = min(limit, 1000)
        self.connector, self.sleep = connector, sleep
        self.requested = {}
        self.active = set()
        self.socket = None
        self.connection_id = 'sharekhan:0'
        self.resubscribing = False

    async def unsubscribe(self, instrument_ids):
        keys = [key for key, instrument in self.requested.items() if instrument.instrument_id in instrument_ids]
        for key in keys:
            del self.requested[key]
            self.active.discard(key)
        if self.socket and keys:
            await self.socket.send(json.dumps({'action': 'unsubscribe', 'key': ['feed'],
                                               'value': [','.join(keys)]}))

    async def stream(self, instruments):
        if len(instruments) > self.limit:
            raise ProviderError('SUBSCRIPTION_LIMIT')
        self.requested = {i.provider_key: i for i in instruments}
        delay = 1
        while self.requested:
            try:
                token = await self.token_supplier()
                url = 'wss://stream.sharekhan.com/skstream/api/stream?' + urlencode(
                    {'ACCESS_TOKEN': token, 'API_KEY': self.api_key})
                async with self.connector(url, max_queue=128, max_size=1048576,
                                          ping_interval=30, ping_timeout=30) as socket:
                    self.socket = socket
                    self.resubscribing = True
                    await socket.send(json.dumps({'action': 'subscribe', 'key': ['feed'], 'value': ['']}))
                    await socket.send(json.dumps({'action': 'feed', 'key': ['ltp'],
                                                   'value': [','.join(self.requested)]}))
                    self.active = set(self.requested)
                    self.resubscribing = False
                    await self.connected()
                    async for message in socket:
                        tick = decode_message(message, self.requested)
                        if tick:
                            delay = 1
                            yield tick
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning('provider_feed_disconnected', extra={'provider': 'sharekhan'})
            finally:
                self.socket = None
                self.active.clear()
                await self.disconnected()
            await self.sleep(delay)
            delay = min(delay * 2, 60)
