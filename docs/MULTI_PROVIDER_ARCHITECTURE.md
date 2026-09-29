# Multi-provider architecture

IMPLEMENTED; tested with mocks and disposable PostgreSQL. No credentialed provider is LIVE VERIFIED.

Application -> capability-aware registry -> provider adapters -> normalized observations ->
HistoricalIngestion -> provider_candles -> configured canonical preference -> candles -> offline indicators.

`MarketDataProvider` remains the shared protocol. `ProviderCapabilities` is immutable and typed.
`providers/factory.py` is the composition point for transport/authentication. Generic workers do not
construct Upstox providers or feeds. Adapters resolve provider routing keys through the mapping table.
Orders are represented as a disabled capability; there are no order methods or routes.

The default remains Upstox to preserve existing deployment behavior. Enable Sharekhan explicitly.
HDFC SKY is a disabled capability descriptor until official endpoint contracts and account access are verified.
A provider database table was not needed: configuration and capabilities live in settings/adapters,
operational status in expiring Redis keys, observations and mappings in PostgreSQL. Credentials never
enter a provider-status table.

Fallback for jobs without an explicit provider tries the configured default followed by
PROVIDER_PREFERENCE, skipping disabled/unsupported providers and unavailable instrument mappings.
Authentication/availability errors permit fallback; malformed payloads fail visibly. An explicitly
selected provider does not silently change. Partial success followed by fallback remains auditable
through provider observations and canonical revisions. Canonical priority is configured separately by
PROVIDER_PREFERENCE; changing configuration does not retrospectively rewrite stored candles.

Live subscription planning supports provider-specific pools, priorities, instrument routing keys,
connection IDs, active instruments and reconnect state. MAX_FEED_CONNECTIONS defaults to one; additional
connections require account entitlement verification. Each connection has independent transport and
resubscription. Sharekhan uses a conservative 1,000 instrument ceiling from the current official FAQ.
Redis caches are bounded by expiry; WebSocket buffers are bounded by max_queue/max_size.

PostgreSQL remains supported without TimescaleDB. No scanner, execution or later analytics was added.
