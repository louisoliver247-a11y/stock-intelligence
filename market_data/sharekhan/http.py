import asyncio
import time

import httpx

from market_data.providers.errors import ProviderError


class SharekhanHTTP:
    def __init__(self, client, api_key: str, token: str, retries=3):
        self.client, self.api_key, self.token, self.retries = client, api_key, token, retries
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def get(self, path):
        if not self.api_key or not self.token:
            raise ProviderError("AUTH_REQUIRED")
        if not path.startswith(('/master/', '/historical/')):
            raise ProviderError('UNSUPPORTED_ENDPOINT')
        for attempt in range(self.retries + 1):
            async with self._lock:
                await asyncio.sleep(max(0, .5 - (time.monotonic() - self._last)))
                self._last = time.monotonic()
                try:
                    response = await self.client.get('https://api.sharekhan.com/skapi/services' + path,
                        headers={'api-key': self.api_key, 'access-token': self.token,
                                 'Content-Type': 'application/json'})
                except httpx.TransportError:
                    response = None
            if response is not None and response.status_code not in (429, 500, 502, 503, 504):
                if response.status_code in (401, 403):
                    raise ProviderError('AUTH_REQUIRED')
                if response.status_code != 200:
                    raise ProviderError('PROVIDER_HTTP_ERROR')
                try:
                    body = response.json()
                    if body['status'] not in (200, 'success') or not isinstance(body['data'], list):
                        raise ValueError()
                    return body['data']
                except (ValueError, KeyError, TypeError):
                    raise ProviderError('INVALID_PROVIDER_RESPONSE') from None
            if attempt < self.retries:
                await asyncio.sleep(min(2 ** attempt, 30))
        raise ProviderError('PROVIDER_TEMPORARILY_UNAVAILABLE')
