import base64
import secrets
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text

from market_data.providers.errors import ProviderError
from market_data.upstox.auth import BrokerAuth


def exchange_request_token(request_token: str, secret: str) -> str:
    """Sharekhan version 1005 wire protocol; authenticate the GCM tag before using plaintext."""
    try:
        key = secret.encode()
        if len(key) != 32:
            raise ValueError()
        cipher = AESGCM(key)
        raw = base64.urlsafe_b64decode(request_token + '=' * (-len(request_token) % 4))
        parts = cipher.decrypt(bytes(16), raw, None).decode().split('|')
        if len(parts) != 2 or not all(parts):
            raise ValueError()
        encrypted = cipher.encrypt(bytes(16), f'{parts[1]}|{parts[0]}'.encode(), None)
        return base64.urlsafe_b64encode(encrypted).rstrip(b'=').decode()
    except (ValueError, InvalidTag, UnicodeError):
        raise ProviderError('INVALID_REQUEST_TOKEN') from None


class SharekhanAuth(BrokerAuth):
    async def start(self):
        self.cipher()
        if not self.settings.sharekhan_api_key.get_secret_value() or not self.settings.sharekhan_secret_key.get_secret_value():
            raise ProviderError('SHAREKHAN_AUTH_NOT_CONFIGURED')
        state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        await self.redis.set(f'sharekhan:auth:{state}', binding, ex=600, nx=True)
        query = urlencode({'api_key': self.settings.sharekhan_api_key.get_secret_value(),
                           'state': state, 'version_id': '1005'})
        return 'https://api.sharekhan.com/skapi/auth/login.html?' + query, binding

    async def finish(self, request_token, state, binding, client):
        expected = await self.redis.getdel(f'sharekhan:auth:{state}')
        if not expected or not secrets.compare_digest(expected, binding):
            raise ProviderError('INVALID_AUTH_STATE', 400)
        manipulated = exchange_request_token(request_token, self.settings.sharekhan_secret_key.get_secret_value())
        try:
            response = await client.post('https://api.sharekhan.com/skapi/services/access/token',
                json={'apiKey': self.settings.sharekhan_api_key.get_secret_value(),
                      'requestToken': manipulated, 'state': state, 'versionId': '1005'})
            response.raise_for_status()
            body = response.json()
            if body.get('status') not in (200, 'success'):
                raise ValueError()
            token = body['data']['token']
            if not isinstance(token, str) or not token:
                raise ValueError()
            encrypted = self.cipher().encrypt(token.encode()).decode()
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ProviderError('AUTH_EXCHANGE_FAILED') from None
        async with self.engine.begin() as conn:
            await conn.execute(text("""INSERT INTO broker_connections(provider,encrypted_token)
                VALUES ('sharekhan',:token) ON CONFLICT(provider) DO UPDATE SET
                encrypted_token=excluded.encrypted_token,updated_at=now()"""), {'token': encrypted})

    async def token(self):
        manual = self.settings.sharekhan_access_token.get_secret_value()
        if manual:
            return manual
        async with self.engine.connect() as conn:
            encrypted = (await conn.execute(text(
                "SELECT encrypted_token FROM broker_connections WHERE provider='sharekhan'"))).scalar_one_or_none()
        return self.cipher().decrypt(encrypted.encode()).decode() if encrypted else ''
