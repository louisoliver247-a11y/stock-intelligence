from datetime import date, datetime

import pytest

from config.settings import Settings, get_settings
from market_data.calendar import IST, SessionCalendar
from market_data.providers.models import Candle, ExchangeSession, Instrument, Timeframe


@pytest.fixture(autouse=True)
def isolate_local_dotenv(monkeypatch):
    """Tests must not consume an operator's local deployment credentials."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def instrument():
    return Instrument(
        instrument_id="test-equity",
        symbol="TEST",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        provider_key="NSE_EQ|TESTISIN", provider="upstox",
    )


@pytest.fixture
def session():
    return ExchangeSession(
        session_date=date(2025, 1, 2),
        opens_at=datetime(2025, 1, 2, 9, 15, tzinfo=IST),
        closes_at=datetime(2025, 1, 2, 15, 30, tzinfo=IST),
        source="synthetic_test",
    )


@pytest.fixture
def calendar(session):
    return SessionCalendar(
        [session, ExchangeSession(session_date=date(2025, 1, 3), source="synthetic_holiday")]
    )


@pytest.fixture
def candle(instrument, session):
    return Candle(
        instrument_id=instrument.instrument_id,
        symbol=instrument.symbol,
        exchange="NSE",
        timeframe=Timeframe.M1,
        timestamp=session.opens_at,
        open=100,
        high=103,
        low=99,
        close=102,
        volume=10,
        is_complete=True,
        source="upstox_history", provider="upstox",
    )
