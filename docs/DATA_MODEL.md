# Data model

## Implemented foundation

| Table | Purpose / key |
|---|---|
| users | Future ownership anchor; UUID, display name, creation time; no login system yet |
| broker_connections | Single-operator provider connection; encrypted token, updated time |
| instruments | Canonical stable UUID, symbol, exchange, segment, ISIN, provider routing key |
| instrument_metadata | Append-only snapshots for observed master changes |
| exchange_sessions | Explicit per-exchange/date open/close; null boundaries mean holiday |
| candles | Composite instrument/timeframe/start timestamp; numeric OHLC, bigint volume, OI, completion, flags |
| candle_revisions | Previous candle snapshot, revision, known_at and superseded_at |
| data_quality_issues | Persistent quality code, instrument/time, structured evidence, resolution time |
| system_jobs | Durable priority queue, claims, heartbeat lease, attempts, outcome |
| audit_logs | Append-only ingestion, token connection, calendar and correction events |

All temporal columns use timestamptz. Candle timestamps are interval starts;
`known_at` is server receipt/persistence time, not the price timestamp. Decimal
prices serialize as strings to preserve accuracy. Provisional feed candles stay
in Redis; no ticks table or unbounded second-history retention is enabled.

Correction writes hold a transaction-scoped per-candle advisory lock, archive the
old row and update the latest row atomically. Exact repeats are idempotent. A
partial candle cannot overwrite a complete candle. A historical replay must
select revisions whose availability window covers the simulated timestamp.
An as-of revision-query endpoint is deferred to backtesting, so the current
latest-candle endpoint must not be used as a point-in-time backtest source.

## Planned tables, not created in these milestones

* M2–6: indicator_values, market_structure, swings, bos_events, choch_events,
  zones, support_resistance, chart_patterns, candlestick_patterns, scanner_events,
  market_regimes, market_breadth, sector_mapping, sector_metrics.
* M7–8: strategies, strategy_versions, setups, signals, signal_transitions,
  targets. Immutable strategy versions and append-only transitions are required.
* M9: alerts, watchlists, watchlist_items, portfolio, portfolio_positions, trades,
  trade_journal, corporate_events. Feature/setup snapshots must be immutable.
* M10–12: backtests, backtest_runs, backtest_trades, backtest_metrics,
  historical_setup_stats; train/validate/test windows and feature/outcome datasets.

Each owning milestone must introduce typed columns, constraints and indexes with
its implementation. No speculative JSON-only tables are presented as completed
domain functionality.


## Multi-provider phase, 2026-09-27

Migration 0003 adds provider mappings, derivative-ready nullable identity, provider candle observations, canonical provenance, lease tokens/idempotency, quality resolution metadata and dated universe membership. Existing IDs and candle keys remain. See [identity](INSTRUMENT_IDENTITY.md) and [provenance](DATA_PROVENANCE.md).
