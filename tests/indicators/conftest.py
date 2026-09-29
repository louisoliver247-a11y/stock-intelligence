from datetime import timedelta
from decimal import Decimal

import pytest

from config.indicators import IndicatorConfig
from market_data.providers.models import Candle, CandleObservation, Timeframe


@pytest.fixture
def short_config():
    return IndicatorConfig(ema_periods=(2, 3, 5), rsi_period=3, atr_period=3, adx_period=3,
                           macd_fast=2, macd_slow=5, macd_signal=3, rvol_period=3)


@pytest.fixture
def observations(instrument, session):
    def make(prices, volumes=None, start=None):
        start = start or session.opens_at
        volumes = volumes if volumes is not None else [100] * len(prices)
        result = []
        for index, (price, volume) in enumerate(zip(prices, volumes, strict=True)):
            close = Decimal(str(price))
            timestamp = start + timedelta(minutes=index)
            candle = Candle(instrument_id=instrument.instrument_id, symbol=instrument.symbol, exchange="NSE",
                            timeframe=Timeframe.M1, timestamp=timestamp, open=close, high=close + 1,
                            low=max(Decimal("0.1"), close - 1), close=close, volume=int(volume),
                            source="synthetic_test", is_complete=True)
            result.append(CandleObservation(candle=candle, known_at=timestamp + timedelta(minutes=1)))
        return result
    return make
