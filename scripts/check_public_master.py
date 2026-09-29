"""Opt-in read-only check of the public Upstox instrument master; no token needed."""

import asyncio

import httpx

from market_data.calendar import SessionCalendar
from market_data.upstox.http import UpstoxHTTP
from market_data.upstox.provider import UpstoxProvider


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        rows = await UpstoxProvider(UpstoxHTTP(client, ""), SessionCalendar([])).get_instruments()
        print(
            {
                "normalized_instruments": len(rows),
                "unique_ids": len({i.instrument_id for i in rows}),
                "segments": sorted({i.segment for i in rows}),
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
