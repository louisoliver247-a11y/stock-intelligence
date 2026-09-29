"""Prepare isolated, persistent Windows-local configuration without printing secrets."""

import argparse
import asyncio
import os
import secrets
import subprocess
from pathlib import Path

import asyncpg
import redis
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / ".tools"
DATA = TOOLS / "local-pgdata"
RUNTIME = ROOT / ".local"


def prepare():
    RUNTIME.mkdir(exist_ok=True)
    local_env = ROOT / ".env.local"
    if not local_env.exists():
        values = dict(dotenv_values(ROOT / ".env"))
        password = secrets.token_hex(24)
        values.update(
            LOCAL_POSTGRES_PASSWORD=password,
            DATABASE_URL=f"postgresql+asyncpg://stock_local:{password}@127.0.0.1:55433/stock_local",
            REDIS_URL=f"redis://:{values['REDIS_PASSWORD']}@127.0.0.1:56379/0",
            WEB_ORIGIN="http://localhost:8080",
            UPSTOX_REDIRECT_URI="http://localhost:8080/api/auth/upstox/callback",
        )
        with local_env.open("x", encoding="utf-8") as target:
            for key, value in values.items():
                if value is not None:
                    target.write(f"{key}={value}\n")
    values = dotenv_values(local_env)
    if not (DATA / "PG_VERSION").exists():
        password_file = RUNTIME / "init-password"
        password_file.write_text(values["LOCAL_POSTGRES_PASSWORD"], encoding="utf-8")
        try:
            subprocess.run([
                str(TOOLS / "postgres/pgsql/bin/initdb.exe"), "-D", str(DATA),
                "-U", "stock_local", "--pwfile", str(password_file),
                "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C",
            ], check=True)
        finally:
            password_file.unlink(missing_ok=True)
    redis_data = RUNTIME / "redis-data"
    redis_data.mkdir(exist_ok=True)
    (RUNTIME / "redis.conf").write_text(
        "bind 127.0.0.1\nport 56379\nprotected-mode yes\n"
        f"requirepass {values['REDIS_PASSWORD']}\n"
        "appendonly yes\nappendfsync everysec\n"
        "dir ./redis-data\n", encoding="utf-8",
    )
    print("Local configuration prepared; secrets retained in .env.local.")


async def database():
    values = dotenv_values(ROOT / ".env.local")
    conn = await asyncpg.connect(
        host="127.0.0.1", port=55433, user="stock_local",
        password=values["LOCAL_POSTGRES_PASSWORD"], database="postgres",
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname='stock_local'"):
            await conn.execute("CREATE DATABASE stock_local")
    finally:
        await conn.close()
    os.environ.update({k: v for k, v in values.items() if v is not None})
    subprocess.run([str(TOOLS / "python/python.exe"), "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "database", "stop-redis"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "database":
        asyncio.run(database())
    else:
        values = dotenv_values(ROOT / ".env.local")
        redis.Redis.from_url(values["REDIS_URL"]).shutdown(save=True)
