"""Serve the built frontend and API together for the Windows local launcher."""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from api.main import create_app
from config.settings import Settings


def create_local_app(settings: Settings | None = None, directory: Path | None = None):
    app = create_app(settings)
    directory = directory or Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app.mount("/", StaticFiles(directory=directory, html=True, check_dir=False))
    return app


app = create_local_app()
