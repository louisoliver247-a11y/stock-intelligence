from collections import deque
from datetime import date

import numpy as np

from analysis.indicators.models import RelativeVolumeValue, VWAPValue
from config.indicators import IndicatorConfig


class RelativeVolume:
    def __init__(self, config: IndicatorConfig):
        self.period, self.baseline_method = config.rvol_period, config.rvol_baseline
        self.thresholds = config.rvol_thresholds
        self.volumes: deque[int] = deque(maxlen=self.period)
        self.total = 0

    def update(self, volume: int) -> RelativeVolumeValue:
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise ValueError("volume must be a nonnegative integer")
        if len(self.volumes) < self.period:
            result = RelativeVolumeValue(status="WARMUP")
        else:
            baseline = (self.total / self.period if self.baseline_method == "mean"
                        else float(np.median(np.asarray(self.volumes, dtype=np.float64))))
            if baseline == 0:
                result = RelativeVolumeValue(status="ZERO_BASELINE", baseline=0)
            else:
                value = volume / baseline
                result = RelativeVolumeValue(status="READY", baseline=baseline, value=value,
                                             category=self.category(value))
            self.total -= self.volumes[0]
        self.volumes.append(volume)
        self.total += volume
        return result

    def category(self, value: float) -> str:
        thresholds = self.thresholds
        if value < thresholds.normal:
            return "LOW"
        if value < thresholds.elevated:
            return "NORMAL"
        if value < thresholds.strong:
            return "ELEVATED"
        if value < thresholds.exceptional:
            return "STRONG"
        return "EXCEPTIONAL"


class SessionVWAP:
    """Candle HLC3 proxy, never represented as true trade-tape VWAP."""

    def __init__(self):
        self.day: date | None = None
        self.started_at_open = False
        self.total_volume = 0
        self.value = 0.0

    def update(self, *, day: date, at_session_open: bool, typical_price: float, volume: int,
               intraday: bool) -> VWAPValue:
        if not intraday:
            return VWAPValue(status="NOT_APPLICABLE")
        if day != self.day:
            self.day, self.started_at_open = day, at_session_open
            self.total_volume, self.value = 0, 0.0
        if not self.started_at_open:
            return VWAPValue(status="MISSING_SESSION_OPEN")
        if volume:
            weight = volume / (self.total_volume + volume)
            self.value = (1 - weight) * self.value + weight * typical_price
            self.total_volume += volume
        return VWAPValue(value=self.value, status="READY") if self.total_volume else VWAPValue(status="ZERO_VOLUME")
