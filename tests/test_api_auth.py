from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import Settings
from market_data.upstox.auth import BrokerAuth
from market_data.upstox.http import ProviderError


def test_liveness_requires_no_external_services():
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/health/live").json()["status"] == "ok"
        assert client.get("/api/instruments").status_code == 503


def test_mutations_require_operator_key():
    with TestClient(create_app(Settings(admin_api_key="x" * 32))) as client:
        assert client.post("/api/instruments/sync").status_code == 401
        assert client.get("/api/market/status", headers={"X-API-Key": "incorrect"}).status_code == 401
        assert (
            client.post(
                "/api/history/ingest",
                headers={"X-API-Key": "x" * 32},
                json={"instrument_id": "test", "start": "2025-02-01", "end": "2025-01-01"},
            ).status_code
            == 422
        )


async def test_oauth_state_random_expiring_and_browser_bound():
    redis = AsyncMock()
    auth = BrokerAuth(
        Settings(
            upstox_client_id="test",
            upstox_client_secret="test-secret",
            token_encryption_key=Fernet.generate_key().decode(),
        ),
        AsyncMock(),
        redis,
    )
    url, binding = await auth.start()
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["test"] and len(query["state"][0]) >= 32
    assert "test-secret" not in url
    assert redis.set.call_args.kwargs["ex"] == 600
    redis.getdel.return_value = "wrong-browser"
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError, match="INVALID_OAUTH_STATE"):
            await auth.finish("code", query["state"][0], binding, client)


def test_encrypted_token_round_trip():
    auth = BrokerAuth(Settings(token_encryption_key=Fernet.generate_key().decode()), AsyncMock(), AsyncMock())
    encrypted = auth.cipher().encrypt(b"private-token")
    assert b"private-token" not in encrypted
    assert auth.cipher().decrypt(encrypted) == b"private-token"
