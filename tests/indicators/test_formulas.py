import numpy as np
import pytest

from analysis.indicators.momentum import MACD, RSI
from analysis.indicators.smoothing import EMA
from analysis.indicators.volatility import ADX, ATR
from analysis.indicators.volume import RelativeVolume, SessionVWAP
from config.indicators import IndicatorConfig


def test_ema_sma_seed_and_exact_recurrence():
    ema = EMA(3)
    assert [ema.update(value) for value in [1, 2, 3, 4, 5]] == [None, None, 2, 3, 4]


@pytest.mark.parametrize("prices,expected", [([5] * 8, 50), (list(range(1, 9)), 100),
                                            (list(range(8, 0, -1)), 0)])
def test_rsi_flat_rising_and_falling(prices, expected):
    rsi = RSI(3)
    result = [rsi.update(price) for price in prices]
    assert result[:3] == [None] * 3
    assert result[3:] == pytest.approx([expected] * 5)


def test_rsi_mixed_changes_exact_wilder_seed():
    rsi = RSI(3)
    result = [rsi.update(value) for value in [1, 2, 1, 3, 2]]
    assert result[3] == pytest.approx(75)
    assert result[4] == pytest.approx(600 / 11)


def test_atr_gap_counts_and_first_bar_is_not_a_change():
    atr = ATR(3)
    result = [atr.update(*bar) for bar in [(10, 8, 9), (12, 9, 11), (11, 7, 8), (15, 13, 14), (14, 10, 11)]]
    assert result[:3] == [None] * 3
    assert result[3:] == pytest.approx([14 / 3, 40 / 9])


@pytest.mark.parametrize("direction", [1, -1])
def test_adx_direction_and_strength_are_separate(direction):
    adx = ADX(3)
    result = [adx.update(100 + direction * i + 1, 100 + direction * i - 1, 100 + direction * i)
              for i in range(10)]
    assert all(value.adx is None for value in result[:5])
    assert result[5].adx == pytest.approx(100)
    assert result[5].plus_di == pytest.approx(50 if direction == 1 else 0)
    assert result[5].minus_di == pytest.approx(50 if direction == -1 else 0)


def test_adx_equal_directional_expansion_and_flat_price():
    adx = ADX(2)
    values = [adx.update(10 + i, 10 - i, 10) for i in range(5)]
    assert values[-1].plus_di == 0 and values[-1].minus_di == 0 and values[-1].adx == 0
    flat = ADX(2)
    assert [flat.update(10, 10, 10).adx for _ in range(5)] == [None, None, None, 0, 0]


def test_macd_separate_warmup_for_signal():
    macd = MACD(2, 3, 2)
    values = [macd.update(value) for value in [1, 2, 3, 4, 5]]
    assert values[1].line is None
    assert values[2].line == pytest.approx(0.5) and values[2].signal is None
    assert values[3].signal == pytest.approx(0.5) and values[3].histogram == pytest.approx(0)


@pytest.mark.parametrize("method,baseline", [("mean", 40), ("median", 10)])
def test_relative_volume_uses_prior_window_not_current(method, baseline):
    rvol = RelativeVolume(IndicatorConfig(rvol_period=3, rvol_baseline=method))
    values = [rvol.update(v) for v in [10, 10, 100, 80]]
    assert all(v.status == "WARMUP" for v in values[:3])
    assert values[-1].baseline == baseline and values[-1].value == 80 / baseline
    next_result = rvol.update(40)
    assert next_result.baseline == pytest.approx(np.mean([10, 100, 80]) if method == "mean" else 80)


@pytest.mark.parametrize("volume,category", [(0, "LOW"), (79, "LOW"), (80, "NORMAL"), (149, "NORMAL"),
                                              (150, "ELEVATED"), (200, "STRONG"), (300, "EXCEPTIONAL")])
def test_rvol_categories(volume, category):
    rvol = RelativeVolume(IndicatorConfig(rvol_period=2))
    rvol.update(100)
    rvol.update(100)
    assert rvol.update(volume).category == category


def test_zero_volume_baseline_is_unknown_not_infinity():
    rvol = RelativeVolume(IndicatorConfig(rvol_period=2))
    rvol.update(0)
    rvol.update(0)
    value = rvol.update(100)
    assert value.value is None and value.category is None and value.status == "ZERO_BASELINE"


def test_vwap_weighting_zero_volume_and_reset(session):
    from datetime import timedelta
    vwap = SessionVWAP()
    day = session.session_date
    first = vwap.update(day=day, at_session_open=True, typical_price=10, volume=0, intraday=True)
    assert first.value is None and first.status == "ZERO_VOLUME"
    vwap.update(day=day, at_session_open=False, typical_price=10, volume=100, intraday=True)
    value = vwap.update(day=day, at_session_open=False, typical_price=20, volume=300, intraday=True)
    assert value.value == pytest.approx(17.5) and value.method == "OHLCV_HLC3_PROXY"
    zero = vwap.update(day=day, at_session_open=False, typical_price=50, volume=0, intraday=True)
    assert zero.value == value.value
    reset = vwap.update(day=day + timedelta(days=1), at_session_open=True, typical_price=30,
                        volume=100, intraday=True)
    assert reset.value == 30
