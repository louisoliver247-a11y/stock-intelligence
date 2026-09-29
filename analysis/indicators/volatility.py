from analysis.indicators.models import DirectionalValue
from analysis.indicators.smoothing import WilderAverage, require_finite


def true_range(high: float, low: float, previous_close: float) -> float:
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


class ATR:
    """First bar establishes previous close; period subsequent true ranges seed ATR."""

    def __init__(self, period: int):
        self.smoother = WilderAverage(period)
        self.previous_close: float | None = None

    def update(self, high: float, low: float, close: float) -> float | None:
        for value in (high, low, close):
            require_finite(value)
        previous, self.previous_close = self.previous_close, close
        return None if previous is None else self.smoother.update(true_range(high, low, previous))


class ADX:
    def __init__(self, period: int):
        self.ranges = WilderAverage(period)
        self.up, self.down, self.strength = (WilderAverage(period) for _ in range(3))
        self.previous: tuple[float, float, float] | None = None

    def update(self, high: float, low: float, close: float) -> DirectionalValue:
        for value in (high, low, close):
            require_finite(value)
        previous, self.previous = self.previous, (high, low, close)
        if previous is None:
            return DirectionalValue()
        previous_high, previous_low, previous_close = previous
        rising, falling = high - previous_high, previous_low - low
        # An equal positive expansion in both directions contributes to neither DM.
        plus = self.up.update(rising if rising > falling and rising > 0 else 0)
        minus = self.down.update(falling if falling > rising and falling > 0 else 0)
        spread = self.ranges.update(true_range(high, low, previous_close))
        if spread is None:
            return DirectionalValue()
        plus_di = 0.0 if spread == 0 else (plus / spread) * 100
        minus_di = 0.0 if spread == 0 else (minus / spread) * 100
        total = plus_di + minus_di
        dx = 0.0 if total == 0 else abs(plus_di - minus_di) / total * 100
        return DirectionalValue(plus_di=plus_di, minus_di=minus_di, adx=self.strength.update(dx))
