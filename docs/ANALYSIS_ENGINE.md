# Offline indicator engine

Milestone 2 provides EMA, RSI, MACD, ATR, ADX, session VWAP and relative volume.
Live analysis and trading signals remain disabled.

## Conventions

EMA is seeded with a period-length mean, then uses alpha 2/(period+1).
RSI and ATR use Wilder smoothing of changes and require period+1 candles.
Flat RSI is 50; gains without losses yield 100, losses without gains yield 0.
MACD uses separately seeded EMAs; signal warm-up begins with available MACD values.
ADX uses Wilder smoothing and first becomes available after 2*period candles.
Session VWAP is an OHLCV HLC3 proxy, requires the session opening candle, resets
per session and is unavailable for daily candles. Relative volume uses only the
previous n volumes, with a configurable mean or median, without time-of-day
adjustment. Zero-volume baselines return unavailable rather than infinity.

Configuration in config/indicators.py is immutable. Snapshots contain nulls and
reasons for unavailable outputs, algorithm version, configuration fingerprint,
input digest, history start and known-at time. Incremental state is bounded by
configured periods; batch processing uses the same update implementation.

## Integrity and replay

Use one ordered instrument/timeframe stream per engine and explicit exchange
sessions. Partial/flagged, unreconciled feed, future, mixed, misaligned, gapped
and out-of-order inputs are rejected before state mutation. Repeating the last
identical observation is idempotent. Corrections require ordered replay through
a new engine. Explicit holidays are required when crossing non-trading dates.
MarketRepository.candles_as_of retrieves revisions available at a timezone-aware
system-time cutoff; this is a repository method, not a public endpoint.

## Offline usage

Run from the project directory with dependencies installed:

```sh
python -m analysis.indicators --candles observations.json --sessions sessions.json --as-of 2025-01-02T16:00:00+05:30 --output indicators.json
```

Observations are a JSON array of objects with candle (canonical Candle schema),
known_at (timezone-aware timestamp) and optional revision. Sessions use the
ExchangeSession schema illustrated in README.md. Inputs must be ordered and
belong to one stream. Use --config config.json for IndicatorConfig overrides.
The output file must not already exist. Output identifies offline research and
unverified live integrity. Broker credentials are not required.

Formula tests, an independent NumPy oracle, prefix-invariance checks, input
rejection tests and PostgreSQL correction-cutoff tests validate this milestone.
Real-provider and container acceptance remain outstanding.
