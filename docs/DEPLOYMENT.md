# Deployment and operations

Compose runs Timescale/PostgreSQL, authenticated Redis, a one-shot migration
service, FastAPI, a durable ingestion worker, and Nginx serving the built React
application. The live feed is an explicit `live` profile. No database or Redis
ports are published. The UI binds to loopback at port 8080.

## Configuration

| Variable | Purpose |
|---|---|
| POSTGRES_PASSWORD / DATABASE_URL | DB bootstrap and async SQLAlchemy connection; URL-encode special characters |
| REDIS_PASSWORD / REDIS_URL | Redis server password and client URL; keep them consistent |
| ADMIN_API_KEY | Random operator key, at least 32 characters; protected routes fail closed when absent |
| TOKEN_ENCRYPTION_KEY | Fernet key for encrypted broker token storage; back up securely |
| UPSTOX_CLIENT_ID / UPSTOX_CLIENT_SECRET | Server-side OAuth application credentials |
| UPSTOX_REDIRECT_URI | Registered callback; HTTPS for remote deployment |
| UPSTOX_ACCESS_TOKEN | Optional manual backend token; overrides stored token |
| WEB_ORIGIN | Exact UI origin for CORS and OAuth completion redirect |
| FEED_INSTRUMENT_IDS | JSON array of synchronized canonical IDs |
| HTTP_TIMEOUT_SECONDS / HTTP_RETRIES | REST timeout and bounded retry control |
| HISTORY_CHUNK_DAYS | 1–28 days per history request |
| RECONCILE_SECONDS | Minimum 30s, default 60s |
| MAX_SUBSCRIPTIONS | Conservative deployment cap, default 100 |
| VOLUME_BASELINE_PERIOD / ABNORMAL_VOLUME_MULTIPLE | Prior-volume median window and anomaly threshold |

Do not put secrets in VITE variables. Use external secret management for an
internet-facing deployment. .env is ignored. No real credentials are included.

OAuth state is random, Redis-backed, expires in ten minutes, is single-use and
bound to an HttpOnly browser cookie. The token exchange occurs server-side; only
encrypted tokens enter PostgreSQL. Access logs are disabled so callback codes
and token-bearing WebSocket URLs are not logged. Broker expiry requires operator
reauthorization; there is no invented refresh-token flow.

This is a single-operator foundation, not a multi-tenant authenticated product.
Before public exposure add identity/roles, rate limiting, TLS termination, backups,
secret rotation, monitoring, resource limits and deployment-specific hardening.
The frontend/API images run as non-root. Broker errors are sanitized; no order
API is included. The API key belongs to this application, not to Upstox.

## Health and recovery

Run the read-only deployment smoke check from the project directory after
starting Compose:

```sh
docker compose up --build -d
python scripts/check_deployment.py --output deployment-check.json
```

The script reads ADMIN_API_KEY from the environment or .env without printing it.
It checks the served frontend, API liveness, database/Redis readiness, denied
unauthenticated access, authenticated status and worker heartbeat. It exits 1
when any check fails and never overwrites an existing report. A remote base URL
requires HTTPS; redirects are not followed. Passing this check does not validate
Timescale activation, broker access, exchange calendars or market-data continuity.

For Timescale, inspect the extension and candle hypertable inside PostgreSQL:

```sh
docker compose exec postgres psql -U stock -d stock -c "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"
docker compose exec postgres psql -U stock -d stock -c "SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_name='candles';"
```

Then complete the README sequence: connect Upstox, synchronize instruments,
import verified sessions, ingest a bounded historical range, inspect job and
quality outcomes, and compare the selected live stream against reconciled history.
Record actual observations before claiming live acceptance.

* `/api/health/live`: process liveness without dependencies.
* `/api/health/ready`: DB migration head and Redis connectivity; 503 when unready.
* `/api/market/status`: session/calendar status, worker heartbeat, feed state,
  last received update, latest complete candle, counts; operator key required.
* `/api/jobs` and `/api/data-quality`: bounded latest outcomes and issues.

Jobs persist to PostgreSQL before Redis notifications. Workers poll the durable
queue if notifications are lost. `FOR UPDATE SKIP LOCKED` claims jobs; 30s lease
heartbeats protect active work; abandoned jobs retry up to three claims. Priority
1/2/3 are supported; universe assignment is introduced with scanners. Failed jobs
retain error codes; requeue explicitly after resolving the cause.

`docker compose down` preserves named volumes; do not use `down -v` on valuable
history. Back up database and encryption key together. Migrations are forward
versioned. Timescale migration only activates where the extension is available;
regular PostgreSQL follows the same candle schema. The extension is deliberately
not removed on downgrade.

## Performance limits

No full-market scans or tick-history persistence. Active feed state is O(selected
instruments). History writes are transactional and currently per-candle, favoring
correctness over bulk speed. Reconciliation fetches today's series and idempotently
checks records; it is intended for small selected universes at this stage. Before
NIFTY500/F&O scale: benchmark and add batch upserts, rolling reconciliation windows,
central rate limits, retention policies, approximate/cached status counts and
backpressure metrics. The status endpoint currently uses exact DB counts.


## Multi-provider phase, 2026-09-27

Run Alembic upgrade head before new workers. Readiness resolves actual Alembic heads dynamically. Local PostgreSQL needs no TimescaleDB. For this Windows workspace scripts/migrate_local_safe.py backs up local data and checks identity preservation; scripts/test_disposable_database.py creates/removes only a fresh test database. Provider configuration is documented in .env.example. Keep one live connection until broker entitlement is verified; MAX_FEED_CONNECTIONS and FEED_PRIORITIES allow explicit pooling. Credentialed acceptance is pending.
