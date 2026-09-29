from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app
from api.users import NewUser, hash_password, verify_password
from config.settings import Settings


def test_password_hashes_are_salted_and_verified():
    one = hash_password("test-password")
    assert one != hash_password("test-password")
    assert "test-password" not in one
    assert verify_password("test-password", one)
    assert not verify_password("wrong-password", one)


def test_user_input_validation():
    assert NewUser(email=" Test@Example.com ", password="password").email == "test@example.com"
    with pytest.raises(ValidationError):
        NewUser(email="invalid", password="password")
    with pytest.raises(ValidationError):
        NewUser(email="test@example.com", password="short")


def test_user_permissions_and_self_deletion():
    identity = {"id": uuid4(), "email": "test@example.com", "role": "user"}
    with TestClient(create_app(Settings(admin_api_key="x" * 32))) as client:
        assert client.get("/api/users").status_code == 401
        with patch("api.main.session_user", AsyncMock(return_value=identity)):
            headers = {"X-API-Key": "s" * 43}
            assert client.get("/api/users", headers=headers).status_code == 403
            assert client.post("/api/instruments/sync", headers=headers).status_code == 403
            identity["role"] = "admin"
            response = client.delete(f"/api/users/{identity['id']}", headers=headers)
            assert response.status_code == 409
            assert response.json()["detail"] == "CANNOT_DELETE_YOUR_OWN_ACCOUNT"
