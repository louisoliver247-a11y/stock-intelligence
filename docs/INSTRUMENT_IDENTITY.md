# Canonical instrument identity

IMPLEMENTED and tested with concurrent PostgreSQL syncs.

Instrument IDs remain stable. instrument_provider_mappings has unique (provider, provider_instrument_id)
and (instrument_id, provider), plus symbol/exchange/segment metadata, active and timestamps. Sharekhan
routing keys include exchange (e.g. NC plus scripCode), avoiding cross-exchange numeric collisions.

Existing mappings win. New cash EQ mappings may share a canonical instrument only when exchange,
ISIN and EQ type match exactly and there is exactly one candidate without derivative identity. Symbols
alone never merge instruments. Ambiguous and non-EQ records retain distinct provider-namespaced IDs;
this intentionally favors reviewable duplicates over false merges. Derivative cross-provider automatic
matching is not enabled until all expiry/strike/type/underlying fields can be confirmed.

Nullable trading_symbol, expiry, strike, option_type, lot_size, tick_size and underlying_instrument_id
are added. The legacy nullable provider_key column is retained for compatibility and practical rollback;
generic workers request mapped_instrument instead of using it directly. Old mappings are never silently
deleted when a master omits a security. Raw Sharekhan metadata uses a documented-field allowlist.

Migration 0003 backfills Upstox mappings without replacing IDs or candle foreign keys. Local verification
preserved 9,885 IDs/keys and created every mapping; see MULTIPROVIDER_MIGRATION_RESULT.json.

UniverseService and dated/sourced universe membership tables prepare NIFTY50, NIFTY100, NIFTY200,
NIFTY500, NSE_FNO, CUSTOM and WATCHLIST. No membership is fabricated or inferred from instrument count.
The service uses both membership dates and known_at. Authoritative index ingestion remains future work.
