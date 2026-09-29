# MULTI-PROVIDER PHASE REPORT

## PHASE STATUS

Implementation and local verification complete within confirmed provider contracts. Credentialed provider
acceptance remains NOT VERIFIED. HDFC SKY stays gated because usable official technical contracts/account
access were not established. This is not a claim of live brokerage connectivity.

Upstox and the offline indicator engine are preserved. No scanner, strategy, signals, structure, zones,
patterns, backtesting, AI/ML or order execution was implemented. Stop condition reached.

## BASELINE BEFORE CHANGES

2026-09-27: 72 backend tests passed, four database tests skipped without TEST_DATABASE_URL; Ruff passed;
one frontend test passed; frontend production build passed. Frontend sandbox directory access initially
failed; verification succeeded outside the sandbox. Existing Starlette TestClient deprecation warning remains.

Git already existed at baseline commit 3b8ed86. Existing .dockerignore and NumPy requirements.lock edits
were preserved. NumPy 2.5.3 was already pinned and matches the installed environment. pip check passes.
No unrelated packages were upgraded; no remote, push or new commit was created.

## FILES CREATED

- docs/DATA_PROVENANCE.md
- docs/HDFC_SKY.md
- docs/INSTRUMENT_IDENTITY.md
- docs/MULTIPROVIDER_MIGRATION_RESULT.json
- docs/MULTIPROVIDER_PHASE_REPORT.md
- docs/MULTI_PROVIDER_ARCHITECTURE.md
- docs/PROVIDER_CAPABILITIES.md
- docs/SHAREKHAN.md
- market_data/hdfc_sky/__init__.py
- market_data/hdfc_sky/provider.py
- market_data/migration_status.py
- market_data/providers/capabilities.py
- market_data/providers/factory.py
- market_data/providers/registry.py
- market_data/providers/status.py
- market_data/providers/subscriptions.py
- market_data/resilience.py
- market_data/sharekhan/__init__.py
- market_data/sharekhan/auth.py
- market_data/sharekhan/http.py
- market_data/sharekhan/normalize.py
- market_data/sharekhan/provider.py
- market_data/sharekhan/websocket.py
- market_data/universes.py
- migrations/versions/0003_multi_provider.py
- scripts/migrate_local_safe.py
- scripts/test_disposable_database.py
- tests/test_multi_provider.py
- tests/test_multi_provider_integration.py

## FILES MODIFIED

- .dockerignore
- .env.example
- .gitignore
- analysis/indicators/validation.py
- api/main.py
- config/settings.py
- docs/ARCHITECTURE.md
- docs/CHANGELOG.md
- docs/DATA_MODEL.md
- docs/DEPLOYMENT.md
- docs/MARKET_DATA.md
- docs/MULTIPROVIDER_BASELINE.md
- frontend/src/App.test.tsx
- frontend/src/App.tsx
- frontend/src/api.ts
- market_data/aggregation.py
- market_data/jobs.py
- market_data/providers/base.py
- market_data/providers/models.py
- market_data/repository.py
- market_data/upstox/normalize.py
- market_data/upstox/provider.py
- market_data/websocket/aggregation.py
- market_data/websocket/worker.py
- market_data/worker.py
- requirements.lock
- tests/conftest.py
- tests/indicators/test_engine.py
- tests/test_jobs_integration.py
- tests/test_repository_integration.py

The .dockerignore and requirements.lock modifications predated this turn and were retained.

## MIGRATIONS CREATED

0003_multi_provider.py, revision 0003, parent 0002. Disposable tests exercised legacy backfill,
known_at preservation, downgrade to 0002 and re-upgrade. Downgrade refuses non-Upstox provider data to
avoid silently deleting it; use a tested backup/restore plan after multi-provider ingestion begins.

## DATABASE CHANGES

Added instrument_provider_mappings, provider_candles, instrument_universes and universe_memberships.
Added nullable derivative identity fields; canonical provider/reconciliation/adjustment metadata;
job lease tokens and active-job idempotency index; quality-resolution metadata.

The local application database was backed up in .local/backups before migration to 0003. All 9,885
instrument IDs and legacy keys were preserved, verified by identical SHA-256 identity fingerprints.
There are zero missing Upstox mappings. Before/after candle and revision counts are both zero.
See MULTIPROVIDER_MIGRATION_RESULT.json for the backup name and exact verification result.
Disposable databases created for testing were removed. TimescaleDB remains optional.
The PostgreSQL process started for these checks was stopped after verification; local services are back
to their prior stopped state. The Start Local App launcher can start them normally.

## PROVIDER ARCHITECTURE

Existing protocol extended; typed capabilities and registry/factory introduced. Authentication/transport
construction is centralized in adapters/factory. Generic workers consume normalized observations.
Provider status uses safe configuration/runtime information; credentials remain backend-only.
See MULTI_PROVIDER_ARCHITECTURE.md and PROVIDER_CAPABILITIES.md.

## UPSTOX STATUS

Existing REST, instrument master, history, WebSocket/protobuf and auth routes preserved and regression-tested.
Adapters explicitly tag provenance. Generic workers obtain Upstox through the registry and mapped identity.
No configured credentials or stored token; credentialed live behavior NOT VERIFIED in this phase.

## SHAREKHAN STATUS

IMPLEMENTED / TESTED WITH MOCKS from official documentation and official SDK evidence.
Backend browser-bound version-1005 authentication, GCM tag validation, encrypted token storage,
NC ScripMaster, 1-minute/daily historical normalization and JSON streaming are implemented.

## SHAREKHAN CAPABILITIES

Enabled adapter capabilities: NC instrument master, historical candles, WebSocket quotes/sampled ticks, live OI.
Unadjusted history is explicitly marked. No undocumented start/end query parameters are sent.
REST quote/LTP, current-day historical reconciliation and full depth remain disabled because the needed
contracts were not established. Optional top-of-book fields are normalized. Derivative schema is ready,
but Sharekhan exchange coverage is currently NC cash. Orders remain disabled and unimplemented.

## SHAREKHAN LIVE VERIFICATION STATUS

NOT VERIFIED. No SHAREKHAN credentials or encrypted connection token exist locally. No credentialed
history, quote, login or WebSocket request was made. Mock success is not presented as live verification.

## HDFC SKY STATUS

Explicit capability descriptor implemented; market-data transports and payload parsers intentionally absent.
Official public pages have uneven availability claims; no usable technical payload contract/account
entitlement was confirmed. No guessed endpoints or fictional fixtures were introduced.

## HDFC SKY CAPABILITIES

Authentication contract, instrument master, history, REST quotes, REST LTP, WebSocket contract, depth and
OI are classified NOT_DOCUMENTED in the inspected technical material. All operational flags are false.
This does not assert that the provider offers none of these to entitled customers. See HDFC_SKY.md.

## HDFC SKY LIVE VERIFICATION STATUS

NOT VERIFIED. No credentials/access. HDFC-origin offline-indicator tests establish mathematical provider
independence only, not HDFC API compatibility.

## INSTRUMENT MAPPING STATUS

9,885 existing Upstox instruments mapped without replacement. Exchange/ISIN/EQ matching is serialized
and ambiguity-safe. Symbol-only matching is prohibited. Unknown derivative identity is never guessed.
Master omissions do not delete old mappings. See INSTRUMENT_IDENTITY.md.

## CANDLE PROVENANCE DESIGN

Distinct provider revisions are append-only observations. Canonical candles retain their existing key and
point-in-time history. Complete/reconciled observations follow configured priority; lower-ranked values
remain discoverable without overwriting preferred data. Unknown origin is rejected for new persistence.
Quote receipt/knowledge times are recorded in expiring Redis values. See DATA_PROVENANCE.md.

## PROVIDER FALLBACK DESIGN

For jobs without an explicit provider, try default then ordered preferences, selecting only enabled
capabilities/mappings. Availability/authentication failures can fall back; malformed payloads cannot.
Explicit provider selection stays explicit. Canonical priority is PROVIDER_PREFERENCE; changing it does
not retrospectively rewrite history. Re-ingestion applies current preference while retaining revisions.

## WEBSOCKET STATUS

Upstox preserved; Sharekhan JSON transport added with TLS, bounded buffering, subscription limits,
unsubscription, reconnect/backoff and resubscription. Provider-aware subscription pools track priorities,
connections and requested/active instruments. Default one connection; extra entitlement is unverified.
HDFC transport unavailable. All live feed behavior in this phase is mock-tested, not live-verified.

## HISTORICAL DATA STATUS

Existing HistoricalIngestion reused. Sharekhan filters its documented returned history window locally;
minute gaps and conflicts use existing quality checks. No fabricated candles or corporate-action adjustment.
Upstox remains the available current-day reconciliation provider. The indicator engine accepts either
provider's validated candles and preserves look-ahead checks and provenance-sensitive audit digests.

## REDIS STATUS

Worker heartbeat/cache/blocking-pop failures log a sanitized degraded event, wait with controlled delay,
and retry. Redis clients have bounded connect/read timeouts. Durable PostgreSQL jobs remain recoverable.
Outage/recovery behavior is mock-tested. Redis was not started for the read-only local database smoke test.

## JOB SYSTEM STATUS

Claims generate unique lease tokens. Heartbeat and completion are fenced by token and RUNNING state;
stale completion cannot overwrite a reclaimed job or append a success audit entry. Reconciliation uses
an active PostgreSQL idempotency key, retained throughout slow jobs, replacing TTL-only suppression.
Concurrent enqueue/claim, reclaim, stale completion and post-completion re-enqueue are database-tested.

## DATA QUALITY STATUS

Existing issue recording retained. Unresolved listing, acknowledgement/resolution notes and audit events
added. Review actions never edit prices or clear candle flags. Raw failed/tick payload retention is disabled;
only normalized data, allowlisted instrument metadata and safe error categories are retained.

Calendar imports already accept explicit sourced sessions across dates; this workflow is preserved.
Coverage beyond supplied dates must be imported from authoritative data. No holidays were invented.
Universe schema/services are ready, but no index membership was fabricated or ingested.

## FRONTEND CHANGES

Provider configuration/authentication/capability/feed/mapping/update display; backend Sharekhan connection
control; provider selection for new jobs. Debounced server search by symbol/name/ISIN, active filtering and
50-row pagination. Search/page changes clear stale selections. Generic Upstox labels replaced; dedicated
Upstox authentication label retained. No order controls added.

## SECURITY REVIEW

Configured local secret values were checked against tracked/candidate files: no matches. No tracked
.env/.env.local/runtime data. Ignore rules cover credentials/tokens, runtime databases, Redis data, keys,
logs, Python/node/build caches and .local backups. No credentials printed, committed or sent to frontend
source/storage. Login redirect necessarily carries the broker's API identifier according to its protocol;
secure key/access token stay backend-side. Access logging remains disabled in local/Docker launch paths.
No order endpoint is present in the new provider adapter.

## BACKEND TEST RESULTS

97 passed, zero skipped on disposable PostgreSQL. Includes original database tests, identity/provenance,
lease/idempotency concurrency, Sharekhan auth storage/normalization/reconnect, provider routing/status,
Redis recovery, source-independent indicators and instrument API search contracts.
Migration backfill/downgrade/re-upgrade checks also passed, including generic unreconciled marking
for legacy Upstox feed candles so the former indicator safeguard is preserved.

## FRONTEND TEST RESULTS

2 passed, including server search/pagination.

## RUFF RESULT

Passed. git diff --check passed (only ordinary Windows line-ending notices).

## FRONTEND BUILD RESULT

TypeScript and Vite production build passed.

## LIVE ACCEPTANCE TESTS

Local migrated database/API read-only smoke checks passed: provider status reports 9,885 Upstox mappings,
two distinct instrument pages each contain 50 rows, and database readiness is ready.
No credentialed broker acceptance was eligible: environment credentials absent and stored connections=0.

## FAILED TESTS

None remaining. During development, a TypeScript test option and a factory import-order error were fixed.
Provider-independence tests were corrected to compare numerical results while preserving differing
provenance digests. Final full verification passed.

## KNOWN ISSUES

- Credentialed market-data accuracy, availability and broker entitlement remain unverified.
- Sharekhan NC-only scope; REST quote/LTP, current-day reconciliation and full depth unavailable in adapter.
- HDFC SKY awaits accessible official endpoint/payload specifications and account access.
- Calendar coverage remains limited to explicitly imported sessions; index membership is not loaded.
- Sharekhan pacing is per adapter, not a distributed account-wide limiter.
- Extra simultaneous WebSocket connections require entitlement confirmation; default is one.
- Existing Starlette TestClient deprecation warning remains; no unrelated dependency upgrade was made.
- Docker/Timescale execution was not run in this phase; native PostgreSQL migration/tests passed.

## UNVERIFIED ASSUMPTIONS

No real provider payload was used to validate account-specific field availability, retained history depth,
current permissions, feed timestamps, subscription entitlement or corporate-action behavior. Implemented
Sharekhan parsing follows inspected official contracts and must still undergo controlled acceptance.
HDFC availability is not inferred from promotional pages.

## MANUAL ACTION REQUIRED FROM USER

Configure broker credentials locally, register the Sharekhan backend callback, and authenticate through
the backend flow. Start with one liquid NSE equity and a small historical/live request. Verify timestamps,
volume and data completeness before broader subscriptions. Obtain HDFC's account-accessible official
specifications. Import authoritative additional NSE sessions/universe membership when available.
Review the generated backup/report before operational rollout. No remote or commit was created.

## ENVIRONMENT VARIABLES REQUIRED

Existing DATABASE_URL, REDIS_URL, ADMIN_API_KEY and TOKEN_ENCRYPTION_KEY remain.
DEFAULT_MARKET_DATA_PROVIDER=upstox preserves behavior.
PROVIDER_PREFERENCE is a JSON array, default ["upstox","sharekhan","hdfc_sky"].
ENABLE_UPSTOX=true; ENABLE_SHAREKHAN=false; ENABLE_HDFC_SKY=false by default.
For Sharekhan: SHAREKHAN_API_KEY, SHAREKHAN_SECRET_KEY and/or SHAREKHAN_ACCESS_TOKEN as documented.
Existing UPSTOX_* variables remain. No invented HDFC credential variables were added.
FEED_INSTRUMENT_IDS, MAX_SUBSCRIPTIONS, MAX_FEED_CONNECTIONS and FEED_PRIORITIES control live subscriptions.
Selecting a provider for a UI job does not globally rewrite canonical priority.

## COMMANDS FOR USER TO VERIFY LOCALLY

Run from stock-intelligence in PowerShell:

```powershell
..\.tools\python\python.exe -m pytest -q
..\.tools\python\python.exe -m ruff check .
..\.tools\python\python.exe -m pip check
```

With local PostgreSQL running, run the full suite including isolated database tests:

```powershell
..\.tools\python\python.exe scripts/test_disposable_database.py
```

Frontend:

```powershell
Set-Location frontend
npm.cmd test
npm.cmd run build
```

Use Start Local App.cmd to start the local services/UI. It runs Alembic upgrade head. The application
database has already been migrated safely; the stored backup remains under .local/backups. The standalone
feed worker remains opt-in via `python -m market_data.websocket.worker` with correctly loaded local settings.

## RECOMMENDED NEXT PHASE ? DO NOT IMPLEMENT

Controlled provider acceptance, data completeness/calendar validation, and obtaining HDFC technical
contracts/access. Review these results before authorizing scanner or later analytics work. No such work
has been started.
