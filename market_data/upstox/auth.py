import secrets
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from config.settings import Settings
from market_data.upstox.http import ProviderError


class BrokerAuth:
    def __init__(self, settings: Settings, engine: AsyncEngine, redis: Redis):
        self.settings, self.engine, self.redis = settings, engine, redis

    def cipher(self) -> Fernet:
        try:
            return Fernet(self.settings.token_encryption_key.get_secret_value().encode())
        except (ValueError, TypeError):
            raise ProviderError("TOKEN_ENCRYPTION_NOT_CONFIGURED") from None

    async def start(self) -> tuple[str, str]:
        self.cipher()
        if not self.settings.upstox_client_id or not self.settings.upstox_client_secret.get_secret_value():
            raise ProviderError("OAUTH_NOT_CONFIGURED")
        state = secrets.token_urlsafe(32)
        binding = secrets.token_urlsafe(32)
        await self.redis.set(f"oauth:{state}", binding, ex=600, nx=True)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.upstox_client_id,
                "redirect_uri": self.settings.upstox_redirect_uri,
                "state": state,
            }
        )
        return f"https://api.upstox.com/v2/login/authorization/dialog?{query}", binding

    async def finish(self, code: str, state: str, binding: str, client: httpx.AsyncClient) -> None:
        expected = await self.redis.getdel(f"oauth:{state}")
        if not expected or not secrets.compare_digest(expected, binding):
            raise ProviderError("INVALID_OAUTH_STATE", 400)
        try:
            response = await client.post(
                "https://api.upstox.com/v2/login/authorization/token",
                data={
                    "code": code,
                    "client_id": self.settings.upstox_client_id,
                    "client_secret": self.settings.upstox_client_secret.get_secret_value(),
                    "redirect_uri": self.settings.upstox_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            encrypted = self.cipher().encrypt(response.json()["access_token"].encode()).decode()
        except (httpx.HTTPError, KeyError, ValueError):
            raise ProviderError("OAUTH_EXCHANGE_FAILED") from None
        async with self.engine.begin() as conn:
            await conn.execute(
                text("""INSERT INTO broker_connections(provider,encrypted_token)
                VALUES ('upstox',:token) ON CONFLICT(provider) DO UPDATE
                SET encrypted_token=excluded.encrypted_token,updated_at=now()"""),
                {"token": encrypted},
            )
            await conn.execute(text("INSERT INTO audit_logs(event) VALUES ('broker_connected')"))

    async def token(self) -> str:
        manual = self.settings.upstox_access_token.get_secret_value()
        if manual:
            return manual
        async with self.engine.connect() as conn:
            encrypted = (
                await conn.execute(
                    text("SELECT encrypted_token FROM broker_connections WHERE provider='upstox'")
                )
            ).scalar_one_or_none()
        return self.cipher().decrypt(encrypted.encode()).decode() if encrypted else ""
