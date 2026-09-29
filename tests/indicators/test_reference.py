"""Independent vectorized closed-form smoothing oracle, not the streaming recurrence."""

import numpy as np

from analysis.indicators import calculate_series


def seeded_reference(values, period, alpha):
    values = np.asarray(values, dtype=np.float64)
    result = np.full(len(values), np.nan)
    if len(values) < period:
        return result
    seed = np.mean(values[:period])
    result[period - 1] = seed
    decay = 1 - alpha
    for end in range(period, len(values)):
        weights = decay ** np.arange(end - period, -1, -1)
        result[end] = decay ** (end - period + 1) * seed + alpha * np.dot(weights, values[period:end + 1])
    return result


def test_mixed_prices_against_numpy_oracle(observations, calendar, short_config):
    random = np.random.default_rng(1837)
    close = 100 + np.cumsum(random.normal(0, 1, 90))
    volume = random.integers(100, 1000, 90)
    rows = observations(close, volume)
    results = list(calculate_series(rows, calendar, as_of=rows[-1].known_at, config=short_config))
    for period in short_config.ema_periods:
        actual = [next(v.value for v in s.ema if v.period == period) for s in results]
        np.testing.assert_allclose(np.asarray(actual, dtype=float), seeded_reference(close, period, 2/(period+1)),
                                   rtol=1e-12, atol=1e-12, equal_nan=True)
    changes = np.diff(close)
    gains = seeded_reference(np.maximum(changes, 0), 3, 1/3)
    losses = seeded_reference(np.maximum(-changes, 0), 3, 1/3)
    expected_rsi = np.r_[np.nan, 100 * gains / (gains + losses)]
    np.testing.assert_allclose(np.array([s.rsi for s in results], dtype=float), expected_rsi, equal_nan=True)

    high, low = close + 1, close - 1
    tr = np.maximum.reduce([high[1:]-low[1:], np.abs(high[1:]-close[:-1]), np.abs(low[1:]-close[:-1])])
    expected_atr = np.r_[np.nan, seeded_reference(tr, 3, 1/3)]
    np.testing.assert_allclose(np.array([s.atr for s in results], dtype=float), expected_atr, equal_nan=True)

    up, down = np.diff(high), -np.diff(low)
    plus = np.r_[np.nan, seeded_reference(np.where((up > down) & (up > 0), up, 0), 3, 1/3)]
    minus = np.r_[np.nan, seeded_reference(np.where((down > up) & (down > 0), down, 0), 3, 1/3)]
    plus_di, minus_di = 100 * plus / expected_atr, 100 * minus / expected_atr
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    expected_adx = np.r_[np.full(3, np.nan), seeded_reference(dx[3:], 3, 1/3)]
    np.testing.assert_allclose(np.array([s.directional.adx for s in results], dtype=float), expected_adx, equal_nan=True)

    line = seeded_reference(close, 2, 2/3) - seeded_reference(close, 5, 2/6)
    signal = np.r_[np.full(4, np.nan), seeded_reference(line[4:], 3, 2/4)]
    np.testing.assert_allclose(np.array([s.macd.line for s in results], dtype=float), line, atol=1e-12, equal_nan=True)
    np.testing.assert_allclose(np.array([s.macd.signal for s in results], dtype=float), signal, atol=1e-12, equal_nan=True)
    np.testing.assert_allclose(np.array([s.macd.histogram for s in results], dtype=float), line-signal, atol=1e-12, equal_nan=True)
    expected_vwap = np.cumsum(close * volume) / np.cumsum(volume)
    np.testing.assert_allclose([s.vwap.value for s in results], expected_vwap)
    expected_rvol = np.r_[np.full(3, np.nan), [volume[i] / np.mean(volume[i-3:i]) for i in range(3, len(volume))]]
    np.testing.assert_allclose(np.array([s.rvol.value for s in results], dtype=float), expected_rvol, equal_nan=True)
