"""Run integration tests only on a newly created database, never the application database."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


async def main():
    values = dotenv_values(ROOT / '.env.local')
    base = values['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    admin_url = base.rsplit('/', 1)[0] + '/postgres'
    name = 'test_multiprovider_' + uuid4().hex
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
        url = base.rsplit('/', 1)[0] + '/' + name
        env = {**os.environ, 'DATABASE_URL': url.replace('postgresql://', 'postgresql+asyncpg://'),
               'TEST_DATABASE_URL': url.replace('postgresql://', 'postgresql+asyncpg://')}
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0002'], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
        test_conn = await asyncpg.connect(url)
        try:
            await test_conn.execute("""INSERT INTO instruments
                (instrument_id,symbol,exchange,segment,name,instrument_type,provider_key)
                VALUES ('migration-fixture','LEGACY','NSE','NSE_EQ','Legacy fixture','EQ','NSE_EQ|LEGACY')""")
            await test_conn.execute("""INSERT INTO candles
                (instrument_id,timeframe,timestamp,symbol,exchange,open,high,low,close,volume,is_complete,source,known_at)
                VALUES ('migration-fixture','1m','2025-01-02 03:45:00+00','LEGACY','NSE',100,100,100,100,
                        10,false,'upstox_feed','2025-01-03 00:00:00+00')""")
        finally:
            await test_conn.close()
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
        test_conn = await asyncpg.connect(url)
        try:
            assert await test_conn.fetchval("SELECT provider_instrument_id FROM instrument_provider_mappings "
                                            "WHERE instrument_id='migration-fixture'") == 'NSE_EQ|LEGACY'
            assert await test_conn.fetchval("SELECT provider FROM provider_candles "
                                            "WHERE instrument_id='migration-fixture'") == 'upstox'
            assert await test_conn.fetchval("SELECT known_at='2025-01-03 00:00:00+00'::timestamptz FROM candles "
                                            "WHERE instrument_id='migration-fixture'")
            assert await test_conn.fetchval("SELECT reconciled FROM candles "
                                            "WHERE instrument_id='migration-fixture'") is False
        finally:
            await test_conn.close()
        for action, revision in [('downgrade', '0002'), ('upgrade', 'head')]:
            result = subprocess.run([sys.executable, '-m', 'alembic', action, revision], cwd=ROOT, env=env)
            if result.returncode:
                return result.returncode
        test_conn = await asyncpg.connect(url)
        try:
            for table in ('provider_candles', 'instrument_provider_mappings', 'candles', 'instruments'):
                await test_conn.execute(f"DELETE FROM {table} WHERE instrument_id='migration-fixture'")
        finally:
            await test_conn.close()
        print('Legacy migration backfill, preserved known_at, downgrade and re-upgrade: passed', flush=True)
        return subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT, env=env).returncode
    finally:
        # Only the freshly generated name is eligible for cleanup.
        await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await conn.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
