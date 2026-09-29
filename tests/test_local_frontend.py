from fastapi.testclient import TestClient

from api.local import create_local_app
from config.settings import Settings


def test_local_frontend_preserves_api_authentication(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    app = create_local_app(Settings(admin_api_key="test-key-" * 5), tmp_path)
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="root"' in page.text
        assert client.get("/api/health/live").json()["status"] == "ok"
        assert client.get("/api/market/status").status_code == 401
        assert client.get("/.env.local").status_code == 404
        assert client.get("/../.env.local").status_code == 404
