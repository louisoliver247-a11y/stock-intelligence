import httpx
import pytest

from scripts.check_deployment import check


@pytest.mark.parametrize("failure", [None, "redis", "worker", "auth", "malformed", "redirect"])
def test_smoke_requires_dependencies_worker_and_access_control(failure):
    def handler(request):
        path = request.url.path
        if path == "/":
            return httpx.Response(200, text='<div id="root"></div>')
        if path.endswith("/live"):
            return httpx.Response(200, json={"status": "ok"})
        if path.endswith("/ready"):
            if failure == "malformed":
                return httpx.Response(200, text="not json")
            return httpx.Response(200, json={"database": "ready", "redis":
                                            "unavailable" if failure == "redis" else "ready"})
        if "X-API-Key" not in request.headers:
            return httpx.Response(200 if failure == "auth" else 401)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.invalid"})
        return httpx.Response(200, json={"worker": "NOT_RUNNING" if failure == "worker" else "RUNNING",
                                       "services": {"database": "ready", "redis": "ready"}})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler)) as client:
        result = check(client, "test-secret-" * 4)
    assert result["deployment_smoke"] == ("PASS" if failure is None else "FAIL")
    assert result["live_data_acceptance"] == "NOT_VERIFIED"
    assert "test-secret" not in str(result)


def test_unreachable_deployment_fails_without_leaking_exception():
    def handler(request):
        raise httpx.ConnectError("sensitive diagnostic", request=request)

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler)) as client:
        result = check(client, "")
    assert result["deployment_smoke"] == "FAIL"
    assert result["checks"]["operator_and_worker"] == "NOT_CONFIGURED"
    assert "sensitive" not in str(result)
