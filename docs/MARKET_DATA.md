# Market-data contract

## Provider boundary

`MarketDataProvider` exposes normalized instruments, candles, quotes, ticks and
depth. Upstox routing keys and wire structures remain in the adapter. The V1
instrument sync selects NSE cash equity and index records. F&O expiry/rollover
identity, index-universe memberships and corporate-action adjustment are deferred.
Missing instruments are not automatically deactivated: disappearance alone is not
proof of delisting. Master changes preserve metadata snapshots.

## Upstox sources checked during implementation

* [OAuth](https://upstox.com/developer/api-documentation/authentication/)
* [Instrument master](https://upstox.com/developer/api-documentation/instruments/)
* [Historical V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)
* [Intraday V3](https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/)
* [V3 feed](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/)
* [V3 authorization](https://upstox.com/developer/api-documentation/get-market-data-feed-authorize-v3/)
* [Official schema](https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto)

The official schema is vendored unchanged alongside generated Python. Regenerate
with `python -m grpc_tools.protoc -I market_data/upstox --python_out=market_data/upstox market_data/upstox/MarketDataFeed.proto`.
Generated code is excluded from handwritten-code lint rules.

## History and integrity

Historical ingestion fetches canonical 1m/1d in bounded 28-day chunks. Current-day
minute requests use the intraday endpoint. Responses are sorted, validated and
persisted per chunk. Invalid payloads reject the entire chunk and record a quality
issue. An exact duplicate is reported and deduplicated; conflicting duplicate
timestamps are excluded. Missing minute slots are recorded, never filled. Earlier
committed chunks survive a later failed job; rerunning is safe and idempotent.

Valid price: finite and positive; low <= open/close <= high; volume and OI
nonnegative. Missing calendar sessions, holidays, out-of-session/misaligned candles,
future prices and partial candles do not become completed trusted inputs.
Abnormal volume is screened against a strictly prior rolling median (default 20
observations, flag above 20x). Flagged bars remain incomplete pending review.
This conservative screening is not seasonality-adjusted and has no baseline for
the first 20 observations of a fetched chunk; later volume analysis must improve it.

Explicit session rows support holidays and special trading hours. The caller must
provide a verified calendar. Market status is UNKNOWN without today's calendar.
Session imports are audited. They do not automatically repair previously flagged
candles: re-ingest affected ranges after correcting the calendar.

Minute aggregation anchors buckets at session open (normally 09:15 IST), clips the
last bucket at session close and requires every source minute. O/H/L/C = first
open / maximum high / minimum low / last close; volume = sum; OI = final OI.
At `as_of=T`, source minutes ending after T are excluded. All inputs must be
complete for the aggregate to become complete. Supports 3/5/10/15/30m, 1h and 4h.
The enum reserves weekly/monthly/quarterly/half-year/yearly intervals, but those
aggregations are not implemented in this initial foundation.

## Live feed

V3 authorization precedes each connection. Binary protobuf is decoded into canonical
ticks; subscriptions are binary JSON. Reconnects use bounded exponential backoff
and jitter, refresh the stored token and resubscribe. Ping/pong is delegated to the
WebSocket client. Transport and decode failures record disconnect issues.

The feed is sampled market data, not a guaranteed trade tape. **LTQ is never summed
as interval volume.** Consecutive cumulative-volume differences are used only
within the same bucket. Initial snapshots, resets and bucket boundaries are
flagged. Every live candle remains incomplete/unreconciled. One active candle per
instrument is kept in memory and Redis with expiration; raw ticks are not stored.
1/5/15/30s aggregation is available as a provisional utility only.

Reconnect and periodic jobs fetch REST intraday candles to establish durable
history. Redis current state expires during silence. Unknown first/boundary volume
is never represented as validated exchange volume. Last received time is visible;
connection status alone does not certify freshness or absence of missing trades.

## Remaining integrity gates

Real OAuth, entitlements, WebSocket packets and history comparisons require a user
Upstox account and are not certified by mocked tests. Corporate-action adjustment,
seasonality-aware volume validation, cross-day outage reconciliation, automatic exchange-calendar
updates and symbol retirement need additional validation before analysis. Raw
historical prices must not be treated as split/dividend-adjusted series. A live
worker reconciles today's session; queue history explicitly for earlier outages.


## Multi-provider phase, 2026-09-27

Sharekhan adds documented NC instrument master, historical windows and JSON streaming; Upstox is preserved. HDFC SKY remains disabled pending technical contracts/access. See [capabilities](PROVIDER_CAPABILITIES.md), [Sharekhan](SHAREKHAN.md) and [HDFC SKY](HDFC_SKY.md). Existing explicit calendar import accepts additional verified sessions; no holidays or sessions were invented beyond supplied data.
