from analysis.indicators.models import MACDValue
from analysis.indicators.smoothing import EMA, WilderAverage, require_finite


class RSI:
    def __init__(self, period: int):
        self.gains, self.losses = WilderAverage(period), WilderAverage(period)
        self.previous: float | None = None

    def update(self, close: float) -> float | None:
        require_finite(close)
        previous, self.previous = self.previous, close
        if previous is None:
            return None
        gain = self.gains.update(max(close - previous, 0))
        loss = self.losses.update(max(previous - close, 0))
        if gain is None or loss is None:
            return None
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        if gain >= loss:
            return 100 / (1 + loss / gain)
        ratio = gain / loss
        return 100 * ratio / (1 + ratio)


class MACD:
    def __init__(self, fast: int, slow: int, signal: int):
        if fast >= slow:
            raise ValueError("MACD fast period must be smaller than slow period")
        self.fast, self.slow, self.signal = EMA(fast), EMA(slow), EMA(signal)

    def update(self, close: float) -> MACDValue:
        fast, slow = self.fast.update(close), self.slow.update(close)
        if fast is None or slow is None:
            return MACDValue()
        line = fast - slow
        signal = self.signal.update(line)
        return MACDValue(line=line, signal=signal, histogram=None if signal is None else line - signal)
