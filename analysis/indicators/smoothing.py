"""Arithmetic-mean seeded exponential and Wilder smoothing."""

import math


def require_finite(value: float) -> None:
    if not math.isfinite(value):
        raise ValueError("NON_FINITE_INPUT")


class SeededSmoother:
    """O(1) memory: seed with the first period samples, then a convex recurrence."""

    def __init__(self, period: int, alpha: float):
        if isinstance(period, bool) or not isinstance(period, int) or period < 2:
            raise ValueError("period must be an integer >= 2")
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.period, self.alpha = period, alpha
        self.count = 0
        self.seed_mean = 0.0
        self.value: float | None = None

    def update(self, sample: float) -> float | None:
        require_finite(sample)
        self.count += 1
        if self.count <= self.period:
            weight = 1 / self.count
            self.seed_mean = (1 - weight) * self.seed_mean + weight * sample
            if self.count == self.period:
                self.value = self.seed_mean
        else:
            self.value = (1 - self.alpha) * self.value + self.alpha * sample
        return self.value


class EMA(SeededSmoother):
    def __init__(self, period: int):
        super().__init__(period, 2 / (period + 1))


class WilderAverage(SeededSmoother):
    def __init__(self, period: int):
        super().__init__(period, 1 / period)
