from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Timeframe(StrEnum):
    S1 = "1s"
    S5 = "5s"
    S15 = "15s"
    S30 = "30s"
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MONTH = "1mo"
    QUARTER = "3mo"
    HALF = "6mo"
    YEAR = "1y"


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)


class Instrument(DomainModel):
    instrument_id: str
    symbol: str
    exchange: str
    segment: str
    name: str = ""
    isin: str | None = None
    instrument_type: str
    provider_key: str | None = None
    provider: str = "unknown"
    trading_symbol: str | None = None
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: str | None = None
    lot_size: int | None = Field(default=None, gt=0)
    tick_size: Decimal | None = Field(default=None, gt=0)
    underlying_instrument_id: str | None = None
    provider_metadata: dict = Field(default_factory=dict)
    active: bool = True


class Candle(DomainModel):
    instrument_id: str
    symbol: str
    exchange: str
    timeframe: Timeframe
    timestamp: AwareDatetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    is_complete: bool
    source: str
    provider: str = "unknown"
    provider_instrument_id: str | None = None
    reconciled: bool = True
    adjustment: str = "unspecified"
    quality_flags: tuple[str, ...] = ()

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_range(self) -> "Candle":
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC range")
        if self.is_complete and self.quality_flags:
            raise ValueError("flagged candles cannot be complete")
        return self


class DepthLevel(DomainModel):
    bid_price: Decimal = Field(ge=0)
    bid_quantity: int = Field(ge=0)
    ask_price: Decimal = Field(ge=0)
    ask_quantity: int = Field(ge=0)


class CandleObservation(DomainModel):
    """A candle revision and the instant it actually became available to this system."""

    candle: Candle
    known_at: AwareDatetime
    revision: int = Field(default=1, ge=1)

    @field_validator("known_at")
    @classmethod
    def utc_known_at(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class Quote(DomainModel):
    instrument_id: str
    price: Decimal = Field(gt=0)
    timestamp: AwareDatetime
    open_interest: Decimal | None = Field(default=None, ge=0)
    previous_close: Decimal | None = None
    cumulative_volume: int | None = Field(default=None, ge=0)
    depth: tuple[DepthLevel, ...] = ()
    source: str = "unspecified"
    provider: str = "unknown"
    is_snapshot: bool = False
    received_at: AwareDatetime | None = None
    known_at: AwareDatetime | None = None


class Tick(Quote):
    """A sampled quote update, not a guaranteed individual exchange trade."""


class ExchangeSession(DomainModel):
    exchange: str = "NSE"
    session_date: date
    opens_at: AwareDatetime | None = None
    closes_at: AwareDatetime | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_session(self) -> "ExchangeSession":
        if (self.opens_at is None) != (self.closes_at is None):
            raise ValueError("both session boundaries required, or neither for a holiday")
        if self.opens_at and self.closes_at <= self.opens_at:
            raise ValueError("session must have positive duration")
        if self.opens_at:
            from zoneinfo import ZoneInfo

            local_open = self.opens_at.astimezone(ZoneInfo("Asia/Kolkata"))
            local_close = self.closes_at.astimezone(ZoneInfo("Asia/Kolkata"))
            if local_open.date() != self.session_date or local_close.date() != self.session_date:
                raise ValueError("session boundaries must match local session date")
            if local_open.second or local_close.second or local_open.microsecond or local_close.microsecond:
                raise ValueError("session boundaries must align to minutes")
        return self


class QualityIssue(DomainModel):
    code: str
    instrument_id: str | None = None
    timestamp: datetime | None = None
    details: dict = {}
