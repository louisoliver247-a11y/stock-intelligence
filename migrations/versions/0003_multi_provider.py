"""Add provider identity without replacing canonical IDs or candle keys."""
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""ALTER TABLE instruments
        ALTER COLUMN provider_key DROP NOT NULL,
        ADD COLUMN trading_symbol text, ADD COLUMN expiry date,
        ADD COLUMN strike numeric, ADD COLUMN option_type text,
        ADD COLUMN lot_size integer, ADD COLUMN tick_size numeric,
        ADD COLUMN underlying_instrument_id text REFERENCES instruments(instrument_id)""")
    op.execute("""CREATE TABLE instrument_provider_mappings (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        instrument_id text NOT NULL REFERENCES instruments(instrument_id),
        provider text NOT NULL, provider_instrument_id text NOT NULL,
        provider_symbol text, provider_exchange text, provider_segment text,
        metadata jsonb NOT NULL DEFAULT '{}', active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(provider,provider_instrument_id), UNIQUE(instrument_id,provider))""")
    op.execute("""INSERT INTO instrument_provider_mappings
        (instrument_id,provider,provider_instrument_id,provider_symbol,provider_exchange,provider_segment,active)
        SELECT instrument_id,'upstox',provider_key,symbol,exchange,segment,active FROM instruments
        WHERE provider_key IS NOT NULL""")
    op.execute("""ALTER TABLE candles ADD COLUMN provider text NOT NULL DEFAULT 'unknown',
        ADD COLUMN provider_instrument_id text, ADD COLUMN reconciled boolean NOT NULL DEFAULT true,
        ADD COLUMN adjustment text NOT NULL DEFAULT 'unspecified'""")
    op.execute("""UPDATE candles SET provider='upstox',
        provider_instrument_id=i.provider_key FROM instruments i
        WHERE candles.instrument_id=i.instrument_id AND candles.source LIKE 'upstox%'""")
    # Preserve the former indicator rejection rule when converting legacy feed data.
    op.execute("UPDATE candles SET reconciled=false WHERE source='upstox_feed'")
    op.execute("""UPDATE candle_revisions SET snapshot=snapshot || jsonb_build_object('reconciled',false)
        WHERE snapshot->>'source'='upstox_feed'""")
    op.execute("""CREATE TABLE provider_candles (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        provider text NOT NULL, instrument_id text NOT NULL REFERENCES instruments(instrument_id),
        timeframe text NOT NULL, timestamp timestamptz NOT NULL,
        revision integer NOT NULL, snapshot jsonb NOT NULL,
        source text NOT NULL, provider_instrument_id text,
        received_at timestamptz NOT NULL DEFAULT now(), known_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(provider,instrument_id,timeframe,timestamp,revision))""")
    op.execute("""INSERT INTO provider_candles
        (provider,instrument_id,timeframe,timestamp,revision,snapshot,source,provider_instrument_id,received_at,known_at)
        SELECT provider,instrument_id,timeframe,timestamp,revision,to_jsonb(c),source,
        provider_instrument_id,known_at,known_at FROM candles c""")
    op.execute("""INSERT INTO provider_candles
        (provider,instrument_id,timeframe,timestamp,revision,snapshot,source,provider_instrument_id,received_at,known_at)
        SELECT CASE WHEN r.snapshot->>'source' LIKE 'upstox%' THEN 'upstox' ELSE 'unknown' END,
        r.instrument_id,r.timeframe,r.timestamp,r.revision,r.snapshot,r.snapshot->>'source',
        i.provider_key,r.known_at,r.known_at FROM candle_revisions r
        JOIN instruments i ON i.instrument_id=r.instrument_id""")
    op.execute("""ALTER TABLE system_jobs ADD COLUMN lease_token uuid, ADD COLUMN idempotency_key text""")
    op.execute("""CREATE UNIQUE INDEX jobs_active_idempotency ON system_jobs(idempotency_key)
        WHERE state IN ('QUEUED','RUNNING') AND idempotency_key IS NOT NULL""")
    op.execute("ALTER TABLE data_quality_issues ADD COLUMN resolution jsonb")
    op.execute("""CREATE TABLE instrument_universes (
        code text PRIMARY KEY, authoritative_source text,
        CHECK(code IN ('NIFTY50','NIFTY100','NIFTY200','NIFTY500','NSE_FNO','CUSTOM','WATCHLIST')))""")
    op.execute("""CREATE TABLE universe_memberships (
        universe text REFERENCES instrument_universes(code),
        instrument_id text REFERENCES instruments(instrument_id),
        valid_from date NOT NULL, valid_to date, source text NOT NULL,
        known_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(universe,instrument_id,valid_from), CHECK(valid_to IS NULL OR valid_to>=valid_from))""")


def downgrade():
    # Refuse lossy rollback once new providers are in use. Restore a backup instead.
    op.execute("""DO $$ BEGIN IF EXISTS
        (SELECT 1 FROM instrument_provider_mappings WHERE provider<>'upstox') OR EXISTS
        (SELECT 1 FROM provider_candles WHERE provider NOT IN ('upstox','unknown'))
        THEN RAISE EXCEPTION 'Non-Upstox observations exist; downgrade would lose data'; END IF; END $$""")
    for table in ('universe_memberships', 'instrument_universes', 'provider_candles',
                  'instrument_provider_mappings'):
        op.execute(f'DROP TABLE {table}')
    op.execute('DROP INDEX jobs_active_idempotency')
    op.execute('ALTER TABLE system_jobs DROP COLUMN lease_token, DROP COLUMN idempotency_key')
    op.execute('ALTER TABLE data_quality_issues DROP COLUMN resolution')
    op.execute('ALTER TABLE candles DROP COLUMN provider, DROP COLUMN provider_instrument_id, '
               'DROP COLUMN reconciled, DROP COLUMN adjustment')
    op.execute('ALTER TABLE instruments ALTER COLUMN provider_key SET NOT NULL, '
               'DROP COLUMN trading_symbol, DROP COLUMN expiry, DROP COLUMN strike, '
               'DROP COLUMN option_type, DROP COLUMN lot_size, DROP COLUMN tick_size, '
               'DROP COLUMN underlying_instrument_id')
