from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import text


class UniverseCode(StrEnum):
    NIFTY50 = 'NIFTY50'
    NIFTY100 = 'NIFTY100'
    NIFTY200 = 'NIFTY200'
    NIFTY500 = 'NIFTY500'
    NSE_FNO = 'NSE_FNO'
    CUSTOM = 'CUSTOM'
    WATCHLIST = 'WATCHLIST'


class UniverseService:
    """Explicit, sourced membership only. Instrument-master size is never index membership."""

    def __init__(self, engine):
        self.engine = engine

    async def add_members(self, code: UniverseCode, instrument_ids: list[str], valid_from: date,
                          source: str, valid_to: date | None = None):
        if not source.strip() or valid_to and valid_to < valid_from:
            raise ValueError('VALID_MEMBERSHIP_SOURCE_AND_DATES_REQUIRED')
        async with self.engine.begin() as conn:
            await conn.execute(text('INSERT INTO instrument_universes(code,authoritative_source) '
                                    'VALUES (:code,:source) ON CONFLICT(code) DO NOTHING'),
                               {'code': code.value, 'source': source})
            for instrument_id in dict.fromkeys(instrument_ids):
                await conn.execute(text('''INSERT INTO universe_memberships
                    (universe,instrument_id,valid_from,valid_to,source)
                    VALUES (:code,:id,:start,:end,:source)
                    ON CONFLICT(universe,instrument_id,valid_from) DO NOTHING'''),
                    {'code': code.value, 'id': instrument_id, 'start': valid_from,
                     'end': valid_to, 'source': source})

    async def members(self, code: UniverseCode, on_date: date, known_as_of: datetime) -> list[str]:
        if known_as_of.tzinfo is None:
            raise ValueError('AWARE_KNOWN_AS_OF_REQUIRED')
        async with self.engine.connect() as conn:
            return list((await conn.execute(text('''SELECT instrument_id FROM universe_memberships
                WHERE universe=:code AND valid_from<=:day AND (valid_to IS NULL OR valid_to>=:day)
                AND known_at<=:as_of ORDER BY instrument_id'''),
                {'code': code.value, 'day': on_date, 'as_of': known_as_of})).scalars())
