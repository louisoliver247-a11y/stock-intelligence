import json
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class JobQueue:
    def __init__(self, engine: AsyncEngine, redis: Redis):
        self.engine, self.redis = engine, redis

    async def enqueue(self, kind: str, payload: dict, priority: int = 2, idempotency_key: str | None = None) -> str:
        job_id = str(uuid4())
        async with self.engine.begin() as conn:
            row = (await conn.execute(
                text("""INSERT INTO system_jobs(id,kind,payload,priority,idempotency_key)
                VALUES (:id,:kind,CAST(:payload AS jsonb),:priority,:key)
                ON CONFLICT(idempotency_key) WHERE state IN ('QUEUED','RUNNING')
                AND idempotency_key IS NOT NULL DO UPDATE SET idempotency_key=excluded.idempotency_key
                RETURNING id"""),
                {"id": job_id, "kind": kind, "payload": json.dumps(payload), "priority": priority,
                 "key": idempotency_key},
            )).scalar_one()
            job_id = str(row)
        try:
            await self.redis.lpush(f"jobs:{priority}", job_id)
            await self.redis.ltrim(f"jobs:{priority}", 0, 9999)
        except Exception:
            # Durable DB job remains discoverable by the worker's periodic claim.
            pass
        return job_id

    async def claim(self):
        async with self.engine.begin() as conn:
            await conn.execute(
                text("""UPDATE system_jobs SET state='QUEUED'
                WHERE state='RUNNING' AND started_at < now()-interval '5 minutes' AND attempts<3""")
            )
            await conn.execute(
                text("""UPDATE system_jobs SET state='FAILED',error_code='LEASE_EXHAUSTED',
                finished_at=now() WHERE state='RUNNING' AND started_at < now()-interval '5 minutes' AND attempts>=3""")
            )
            job = (
                (
                    await conn.execute(
                        text("""SELECT * FROM system_jobs WHERE state='QUEUED'
                ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
                    )
                )
                .mappings()
                .one_or_none()
            )
            if not job:
                return None
            token = str(uuid4())
            await conn.execute(
                text("""UPDATE system_jobs SET state='RUNNING',attempts=attempts+1,
                started_at=now(),lease_token=:token WHERE id=:id"""),
                {"id": job["id"], "token": token},
            )
            return {**dict(job), "lease_token": token}

    async def heartbeat(self, job_id, lease_token):
        async with self.engine.begin() as conn:
            await conn.execute(
                text("UPDATE system_jobs SET started_at=now() WHERE id=:id AND state='RUNNING' AND lease_token=:lease_token"),
                {"id": job_id, "lease_token": lease_token},
            )

    async def finish(self, job_id, result: dict | None = None, error: str | None = None, *, lease_token):
        async with self.engine.begin() as conn:
            updated = await conn.execute(
                text("""UPDATE system_jobs SET state=:state,result=CAST(:result AS jsonb),
                error_code=:error,finished_at=now() WHERE id=:id AND lease_token=:lease_token AND state='RUNNING'"""),
                {
                    "id": job_id,
                    "state": "FAILED" if error else "SUCCEEDED",
                    "lease_token": lease_token,
                    "result": json.dumps(result),
                    "error": error,
                },
            )
            if updated.rowcount != 1:
                return False
            await conn.execute(
                text("""INSERT INTO audit_logs(event,entity_id,details)
                VALUES ('job_finished',:id,CAST(:details AS jsonb))"""),
                {"id": str(job_id), "details": json.dumps({"error_code": error, "result": result})},
            )

        return True
