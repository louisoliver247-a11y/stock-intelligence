"""Read-only deployment smoke check. Does not certify provider data integrity."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values


def check(client: httpx.Client, key: str) -> dict:
    checks = {}

    def probe(name, path, predicate, headers=None):
        try:
            response = client.get(path, headers=headers)
            checks[name] = "PASS" if predicate(response) else "FAIL"
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            checks[name] = "FAIL"

    probe("frontend", "/", lambda r: r.status_code == 200 and 'id="root"' in r.text)
    probe("liveness", "/api/health/live", lambda r: r.status_code == 200 and r.json()["status"] == "ok")
    probe("readiness", "/api/health/ready", lambda r: r.status_code == 200 and
          r.json().get("database") == "ready" and r.json().get("redis") == "ready")
    probe("unauthenticated_access_denied", "/api/market/status", lambda r: r.status_code == 401)
    if len(key) >= 32:
        probe("operator_and_worker", "/api/market/status", lambda r: r.status_code == 200 and
              r.json().get("worker") == "RUNNING" and
              r.json().get("services") == {"database": "ready", "redis": "ready"},
              {"X-API-Key": key})
    else:
        checks["operator_and_worker"] = "NOT_CONFIGURED"
    return {"checked_at": datetime.now(UTC).isoformat(), "checks": checks,
            "deployment_smoke": "PASS" if all(v == "PASS" for v in checks.values()) else "FAIL",
            "live_data_acceptance": "NOT_VERIFIED",
            "timescale_acceptance": "NOT_VERIFIED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, help="New JSON report file; never overwritten")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        parser.error("base URL must be an HTTP(S) origin without credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("remote checks require HTTPS")
    values = dotenv_values(args.env_file) if args.env_file.is_file() else {}
    key = os.environ.get("ADMIN_API_KEY", values.get("ADMIN_API_KEY") or "")
    with httpx.Client(base_url=args.base_url, timeout=10, follow_redirects=False, trust_env=False) as client:
        result = check(client, key)
    serialized = json.dumps(result, indent=2)
    if args.output:
        try:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(serialized + "\n")
        except OSError:
            parser.exit(2, "Could not create output report; choose a new writable file.\n")
    print(serialized)
    raise SystemExit(0 if result["deployment_smoke"] == "PASS" else 1)


if __name__ == "__main__":
    main()
