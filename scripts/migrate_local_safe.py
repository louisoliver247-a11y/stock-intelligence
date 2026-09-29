"""Back up local PostgreSQL, migrate, and verify legacy identity preservation."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


async def fingerprint(conn):
    rows = await conn.fetch('SELECT instrument_id,provider_key FROM instruments ORDER BY instrument_id')
    digest = hashlib.sha256(json.dumps([list(row) for row in rows]).encode()).hexdigest()
    return {'instruments': len(rows), 'identity_digest': digest,
            'candles': await conn.fetchval('SELECT count(*) FROM candles'),
            'candle_revisions': await conn.fetchval('SELECT count(*) FROM candle_revisions')}


async def main():
    values = dotenv_values(ROOT / '.env.local')
    url = values['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    parsed = urlsplit(url)
    if parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('LOCAL_DATABASE_REQUIRED')
    conn = await asyncpg.connect(url)
    before = await fingerprint(conn)
    directory = ROOT / '.local' / 'backups'
    directory.mkdir(exist_ok=True)
    backup = directory / ('before-multiprovider-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8] + '.dump')
    env = {**os.environ, 'PGPASSWORD': unquote(parsed.password or '')}
    pg_dump = ROOT.parent / '.tools/postgres/pgsql/bin/pg_dump.exe'
    result = subprocess.run([str(pg_dump), '-h', parsed.hostname, '-p', str(parsed.port or 5432),
        '-U', unquote(parsed.username or ''), '-d', parsed.path.lstrip('/'), '-Fc', '-f', str(backup)], env=env)
    if result.returncode or not backup.exists() or backup.stat().st_size == 0:
        await conn.close()
        raise RuntimeError('BACKUP_FAILED_MIGRATION_NOT_STARTED')
    env = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env)
    if result.returncode:
        await conn.close()
        raise RuntimeError('MIGRATION_FAILED_BACKUP_RETAINED')
    after = await fingerprint(conn)
    assert before == after, 'LEGACY_IDENTITY_OR_CANDLE_COUNT_CHANGED'
    missing = await conn.fetchval("""SELECT count(*) FROM instruments i WHERE provider_key IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM instrument_provider_mappings m WHERE m.instrument_id=i.instrument_id
        AND m.provider='upstox' AND m.provider_instrument_id=i.provider_key)""")
    assert missing == 0, 'LEGACY_MAPPING_MISSING'
    report = {'before': before, 'after': after, 'missing_upstox_mappings': missing,
              'backup': str(backup.relative_to(ROOT)),
              'revision': await conn.fetchval('SELECT version_num FROM alembic_version'),
              'stored_broker_connections': await conn.fetchval('SELECT count(*) FROM broker_connections')}
    (ROOT / 'docs/MULTIPROVIDER_MIGRATION_RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
