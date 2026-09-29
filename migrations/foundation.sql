BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE users (
        id uuid PRIMARY KEY, display_name text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE broker_connections (
        provider text PRIMARY KEY, encrypted_token text NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE instruments (
        instrument_id text PRIMARY KEY, symbol text NOT NULL, exchange text NOT NULL,
        segment text NOT NULL, name text NOT NULL, isin text, instrument_type text NOT NULL,
        provider_key text UNIQUE NOT NULL, active boolean NOT NULL DEFAULT true,
        updated_at timestamptz NOT NULL DEFAULT now());

CREATE INDEX instruments_symbol_idx ON instruments (symbol, exchange);

CREATE TABLE instrument_metadata (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        instrument_id text NOT NULL REFERENCES instruments(instrument_id),
        snapshot jsonb NOT NULL, known_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE exchange_sessions (
        exchange text NOT NULL, session_date date NOT NULL, opens_at timestamptz,
        closes_at timestamptz, source text NOT NULL, PRIMARY KEY(exchange, session_date),
        CHECK ((opens_at IS NULL AND closes_at IS NULL) OR
               (opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)));

CREATE TABLE candles (
        instrument_id text NOT NULL REFERENCES instruments(instrument_id),
        timeframe text NOT NULL, timestamp timestamptz NOT NULL,
        symbol text NOT NULL, exchange text NOT NULL,
        open numeric(24,8) NOT NULL CHECK(open > 0), high numeric(24,8) NOT NULL,
        low numeric(24,8) NOT NULL CHECK(low > 0), close numeric(24,8) NOT NULL CHECK(close > 0),
        volume bigint NOT NULL CHECK(volume >= 0), open_interest numeric(24,8),
        is_complete boolean NOT NULL, source text NOT NULL, quality_flags jsonb NOT NULL DEFAULT '[]',
        known_at timestamptz NOT NULL DEFAULT now(), revision integer NOT NULL DEFAULT 1,
        PRIMARY KEY(instrument_id, timeframe, timestamp),
        CHECK(high >= greatest(open, close, low) AND low <= least(open, close)),
        CHECK(open_interest IS NULL OR open_interest >= 0),
        CHECK(NOT is_complete OR quality_flags = '[]'::jsonb));

CREATE INDEX candles_time_idx ON candles (timeframe, timestamp DESC);

CREATE TABLE candle_revisions (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        instrument_id text NOT NULL, timeframe text NOT NULL, timestamp timestamptz NOT NULL,
        revision integer NOT NULL, snapshot jsonb NOT NULL,
        known_at timestamptz NOT NULL, superseded_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(instrument_id, timeframe, timestamp, revision));

CREATE TABLE data_quality_issues (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, instrument_id text,
        timestamp timestamptz, code text NOT NULL, details jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz);

CREATE INDEX quality_open_idx ON data_quality_issues (created_at DESC) WHERE resolved_at IS NULL;

CREATE TABLE system_jobs (
        id uuid PRIMARY KEY, kind text NOT NULL, payload jsonb NOT NULL,
        priority integer NOT NULL CHECK(priority BETWEEN 1 AND 3),
        state text NOT NULL DEFAULT 'QUEUED' CHECK(state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
        attempts integer NOT NULL DEFAULT 0, result jsonb, error_code text,
        created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz);

CREATE INDEX jobs_queue_idx ON system_jobs (priority, created_at) WHERE state = 'QUEUED';

CREATE TABLE audit_logs (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, event text NOT NULL,
        entity_id text, details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now());

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        PERFORM create_hypertable('candles', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
      END IF;
    END $$;

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;

