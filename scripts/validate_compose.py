"""Structural checks only; use docker compose config and real containers for deployment validation."""

from pathlib import Path

import yaml

config = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
expected = {"postgres", "redis", "migrate", "api", "worker", "feed", "frontend"}
assert set(config["services"]) == expected
assert not config["services"]["postgres"].get("ports")
assert not config["services"]["redis"].get("ports")
assert config["services"]["frontend"]["ports"] == ["127.0.0.1:8080:8080"]
for name in ["api", "worker", "feed"]:
    assert config["services"][name]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
for service in config["services"].values():
    if "build" in service:
        assert Path(service["build"]["dockerfile"]).is_file()
print(
    "Compose YAML structure passed: 7 services; private DB/Redis; migration dependencies; build files present."
)
print("Docker runtime, image availability, Timescale and Redis behavior are NOT validated by this check.")
