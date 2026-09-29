import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from redis.asyncio import Redis
from sqlalchemy import text

from api.logging import configure_logging
from api.users import router as users_router
from api.users import session_user
from config.settings import Settings, get_settings
from market_data.aggregation import aggregate_minutes
from market_data.calendar import IST
from market_data.db import create_engine
from market_data.jobs import JobQueue
from market_data.migration_status import migration_heads
from market_data.providers.errors import ProviderError
from market_data.providers.models import ExchangeSession, Timeframe
from market_data.providers.status import provider_catalog
from market_data.repository import MarketRepository
from market_data.upstox.auth import BrokerAuth


class HistoryRequest(BaseModel):
    instrument_id: str
    provider: str | None = None
    timeframe: Literal["1m", "1d"] = "1m"
    start: date
    end: date
    priority: int = Field(2, ge=1, le=3)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end < self.start or (self.end - self.start).days > 366:
            raise ValueError("request must span at most 366 days with start <= end")
        if self.end > datetime.now(IST).date():
            raise ValueError("future history is not available")
        return self


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        app.state.engine = create_engine(settings)
        app.state.redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
        app.state.repo = MarketRepository(app.state.engine, settings.provider_preference)
        app.state.queue = JobQueue(app.state.engine, app.state.redis)
        app.state.auth = BrokerAuth(settings, app.state.engine, app.state.redis)
        yield
        await app.state.redis.aclose()
        await app.state.engine.dispose()

    app = FastAPI(title="Stock Intelligence · Market Data", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    async def operator(request: Request, x_api_key: Annotated[str | None, Header()] = None):
        key = settings.admin_api_key.get_secret_value()
        if len(key) >= 32 and x_api_key and secrets.compare_digest(key, x_api_key):
            return {"role": "admin", "id": None}
        if not x_api_key:
            raise HTTPException(503 if len(key) < 32 else 401, "UNAUTHORIZED")
        if not x_api_key or len(x_api_key) != 43:
            raise HTTPException(401, "UNAUTHORIZED")
        identity = await session_user(app, x_api_key)
        if identity["role"] != "admin" and request.method != "GET" and request.url.path != "/api/auth/logout":
            raise HTTPException(403, "ADMIN_REQUIRED")
        return identity

    app.include_router(users_router(operator))

    protected = [Depends(operator)]

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse(status_code=400 if exc.status == 400 else 502, content={"detail": exc.code})

    @app.exception_handler(LookupError)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": "NOT_FOUND"})

    @app.get("/api/health/live")
    async def live():
        return {"status": "ok", "version": "0.1.0", "scope": "milestones_0_1"}

    async def dependency_status():
        result = {"database": "unavailable", "redis": "unavailable"}
        try:
            async with asyncio.timeout(4):
                async with app.state.engine.connect() as conn:
                    revision = set((await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars())
                    result["database"] = "ready" if revision == migration_heads() else "migration_required"
        except Exception:
            pass
        try:
            if await app.state.redis.ping():
                result["redis"] = "ready"
        except Exception:
            pass
        return result

    @app.get("/api/health/ready")
    async def ready(response: Response):
        status = await dependency_status()
        if any(v != "ready" for v in status.values()):
            response.status_code = 503
        return status

    @app.get("/api/market/status", dependencies=protected)
    async def market_status():
        status = await dependency_status()
        data = {
            "services": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "timezone": "Asia/Kolkata",
            "market_session": "UNKNOWN",
            "feed": "UNKNOWN",
            "worker": "UNKNOWN",
            "integrity": "NOT_VERIFIED",
            "counts": {},
            "latest_candle": None,
        }
        if status["redis"] == "ready":
            data["feed"] = await app.state.redis.get("feed:status") or "NOT_RUNNING"
            data["worker"] = "RUNNING" if await app.state.redis.get("worker:heartbeat") else "NOT_RUNNING"
            data["last_feed_received"] = await app.state.redis.get("feed:last_received")
        if status["database"] == "ready":
            async with app.state.engine.connect() as conn:
                for label, query in {
                    "instruments": "SELECT count(*) FROM instruments",
                    "candles": "SELECT count(*) FROM candles",
                    "quality_issues": "SELECT count(*) FROM data_quality_issues WHERE resolved_at IS NULL",
                    "queued_jobs": "SELECT count(*) FROM system_jobs WHERE state IN ('QUEUED','RUNNING')",
                }.items():
                    data["counts"][label] = (await conn.execute(text(query))).scalar()
                latest = (
                    await conn.execute(text("SELECT max(timestamp) FROM candles WHERE is_complete"))
                ).scalar()
                data["latest_candle"] = latest.isoformat() if latest else None
            try:
                now = datetime.now(IST)
                session = (await app.state.repo.calendar()).session("NSE", now.date())
                data["market_session"] = (
                    "OPEN" if session.opens_at and session.opens_at <= now < session.closes_at else "CLOSED"
                )
            except ValueError:
                pass
        return data

    @app.get("/api/providers", dependencies=protected)
    async def providers():
        rows = provider_catalog(settings)
        for row in rows:
            code = row["provider"]
            try:
                async with app.state.engine.connect() as conn:
                    row["instrument_mappings"] = (await conn.execute(text(
                        "SELECT count(*) FROM instrument_provider_mappings WHERE provider=:p AND active"),
                        {"p": code})).scalar_one()
                    latest = (await conn.execute(text(
                        "SELECT max(received_at) FROM provider_candles WHERE provider=:p"),
                        {"p": code})).scalar_one()
                    row["last_successful_market_update"] = latest.isoformat() if latest else None
                    if latest:
                        row["rest_status"] = "PREVIOUSLY_SUCCEEDED"
            except Exception:
                row["last_error_category"] = "DATABASE_UNAVAILABLE_OR_MIGRATION_REQUIRED"
            try:
                row["websocket_status"] = await app.state.redis.get(f"provider:{code}:status") or "NOT_RUNNING"
                row["rest_status"] = await app.state.redis.get(f"provider:{code}:rest_status") or row["rest_status"]
                row["last_error_category"] = await app.state.redis.get(f"provider:{code}:last_error") or row["last_error_category"]
                received = await app.state.redis.get(f"provider:{code}:last_received")
                if received:
                    row["last_successful_market_update"] = received
                    row["authenticated"] = "RECENT_MARKET_RESPONSE"
            except Exception:
                row["websocket_status"] = "UNKNOWN"
        return rows

    @app.get("/api/providers/{provider}/status", dependencies=protected)
    async def provider_status(provider: str):
        for row in await providers():
            if row["provider"] == provider:
                return row
        raise HTTPException(404, "UNKNOWN_PROVIDER")

    @app.get("/api/instruments", dependencies=protected)
    async def instruments(q: str = "", limit: int = Query(100, ge=1, le=500),
                          offset: int = Query(0, ge=0), active: bool | None = True):
        return await app.state.repo.instruments(q, limit, offset, active)

    @app.post("/api/instruments/sync", dependencies=protected, status_code=202)
    async def sync_instruments(provider: str | None = None):
        return {"job_id": await app.state.queue.enqueue("instrument_sync", {"provider": provider})}

    @app.post("/api/calendar/sessions", dependencies=protected)
    async def import_sessions(sessions: Annotated[list[ExchangeSession], Field(max_length=400)]):
        return {"count": await app.state.repo.save_sessions(sessions)}

    @app.post("/api/history/ingest", dependencies=protected, status_code=202)
    async def ingest(body: HistoryRequest):
        await app.state.repo.instrument(body.instrument_id)
        return {
            "job_id": await app.state.queue.enqueue("history", body.model_dump(mode="json"), body.priority)
        }

    @app.get("/api/candles", dependencies=protected)
    async def candles(
        instrument_id: str,
        start: AwareDatetime,
        end: AwareDatetime,
        timeframe: Timeframe = Timeframe.M1,
        limit: int = Query(5000, ge=1, le=10000),
    ):
        if start >= end or end - start > timedelta(days=366):
            raise HTTPException(422, "INVALID_RANGE")
        return await app.state.repo.candles(instrument_id, timeframe.value, start, end, limit)

    @app.get("/api/candles/aggregate", dependencies=protected)
    async def aggregate(instrument_id: str, start: AwareDatetime, end: AwareDatetime, timeframe: Timeframe):
        if start >= end or end - start > timedelta(days=7):
            raise HTTPException(422, "aggregation query must span at most seven days")
        rows = await app.state.repo.candles(instrument_id, "1m", start, end, 10000)
        try:
            return aggregate_minutes(
                rows, timeframe, await app.state.repo.calendar(), min(end, datetime.now(UTC))
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/jobs", dependencies=protected)
    async def jobs():
        async with app.state.engine.connect() as conn:
            return [
                dict(r)
                for r in (
                    await conn.execute(text("SELECT * FROM system_jobs ORDER BY created_at DESC LIMIT 100"))
                ).mappings()
            ]

    @app.get("/api/jobs/{job_id}", dependencies=protected)
    async def job(job_id: str):
        from uuid import UUID

        try:
            parsed = UUID(job_id)
        except ValueError:
            raise HTTPException(422, "INVALID_JOB_ID") from None
        async with app.state.engine.connect() as conn:
            row = (
                (await conn.execute(text("SELECT * FROM system_jobs WHERE id=:id"), {"id": parsed}))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise HTTPException(404, "NOT_FOUND")
            return dict(row)

    @app.get("/api/data-quality", dependencies=protected)
    async def quality(unresolved: bool = True):
        async with app.state.engine.connect() as conn:
            return [
                dict(r)
                for r in (
                    await conn.execute(
                        text("SELECT * FROM data_quality_issues WHERE NOT :unresolved OR resolved_at IS NULL "
                             "ORDER BY created_at DESC LIMIT 100"), {"unresolved": unresolved}
                    )
                ).mappings()
            ]

    class ResolutionRequest(BaseModel):
        note: str = Field(min_length=1, max_length=1000)
        action: Literal["acknowledged", "resolved"]

    @app.post("/api/data-quality/{issue_id}/resolve", dependencies=protected)
    async def resolve_quality(issue_id: int, body: ResolutionRequest):
        async with app.state.engine.begin() as conn:
            result = await conn.execute(text("""UPDATE data_quality_issues
                SET resolved_at=CASE WHEN :action='resolved' THEN now() ELSE resolved_at END,
                resolution=CAST(:resolution AS jsonb) WHERE id=:id"""),
                {"id": issue_id, "action": body.action,
                 "resolution": json.dumps({**body.model_dump(), "actor": "operator",
                                            "at": datetime.now(UTC).isoformat()})})
            if result.rowcount != 1:
                raise HTTPException(404, "NOT_FOUND")
            await conn.execute(text("INSERT INTO audit_logs(event,entity_id,details) "
                                    "VALUES ('quality_review',:id,CAST(:detail AS jsonb))"),
                               {"id": str(issue_id), "detail": body.model_dump_json()})
        return {"status": body.action}

    @app.post("/api/auth/sharekhan/start", dependencies=protected)
    async def sharekhan_start(response: Response):
        from market_data.sharekhan.auth import SharekhanAuth
        auth = SharekhanAuth(settings, app.state.engine, app.state.redis)
        url, binding = await auth.start()
        response.set_cookie("sharekhan_binding", binding, max_age=600, httponly=True,
                            samesite="lax", secure=settings.web_origin.startswith("https://"),
                            path="/api/auth/sharekhan")
        return {"authorization_url": url}

    @app.get("/api/auth/sharekhan/callback")
    async def sharekhan_callback(request: Request, request_token: str, state: str):
        from market_data.sharekhan.auth import SharekhanAuth
        auth = SharekhanAuth(settings, app.state.engine, app.state.redis)
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            await auth.finish(request_token, state, request.cookies.get("sharekhan_binding", ""), client)
        response = RedirectResponse(settings.web_origin + "/?broker=connected", status_code=303)
        response.delete_cookie("sharekhan_binding", path="/api/auth/sharekhan")
        return response

    @app.post("/api/auth/upstox/start", dependencies=protected)
    async def oauth_start(response: Response):
        url, binding = await app.state.auth.start()
        response.set_cookie(
            "oauth_binding",
            binding,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=settings.upstox_redirect_uri.startswith("https://"),
            path="/api/auth/upstox",
        )
        return {"authorization_url": url}

    @app.get("/api/auth/upstox/callback")
    async def oauth_callback(request: Request, code: str, state: str):
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            await app.state.auth.finish(code, state, request.cookies.get("oauth_binding", ""), client)
        response = RedirectResponse(settings.web_origin + "/?broker=connected", status_code=303)
        response.delete_cookie("oauth_binding", path="/api/auth/upstox")
        return response

    @app.get("/api/events", dependencies=protected)
    async def events(request: Request):
        async def stream():
            while not await request.is_disconnected():
                yield "event: status\ndata: " + json.dumps(await market_status()) + "\n\n"
                await asyncio.sleep(10)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    return app


app = create_app()
