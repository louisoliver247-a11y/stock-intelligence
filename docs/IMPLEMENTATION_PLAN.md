# Implementation sequence

1. Document architecture, scope, database and environment requirements.
2. Milestone 0: settings, logging, migration foundation, Docker services, API
   liveness/readiness, frontend status shell, baseline tests.
3. Milestone 1: canonical models, explicit sessions, provider protocol, Upstox
   OAuth/REST/V3, instrument sync, chunked history, transactional revisions,
   quality checks, aggregation, queued work and reconnect reconciliation.
4. Add synthetic and mocked provider tests; validate Python, frontend types,
   production build, migrations and infrastructure where local tooling permits.
5. Report exact validation evidence and outstanding real-provider checks. Stop.

## Database foundation

Initial migration owns users, broker_connections, instruments,
instrument_metadata, exchange_sessions, candles, candle_revisions,
data_quality_issues, system_jobs and audit_logs. Composite candle primary key:
(instrument_id, timeframe, timestamp). Indexes support instrument/time queries,
job claims and unresolved quality issues. Later domain tables are documented in
DATA_MODEL.md and introduced by their owning milestone, not empty placeholders.

## Environment requirements

Required: DATABASE_URL, POSTGRES_PASSWORD, REDIS_PASSWORD, REDIS_URL, ADMIN_API_KEY
(32+ characters), TOKEN_ENCRYPTION_KEY (Fernet). OAuth additionally requires
UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI. Optional manual
UPSTOX_ACCESS_TOKEN is backend-only. WEB_ORIGIN controls CORS. FEED_INSTRUMENT_IDS
selects an explicit synchronized universe. No broker or infrastructure secrets
may use VITE_ prefixes. See .env.example for defaults and tuning settings.

## Acceptance boundary

Mocked tests can establish deterministic behavior, but cannot certify exchange
calendar correctness, broker entitlements, actual packet continuity or Docker
deployment. Live integrity remains unverified until credentials, approved session
calendar and actual historical/live comparisons are supplied and exercised.

## Authorized continuation: Milestone 2

The user requested continuation after the M0/M1 report. Build the deterministic
indicator library and validate it offline; live market-data acceptance remains
open and no automatic analysis jobs or signals are enabled.

1. Define immutable indicator configuration, explicit seed/warm-up conventions,
   output availability metadata and a broker-neutral candle observation envelope.
2. Implement bounded incremental EMA, RSI, MACD, ATR, ADX, session OHLCV VWAP and
   prior-window relative volume. Batch processing calls the same update methods.
3. Reject partial, flagged, future, mixed-stream, out-of-order, corrected and
   gapped inputs before changing state. Corrections require ordered replay.
4. Add a point-in-time candle repository query so corrected history cannot leak
   into an earlier analysis. Do not expose analysis through live API routes yet.
5. Add a local JSON analysis command and test exact synthetic outcomes, independent
   NumPy reference calculations, prefix invariance and database correction timing.
6. Run regression checks and report M2 results and the outstanding M1 live gate.
