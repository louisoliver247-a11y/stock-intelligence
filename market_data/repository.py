import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from market_data.calendar import SessionCalendar
from market_data.providers.models import Candle, CandleObservation, ExchangeSession, Instrument, QualityIssue


class MarketRepository:
    def __init__(self, engine: AsyncEngine, preference: list[str] | None = None):
        self.engine = engine
        self.preference = preference or ["upstox", "sharekhan", "hdfc_sky"]

    async def sync_instruments(self, instruments: list[Instrument]) -> int:
        if not instruments:
            raise ValueError("EMPTY_INSTRUMENT_MASTER")
        async with self.engine.begin() as conn:
            for instrument in instruments:
                if not instrument.provider_key or instrument.provider == "unknown":
                    raise ValueError("PROVIDER_IDENTITY_REQUIRED")
                # Serialize identity resolution to prevent duplicate canonical instruments.
                await conn.execute(text("SELECT pg_advisory_xact_lock(7349821)"))
                mapped = (await conn.execute(text("""SELECT instrument_id FROM instrument_provider_mappings
                    WHERE provider=:provider AND provider_instrument_id=:key"""),
                    {"provider": instrument.provider, "key": instrument.provider_key})).scalar_one_or_none()
                if mapped is None and instrument.isin and instrument.instrument_type == "EQ":
                    matches = (await conn.execute(text("""SELECT instrument_id FROM instruments
                        WHERE isin=:isin AND exchange=:exchange AND instrument_type='EQ'
                        AND expiry IS NULL AND strike IS NULL"""),
                        {"isin": instrument.isin, "exchange": instrument.exchange})).scalars().all()
                    if len(matches) == 1:
                        # An ISIN can occur under multiple distinct scrip codes.
                        # Only merge across providers, never two identities from
                        # the same provider into its single canonical mapping.
                        occupied = (await conn.execute(text("""SELECT 1
                            FROM instrument_provider_mappings
                            WHERE instrument_id=:id AND provider=:provider"""),
                            {"id": matches[0], "provider": instrument.provider})).scalar_one_or_none()
                        if occupied is None:
                            mapped = matches[0]
                if mapped:
                    instrument = instrument.model_copy(update={"instrument_id": mapped})
                values = instrument.model_dump()
                values["provider_key"] = instrument.provider_key if instrument.provider == "upstox" else None
                previous = (
                    await conn.execute(
                        text("SELECT row_to_json(i) FROM instruments i WHERE instrument_id=:id FOR UPDATE"),
                        {"id": instrument.instrument_id},
                    )
                ).scalar_one_or_none()
                await conn.execute(
                    text("""INSERT INTO instruments
                    (instrument_id,symbol,exchange,segment,name,isin,instrument_type,provider_key,active)
                    VALUES (:instrument_id,:symbol,:exchange,:segment,:name,:isin,:instrument_type,:provider_key,:active)
                    ON CONFLICT (instrument_id) DO UPDATE SET symbol=excluded.symbol,
                    name=excluded.name, isin=excluded.isin, provider_key=COALESCE(excluded.provider_key,instruments.provider_key),
                    exchange=excluded.exchange,segment=excluded.segment,instrument_type=excluded.instrument_type,
                    active=excluded.active, updated_at=now()"""),
                    values,
                )
                await conn.execute(text("""UPDATE instruments SET trading_symbol=:trading_symbol,
                    expiry=:expiry,strike=:strike,option_type=:option_type,lot_size=:lot_size,
                    tick_size=:tick_size,underlying_instrument_id=:underlying_instrument_id
                    WHERE instrument_id=:instrument_id"""), values)
                await conn.execute(text("""INSERT INTO instrument_provider_mappings
                    (instrument_id,provider,provider_instrument_id,provider_symbol,provider_exchange,
                     provider_segment,metadata,active)
                    VALUES (:instrument_id,:provider,:key,:symbol,:exchange,:segment,CAST(:metadata AS jsonb),:active)
                    ON CONFLICT(provider,provider_instrument_id) DO UPDATE SET
                    provider_symbol=excluded.provider_symbol,metadata=excluded.metadata,
                    active=excluded.active,updated_at=now()"""),
                    {**values, "key": instrument.provider_key,
                     "exchange": instrument.provider_metadata.get("exchange", instrument.exchange),
                     "metadata": json.dumps(instrument.provider_metadata)})
                if previous is None or any(previous.get(k) != v for k, v in values.items()):
                    await conn.execute(
                        text("""INSERT INTO instrument_metadata(instrument_id,snapshot)
                        VALUES (:id,CAST(:snapshot AS jsonb))"""),
                        {"id": instrument.instrument_id, "snapshot": instrument.model_dump_json()},
                    )
            await conn.execute(
                text("""INSERT INTO audit_logs(event,details)
                VALUES ('instrument_sync', CAST(:details AS jsonb))"""),
                {"details": json.dumps({"count": len(instruments)})},
            )
        return len(instruments)

    async def instruments(self, query: str = "", limit: int = 100, offset: int = 0, active: bool | None = True) -> list[Instrument]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("""SELECT * FROM instruments
                WHERE (symbol ILIKE :q OR name ILIKE :q OR isin ILIKE :q)
                AND (CAST(:active AS boolean) IS NULL OR active=:active)
                ORDER BY symbol,instrument_id LIMIT :limit OFFSET :offset"""),
                    {"q": f"%{query}%", "limit": limit, "offset": offset, "active": active},
                )
            ).mappings()
            return [Instrument.model_validate(dict(r)) for r in rows]

    async def mapped_instrument(self, instrument_id: str, provider: str) -> Instrument:
        instrument = await self.instrument(instrument_id)
        async with self.engine.connect() as conn:
            row = (await conn.execute(text("""SELECT * FROM instrument_provider_mappings
                WHERE instrument_id=:id AND provider=:provider AND active"""),
                {"id": instrument_id, "provider": provider})).mappings().one_or_none()
        if row is None:
            raise LookupError("PROVIDER_MAPPING_NOT_FOUND")
        return instrument.model_copy(update={"provider": provider,
            "provider_key": row["provider_instrument_id"], "provider_metadata": row["metadata"]})

    async def instrument(self, instrument_id: str) -> Instrument:
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text("SELECT * FROM instruments WHERE instrument_id=:id"), {"id": instrument_id}
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LookupError("INSTRUMENT_NOT_FOUND")
        return Instrument.model_validate(dict(row))

    async def calendar(self) -> SessionCalendar:
        async with self.engine.connect() as conn:
            rows = (await conn.execute(text("SELECT * FROM exchange_sessions"))).mappings()
            return SessionCalendar([ExchangeSession.model_validate(dict(r)) for r in rows])

    async def save_sessions(self, sessions: list[ExchangeSession]) -> int:
        async with self.engine.begin() as conn:
            for s in sessions:
                await conn.execute(
                    text("""INSERT INTO exchange_sessions
                    (exchange,session_date,opens_at,closes_at,source)
                    VALUES (:exchange,:session_date,:opens_at,:closes_at,:source)
                    ON CONFLICT(exchange,session_date) DO UPDATE SET opens_at=excluded.opens_at,
                    closes_at=excluded.closes_at,source=excluded.source"""),
                    s.model_dump(),
                )
            await conn.execute(
                text("""INSERT INTO audit_logs(event,details)
                VALUES ('calendar_import',CAST(:details AS jsonb))"""),
                {"details": json.dumps({"sessions": [s.model_dump(mode="json") for s in sessions]})},
            )
        return len(sessions)

    async def persist(self, candles: list[Candle], issues: list[QualityIssue]) -> dict:
        counts = {"inserted": 0, "corrected": 0, "unchanged": 0, "issues": len(issues)}
        async with self.engine.begin() as conn:
            for c in candles:
                if not c.provider or c.provider == "unknown":
                    raise ValueError("OBSERVATION_PROVIDER_REQUIRED")
                key = {
                    "instrument_id": c.instrument_id,
                    "timeframe": c.timeframe.value,
                    "timestamp": c.timestamp,
                }
                # Transaction-scoped lock also serializes the first INSERT for a candle key.
                await conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": f"{c.instrument_id}/{c.timeframe}/{c.timestamp.isoformat()}"},
                )
                latest = (await conn.execute(text("""SELECT revision,snapshot FROM provider_candles
                    WHERE provider=:provider AND instrument_id=:instrument_id AND timeframe=:timeframe
                    AND timestamp=:timestamp ORDER BY revision DESC LIMIT 1"""),
                    {**key, "provider": c.provider})).mappings().one_or_none()
                if latest is None or Candle.model_validate(latest["snapshot"]) != c:
                    await conn.execute(text("""INSERT INTO provider_candles
                        (provider,instrument_id,timeframe,timestamp,revision,snapshot,source,provider_instrument_id)
                        VALUES (:provider,:instrument_id,:timeframe,:timestamp,:revision,CAST(:snapshot AS jsonb),
                        :source,:provider_instrument_id)"""),
                        {**key, "provider": c.provider, "revision": latest["revision"]+1 if latest else 1,
                         "snapshot": c.model_dump_json(), "source": c.source,
                         "provider_instrument_id": c.provider_instrument_id})
                old = (
                    (
                        await conn.execute(
                            text("""SELECT * FROM candles WHERE instrument_id=:instrument_id
                    AND timeframe=:timeframe AND timestamp=:timestamp FOR UPDATE"""),
                            key,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if old:
                    old_c = Candle.model_validate(dict(old))
                    def rank(provider):
                        return self.preference.index(provider) if provider in self.preference else len(self.preference)
                    if old_c.provider != c.provider and (
                        rank(c.provider) >= rank(old_c.provider) or not c.is_complete or not c.reconciled
                    ):
                        counts["unchanged"] += 1
                        continue
                    if old_c == c or (old_c.is_complete and not c.is_complete):
                        counts["unchanged"] += 1
                        continue
                    await conn.execute(
                        text("""INSERT INTO candle_revisions
                        (instrument_id,timeframe,timestamp,revision,snapshot,known_at)
                        VALUES (:instrument_id,:timeframe,:timestamp,:revision,CAST(:snapshot AS jsonb),:known_at)"""),
                        {
                            **key,
                            "revision": old["revision"],
                            "known_at": old["known_at"],
                            "snapshot": old_c.model_dump_json(),
                        },
                    )
                    await conn.execute(
                        text("""INSERT INTO audit_logs(event,entity_id,details)
                        VALUES ('candle_correction',:instrument_id,CAST(:details AS jsonb))"""),
                        {
                            "instrument_id": c.instrument_id,
                            "details": json.dumps(
                                {"timestamp": c.timestamp.isoformat(), "revision": old["revision"] + 1}
                            ),
                        },
                    )
                values = c.model_dump()
                values["quality_flags"] = json.dumps(c.quality_flags)
                await conn.execute(
                    text("""INSERT INTO candles
                    (instrument_id,timeframe,timestamp,symbol,exchange,open,high,low,close,volume,
                     open_interest,is_complete,source,quality_flags,provider,provider_instrument_id,reconciled,adjustment)
                    VALUES (:instrument_id,:timeframe,:timestamp,:symbol,:exchange,:open,:high,:low,:close,:volume,
                     :open_interest,:is_complete,:source,CAST(:quality_flags AS jsonb),
                     :provider,:provider_instrument_id,:reconciled,:adjustment)
                    ON CONFLICT(instrument_id,timeframe,timestamp) DO UPDATE SET
                    open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
                    volume=excluded.volume,open_interest=excluded.open_interest,is_complete=excluded.is_complete,
                    provider=excluded.provider,provider_instrument_id=excluded.provider_instrument_id,
                    reconciled=excluded.reconciled,adjustment=excluded.adjustment,
                    source=excluded.source,quality_flags=excluded.quality_flags,known_at=now(),revision=candles.revision+1
                    """),
                    values,
                )
                counts["corrected" if old else "inserted"] += 1
            for issue in issues:
                await conn.execute(
                    text("""INSERT INTO data_quality_issues(instrument_id,timestamp,code,details)
                    VALUES (:instrument_id,:timestamp,:code,CAST(:details AS jsonb))"""),
                    {**issue.model_dump(), "details": json.dumps(issue.details)},
                )
        return counts

    async def candles(
        self, instrument_id: str, timeframe: str, start: datetime, end: datetime, limit: int = 5000
    ) -> list[Candle]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("""SELECT * FROM candles WHERE instrument_id=:id
                AND timeframe=:tf AND timestamp>=:start AND timestamp<:end
                ORDER BY timestamp LIMIT :limit"""),
                    {"id": instrument_id, "tf": timeframe, "start": start, "end": end, "limit": limit},
                )
            ).mappings()
            return [Candle.model_validate(dict(row)) for row in rows]

    async def candles_as_of(
        self, instrument_id: str, timeframe: str, start: datetime, end: datetime,
        as_of: datetime, limit: int = 5000,
    ) -> list[CandleObservation]:
        """Select only the candle revision available at the supplied system-time cutoff."""
        if any(value.tzinfo is None or value.utcoffset() is None for value in (start, end, as_of)):
            raise ValueError("timezone-aware boundaries required")
        if start >= end or not 1 <= limit <= 10000:
            raise ValueError("invalid range or limit")
        async with self.engine.connect() as conn:
            rows = (await conn.execute(text("""
                SELECT snapshot, known_at, revision FROM (
                    SELECT to_jsonb(c) - 'known_at' - 'revision' AS snapshot,
                           known_at, revision, timestamp
                    FROM candles c
                    WHERE instrument_id=:id AND timeframe=:tf AND timestamp>=:start
                      AND timestamp<:end AND known_at<=:as_of
                    UNION ALL
                    SELECT snapshot, known_at, revision, timestamp FROM candle_revisions
                    WHERE instrument_id=:id AND timeframe=:tf AND timestamp>=:start
                      AND timestamp<:end AND known_at<=:as_of AND superseded_at>:as_of
                ) versions ORDER BY timestamp LIMIT :limit
            """), {"id": instrument_id, "tf": timeframe, "start": start, "end": end,
                    "as_of": as_of, "limit": limit})).mappings()
            return [CandleObservation(candle=Candle.model_validate(row["snapshot"]),
                                      known_at=row["known_at"], revision=row["revision"]) for row in rows]
