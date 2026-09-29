# Milestone report — 0 and 1

Scope stopped at the market-data foundation. No indicators, scanners, trading
signals, AI predictions, paper trades or broker execution were added.

## Milestone 0

### COMPLETED

* Inspected the workspace: fresh, no existing application files.
* Created architecture, implementation plan, database/environment documentation.
* Built FastAPI settings, structured logging, liveness/readiness and operator-key
  protection; React/TypeScript/Vite/Tailwind skeleton with a Lightweight Charts
  history view, responsive layout and light/dark controls.
* Added PostgreSQL/optional Timescale migrations, Redis/worker topology, Docker
  Compose, non-root app images and Nginx routing.
* Created dependency locks and environment example with no real credentials.

### FILES CREATED

`README.md`, `pyproject.toml`, `requirements*.lock`, `.env.example`, `.gitignore`,
`.dockerignore`, `alembic.ini`, `compose.yaml`, `api/`, `config/`, `docker/`,
`frontend/`, `migrations/`, `docs/`, and baseline `tests/`.
See [complete file inventory](FILE_INVENTORY.md).

### FILES MODIFIED

No pre-existing project files were modified. All application files were newly
created and refined during this implementation. Workspace-root `.gitignore`
excludes the isolated test-tool downloads in `.tools/`.

### DATABASE CHANGES

Migration `0001` creates ten foundation tables: users, broker_connections,
instruments, instrument_metadata, exchange_sessions, candles, candle_revisions,
data_quality_issues, system_jobs and audit_logs, with constraints and indexes.
`0002` conditionally enables the Timescale candle hypertable. PostgreSQL without
Timescale follows the ordinary-table path. Alembic owns its version table.

### API ENDPOINTS

`GET /api/health/live`, `GET /api/health/ready`, `GET /api/market/status`.
Readiness returns 503 when DB migration head or Redis is unavailable. Market
status explicitly reports unknown/unverified data rather than synthetic values.

### TESTS RUN / TEST RESULTS

Frontend build and UI test passed. Python liveness/security tests passed within
the 37-test backend suite. Migration upgrade, downgrade-to-base, and re-upgrade
passed against a disposable PostgreSQL 16.8 instance; revision is `0002`.
Compose YAML structural checks passed. Exact commands and results are below.

### KNOWN ISSUES

Docker is not installed in this environment, so container builds, image pulls,
Nginx behavior, Timescale activation and a real Redis runtime remain unverified.
No visual browser automation was run; frontend validation is build plus DOM test.
One upstream FastAPI/Starlette TestClient deprecation warning remains.

### SECURITY CONCERNS

Single-operator API-key authentication is suitable for this local foundation;
multi-user identity/authorization and internet-facing TLS/rate limits are not
implemented. Supply random infrastructure passwords and a Fernet encryption key.
The default example values are not production credentials. Broker credentials
are backend-only; OAuth state is expiring, single-use and browser-bound.

### PERFORMANCE CONCERNS

Exact dashboard counts and per-row persistence need benchmarking and optimization
before large-universe deployment. No high-frequency history or full-market scan
has been enabled.

### NEXT MILESTONE

Milestone 1 code was implemented in this same authorized task, as reported below.
Container runtime acceptance remains open.

## Milestone 1

### COMPLETED

* Added a broker-neutral MarketDataProvider protocol and immutable canonical
  instrument, candle, quote, depth and tick models.
* Implemented server-side Upstox OAuth, encrypted token storage, instrument
  synchronization, quote/LTP retrieval, historical/intraday V3 ingestion and
  provider normalization.
* Vendored the official V3 protobuf schema and generated decoder; added binary
  subscription messages, authorization, bounded reconnect/backoff, resubscription,
  unsubscription and token reload on reconnect.
* Added durable priority jobs with recoverable claims/heartbeats, bounded history
  requests, transactional idempotent candles and append-only correction history.
* Added explicit IST session calendars and checks for invalid/misaligned/duplicate/
  conflicting/missing candles, abnormal volume, unknown sessions, out-of-order or
  future ticks, and WebSocket disconnects. Corrupted slots are not filled.
* Added session-aware minute-to-intraday aggregation and provisional second/minute
  tick aggregation. Sampled live candles remain incomplete until REST reconciliation.
* Connected operational UI controls to actual API jobs/history; all empty market
  states are explicit. Completed candles only are displayed on the history chart.

### FILES CREATED

`market_data/providers/*`, `market_data/upstox/*`, `market_data/historical/*`,
`market_data/websocket/*`, `market_data/{calendar,aggregation,repository,db,jobs,worker}.py`,
market-data/API integration tests and validation scripts. Complete inventory:
[FILE_INVENTORY.md](FILE_INVENTORY.md).

### FILES MODIFIED

Expanded the newly created API, settings, frontend, migrations and documentation.
No pre-existing user application content was overwritten.

### DATABASE CHANGES

Populated a disposable database only for tests; integration test records were
cleaned up. Candle corrections preserve original values and known-at timestamps.
No real broker tokens or user portfolio data were written. PostgreSQL was stopped
after validation; the isolated runtime remains under ignored `.tools/`.

### API ENDPOINTS

| Method | Path | Purpose |
|---|---|---|
| POST | /api/auth/upstox/start | Start protected OAuth flow |
| GET | /api/auth/upstox/callback | Browser-bound OAuth completion |
| GET | /api/instruments | Search synchronized instruments |
| POST | /api/instruments/sync | Queue public instrument-master sync |
| POST | /api/calendar/sessions | Import verified exchange sessions/holidays |
| POST | /api/history/ingest | Queue canonical minute/daily ingestion |
| GET | /api/candles | Read stored candles with completion/quality fields |
| GET | /api/candles/aggregate | Derive session-aligned intraday intervals |
| GET | /api/jobs | Recent durable jobs |
| GET | /api/jobs/{job_id} | Job details/outcome |
| GET | /api/data-quality | Latest recorded quality issues |
| GET | /api/events | SSE operational status updates |

### TESTS RUN / TEST RESULTS

37 backend tests passed with zero skips when run against PostgreSQL; this includes
end-to-end mocked-provider ingestion of a full 375-minute synthetic session,
revision/idempotency tests, job recovery/priority, real encrypted-token persistence,
prefix-invariance/no-look-ahead checks and simulated binary-feed reconnection.
Public instrument-master smoke check normalized **9,885 records with 9,885 unique
IDs**, covering `NSE_EQ` and `NSE_INDEX`. No broker token was required for that check.

### KNOWN ISSUES

* Authenticated live Upstox OAuth/history/quote/WebSocket acceptance has not run:
  no real account credentials were supplied. Public master success does not
  certify those paths or live continuity.
* Actual Redis and Timescale behavior is untested here; Redis interactions are
  mocked in integration tests. Docker runtime remains untested.
* Exchange calendars require explicitly verified imports. Corporate-action
  adjustment, automatic calendar updates, instrument retirement/F&O rollover
  identity, and broad index-universe membership are not implemented.
* Live reconciliation covers today's session. Queue historical backfills for
  earlier outage dates. No as-of revision query endpoint exists yet.
* Weekly through yearly aggregation is reserved in the enum but not implemented;
  this milestone delivers basic second/minute and higher-intraday aggregation.
* Abnormal-volume screening uses a prior median, not intraday seasonality; initial
  observations without sufficient baseline cannot be screened.
* The integrity gate intentionally remains NOT_VERIFIED. M1 live-data acceptance
  is pending; this foundation is not represented as production-certified.

### SECURITY CONCERNS

No order-placement API exists. Broker tokens are encrypted at rest and never
returned to the UI. Access logs are disabled to avoid logging OAuth query codes.
Production still requires secret management/rotation, TLS, operator authorization
hardening and backup testing. The temporary local database used synthetic data
only and is not part of the application's deployment configuration.

### PERFORMANCE CONCERNS

History synchronization and reconciliation use per-candle transactions/locks
inside bounded batches. Current-day reconciliation rechecks the full returned
series; optimize and centrally rate-limit before broad-universe use. Feed state
is bounded by the explicit subscription cap and expires from Redis. No unlimited
tick or second-candle persistence is enabled.

### NEXT MILESTONE

Stop here. Finish Docker/Redis/Timescale and authenticated live-data acceptance,
load a verified exchange calendar, and compare historical/live candles before
starting Milestone 2 (indicator engine). No trading signals should be enabled.

## Validation commands and observed results

Commands were run from `stock-intelligence/` unless otherwise shown. This Windows
environment needed a workspace-isolated Python because its system Python alias
was unusable; replace that executable path with your virtual environment's Python.

```powershell
$env:DATABASE_URL='postgresql+asyncpg://stock@127.0.0.1:55432/stock_test'
$env:TEST_DATABASE_URL=$env:DATABASE_URL
& ..\.tools\python\python.exe -m alembic upgrade head
& ..\.tools\python\python.exe -m alembic downgrade base
& ..\.tools\python\python.exe -m alembic upgrade head
# All exited 0; SELECT version_num FROM alembic_version returned 0002.

& ..\.tools\python\python.exe -m pytest -q
# 37 passed, 1 upstream TestClient deprecation warning; zero skips.

& ..\.tools\python\python.exe -m ruff check .
# All checks passed!

& ..\.tools\python\python.exe -m alembic upgrade head --sql
# Exited 0; generated migrations/foundation.sql.

& ..\.tools\python\python.exe scripts/validate_compose.py
# YAML structure passed: 7 services; private DB/Redis; migration dependencies.
# This is not a Docker runtime test.

& ..\.tools\python\python.exe scripts/check_public_master.py
# normalized_instruments=9885, unique_ids=9885, segments=NSE_EQ/NSE_INDEX.

cd frontend
npm.cmd run build
# TypeScript and Vite passed: 37 modules; JS 402.53 kB, gzip 127.33 kB.
npm.cmd test
# 1 test file passed, 1 UI test passed.
```

Frontend esbuild initially hit a sandbox parent-directory permission error; the
same build/test commands passed with approved broader execution. PostgreSQL's
pg_ctl launcher hit a Windows restricted-token error; running the temporary
postgres binary directly allowed migrations and database tests to pass. These
tooling workarounds did not alter production application behavior.

## Milestone 2 - offline indicator continuation

Implemented the authorized offline indicator engine, immutable configuration,
observation/snapshot metadata, point-in-time candle revision queries and JSON CLI.
Indicators include EMA, RSI, MACD, ATR, ADX, session HLC3 VWAP and relative volume.
No live analysis routes, automated signals or database migrations were added.
See ANALYSIS_ENGINE.md for seed, warm-up, replay and command-line conventions.

Validation on 2026-09-25: 68 backend tests passed with zero skips against the
existing disposable PostgreSQL database; Ruff passed. Coverage includes an
independent NumPy oracle, prefix invariance, incremental/batch equivalence,
idempotency, rejected-input state preservation and correction-cutoff selection.
One upstream Starlette TestClient deprecation warning remains. The temporary
database was stopped after validation. Frontend DOM test passed; build result
is recorded below. Sandbox esbuild parent-directory access required an approved
rerun outside the sandbox.

M1 authenticated provider/calendar integrity and Docker/Redis/Timescale runtime
acceptance remain open. Offline calculations do not certify live market data.
Earlier M0/M1 scope statements above describe the original delivery, superseded
by this explicitly authorized offline continuation.

Frontend production build passed (TypeScript and Vite, 37 modules).

## Deployment acceptance preparation - 2026-09-25

Added scripts/check_deployment.py for read-only frontend, liveness, readiness,
access-control and worker-heartbeat checks, with sanitized JSON reports and
nonzero exit status on failure. Added seven tests covering unavailable services,
malformed responses, redirects, failed authentication and missing workers.
Tests now ignore the local .env file so operator configuration cannot influence
unit-test defaults. Validation: 71 passed, 4 database-dependent tests skipped
(database was stopped), Ruff passed; Compose structural validation passed.

Initial local probe is recorded in DEPLOYMENT_CHECK.json. It ran before .env was
created and found no running deployment; it is failure evidence, not acceptance.
Created an ignored .env with generated infrastructure credentials and encryption
key, leaving broker fields empty. No credentials were printed or committed.
Docker was unavailable both on PATH and at the standard Docker Desktop location.
No containers, Timescale or real Redis were tested. DEPLOYMENT.md now provides
the runtime check and separate Timescale verification commands. Docker runtime,
authenticated provider access and verified calendar/data comparisons are still
required to complete acceptance.

## Windows-local deployment - 2026-09-25

The user authorized completing local setup while leaving Upstox connection for
later. The app is now served at http://localhost:8080 with the built frontend,
FastAPI, ingestion worker, password-protected PostgreSQL 16 and Redis 7.4.11.
All listeners bind to 127.0.0.1. This uses the supported plain PostgreSQL schema;
it does not claim Docker or Timescale runtime acceptance.

Added start/stop/key-copy shortcuts, isolated `.env.local`, persistent local
database/cache storage, hidden process launch, process identity checks and
native database/cache shutdown. Tested clean stop/restart and repeated start.
Instrument data survived restart: the public master job imported 9,885 entries.
Imported 30 September 2026 NSE calendar dates with official holiday and normal
hours references; dates outside that month remain unconfigured.

Validation: 76 backend tests passed with zero skips using a separate disposable
database; Ruff passed; frontend test and TypeScript/Vite production build passed.
The existing upstream TestClient deprecation warning remains. All five local
deployment smoke checks passed; see LOCAL_DEPLOYMENT_CHECK.json and LOCAL_SERVER.md.
No broker credentials, historical candles or authenticated live feed were added.
