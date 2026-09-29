import asyncio

import httpx

from market_data.providers.errors import ProviderError


class UpstoxHTTP:
    def __init__(self, client: httpx.AsyncClient, token: str, retries: int = 3):
        self.client, self.token, self.retries = client, token, retries

    async def get(self, path: str, params: dict | None = None) -> dict:
        if not self.token:
            raise ProviderError("BROKER_NOT_CONNECTED", 401)
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.get(
                    "https://api.upstox.com" + path,
                    params=params,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
            except httpx.TransportError:
                if attempt == self.retries:
                    raise ProviderError("UPSTREAM_UNREACHABLE") from None
                await asyncio.sleep(min(2**attempt, 8))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.retries:
                    try:
                        delay = float(response.headers.get("Retry-After", 2**attempt))
                    except ValueError:
                        delay = 2**attempt
                    await asyncio.sleep(max(0, min(delay, 30)))
                    continue
            if response.is_error:
                raise ProviderError("UPSTREAM_HTTP_ERROR", response.status_code)
            try:
                payload = response.json()
                if payload.get("status") != "success":
                    raise ValueError()
                return payload["data"]
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ProviderError("UPSTREAM_INVALID_RESPONSE") from None
        raise ProviderError("UPSTREAM_RETRY_EXHAUSTED")
