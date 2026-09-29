from typing import Literal

from pydantic import AwareDatetime

from market_data.providers.models import DomainModel, Timeframe

ALGORITHM_VERSION = "indicators.v1"


class EMAValue(DomainModel):
    period: int
    value: float | None


class MACDValue(DomainModel):
    line: float | None = None
    signal: float | None = None
    histogram: float | None = None


class DirectionalValue(DomainModel):
    plus_di: float | None = None
    minus_di: float | None = None
    adx: float | None = None


class VWAPValue(DomainModel):
    value: float | None = None
    status: Literal["READY", "ZERO_VOLUME", "MISSING_SESSION_OPEN", "NOT_APPLICABLE"]
    method: Literal["OHLCV_HLC3_PROXY"] = "OHLCV_HLC3_PROXY"


class RelativeVolumeValue(DomainModel):
    value: float | None = None
    baseline: float | None = None
    status: Literal["READY", "WARMUP", "ZERO_BASELINE"]
    category: Literal["LOW", "NORMAL", "ELEVATED", "STRONG", "EXCEPTIONAL"] | None = None


class IndicatorSnapshot(DomainModel):
    instrument_id: str
    timeframe: Timeframe
    timestamp: AwareDatetime
    candle_closed_at: AwareDatetime
    known_at: AwareDatetime
    history_start: AwareDatetime
    observations: int
    algorithm_version: str = ALGORITHM_VERSION
    config_fingerprint: str
    input_digest: str
    ema: tuple[EMAValue, ...]
    rsi: float | None
    macd: MACDValue
    atr: float | None
    directional: DirectionalValue
    vwap: VWAPValue
    rvol: RelativeVolumeValue
    unavailable: tuple[str, ...]
