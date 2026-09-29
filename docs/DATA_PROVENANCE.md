# Market-data provenance

IMPLEMENTED / PostgreSQL integration tested.

provider_candles is append-only per distinct observed revision, keyed uniquely by provider, canonical
instrument, timeframe, timestamp and revision. Each row contains a normalized candle snapshot (OHLCV/OI,
quality flags, completion, reconciliation and adjustment state), source, provider identifier, received_at
and known_at. Provider corrections are independent from canonical revisions. Identical responses are
idempotent. Unknown origin is rejected for new durable observations.

Existing candles remain the canonical query surface. A complete, reconciled observation from a provider
ranked earlier in PROVIDER_PREFERENCE can replace a lower-ranked canonical observation. Lower priority
observations remain stored without overwriting it. Incomplete observations cannot replace completed data.
Canonical revisions preserve the previous snapshot/known_at and existing as-of query behavior. Preferences
do not trigger retroactive rewrites. Old provider revision history is backfilled during migration. Legacy Upstox feed snapshots are explicitly
marked unreconciled during conversion, preserving their prior indicator rejection.

Sampled live candles have reconciled=false and generic sampled-feed semantics. Indicator validation checks
completion, quality, reconciliation and known_at, not broker names. Identical OHLCV from different providers
produces identical numerical indicators; input audit digests correctly differ with provenance.

Raw payload policy: documented instrument metadata is retained in JSONB. Whole failed provider payloads
and live tick payloads are not durably captured. Failures record sanitized categories/quality issues.
Normalized live quotes carry receipt/knowledge times in Redis with 120-second expiry. Active candles are
also ephemeral; canonical candles and observed revisions live in PostgreSQL. Debug payload retention is
disabled by design; adding sampled sanitized diagnostics later requires an explicit retention policy.

GET /api/data-quality defaults to unresolved issues. POST /api/data-quality/{id}/resolve accepts an
operator note and acknowledged/resolved action, recording metadata and an audit event. Acknowledgement
does not resolve an issue. Neither action edits market prices or clears candle quality flags.
