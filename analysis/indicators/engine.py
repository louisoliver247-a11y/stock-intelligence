import hashlib
from collections.abc import Iterable, Iterator
from datetime import datetime

from analysis.indicators.models import EMAValue, IndicatorSnapshot
from analysis.indicators.momentum import MACD, RSI
from analysis.indicators.smoothing import EMA
from analysis.indicators.validation import validate_observation
from analysis.indicators.volatility import ADX, ATR
from analysis.indicators.volume import RelativeVolume, SessionVWAP
from config.indicators import IndicatorConfig
from market_data.calendar import IST, SessionCalendar
from market_data.providers.models import CandleObservation, Timeframe


class IndicatorEngine:
    """One ordered instrument/timeframe stream; no provider, DB, clock or order dependencies."""

    def __init__(self, calendar: SessionCalendar, config: IndicatorConfig | None = None):
        self.calendar = SessionCalendar(list(calendar.sessions.values()))
        self.config = config or IndicatorConfig()
        self.config_fingerprint = self.config.fingerprint
        self.ema = {period: EMA(period) for period in self.config.ema_periods}
        self.rsi = RSI(self.config.rsi_period)
        self.macd = MACD(self.config.macd_fast, self.config.macd_slow, self.config.macd_signal)
        self.atr, self.adx = ATR(self.config.atr_period), ADX(self.config.adx_period)
        self.vwap, self.rvol = SessionVWAP(), RelativeVolume(self.config)
        self.last_observation: CandleObservation | None = None
        self.latest: IndicatorSnapshot | None = None
        self.history_start: datetime | None = None
        self.count = 0
        self.input_digest = ""

    def update(self, observation: CandleObservation, *, as_of: datetime) -> IndicatorSnapshot:
        closed_at = validate_observation(observation, self.calendar, as_of, self.last_observation)
        if observation == self.last_observation:
            return self.latest
        candle = observation.candle
        high, low, close = float(candle.high), float(candle.low), float(candle.close)
        day = candle.timestamp.astimezone(IST).date()
        session = self.calendar.session(candle.exchange, day)
        ema = tuple(EMAValue(period=period, value=state.update(close)) for period, state in self.ema.items())
        rsi, macd = self.rsi.update(close), self.macd.update(close)
        atr, directional = self.atr.update(high, low, close), self.adx.update(high, low, close)
        vwap = self.vwap.update(day=day, at_session_open=candle.timestamp == session.opens_at,
                                typical_price=high / 3 + low / 3 + close / 3,
                                volume=candle.volume, intraday=candle.timeframe != Timeframe.D1)
        rvol = self.rvol.update(candle.volume)
        unavailable = [f"ema_{item.period}:WARMUP" for item in ema if item.value is None]
        for name, value in (("rsi", rsi), ("macd_line", macd.line), ("macd_signal", macd.signal),
                            ("atr", atr), ("adx", directional.adx)):
            if value is None:
                unavailable.append(f"{name}:WARMUP")
        if vwap.value is None:
            unavailable.append(f"vwap:{vwap.status}")
        if rvol.value is None:
            unavailable.append(f"rvol:{rvol.status}")
        self.history_start = self.history_start or candle.timestamp
        self.count += 1
        self.input_digest = hashlib.sha256(
            (self.input_digest + observation.model_dump_json()).encode()
        ).hexdigest()
        self.latest = IndicatorSnapshot(
            instrument_id=candle.instrument_id, timeframe=candle.timeframe, timestamp=candle.timestamp,
            candle_closed_at=closed_at,
            known_at=max(observation.known_at, self.latest.known_at) if self.latest else observation.known_at,
            history_start=self.history_start,
            observations=self.count, config_fingerprint=self.config_fingerprint, input_digest=self.input_digest,
            ema=ema, rsi=rsi, macd=macd, atr=atr, directional=directional, vwap=vwap, rvol=rvol,
            unavailable=tuple(unavailable),
        )
        self.last_observation = observation
        return self.latest


def calculate_series(observations: Iterable[CandleObservation], calendar: SessionCalendar, *,
                     as_of: datetime, config: IndicatorConfig | None = None) -> Iterator[IndicatorSnapshot]:
    """Historical and live processing intentionally share exactly one update implementation."""
    engine = IndicatorEngine(calendar, config)
    for observation in observations:
        yield engine.update(observation, as_of=as_of)
