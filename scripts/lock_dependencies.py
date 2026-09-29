"""Record the successfully tested environment without editable/local filesystem references."""

import importlib.metadata
from pathlib import Path

dev = {"pytest", "pytest-asyncio", "ruff", "grpcio", "grpcio-tools", "iniconfig", "pluggy", "pygments"}
excluded = {"stock-intelligence", "pip", "wheel", "setuptools"}
runtime, development = [], []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata["Name"]
    normalized = name.lower().replace("_", "-")
    if normalized in excluded:
        continue
    line = f"{name}=={distribution.version}"
    (development if normalized in dev else runtime).append(line)
Path("requirements.lock").write_text(
    "# Tested runtime dependencies\n" + "\n".join(sorted(runtime)) + "\n", encoding="utf-8"
)
Path("requirements-dev.lock").write_text(
    "-r requirements.lock\n" + "\n".join(sorted(development)) + "\n", encoding="utf-8"
)
