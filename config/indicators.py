"""Versioned, immutable parameters for the Milestone 2 indicator engine."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Period = Annotated[int, Field(ge=2, le=5000, strict=True)]


class VolumeThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    normal: float = Field(0.8, gt=0)
    elevated: float = Field(1.5, gt=0)
    strong: float = Field(2.0, gt=0)
    exceptional: float = Field(3.0, gt=0)

    @model_validator(mode="after")
    def ordered(self) -> "VolumeThresholds":
        if not self.normal < self.elevated < self.strong < self.exceptional:
            raise ValueError("relative-volume thresholds must be strictly increasing")
        return self


class IndicatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    ema_periods: tuple[Period, ...] = Field(default=(9, 20, 50, 100, 200), min_length=1, max_length=20)
    rsi_period: Period = 14
    atr_period: Period = 14
    adx_period: Period = 14
    macd_fast: Period = 12
    macd_slow: Period = 26
    macd_signal: Period = 9
    rvol_period: Period = 20
    rvol_baseline: Literal["mean", "median"] = "mean"
    rvol_thresholds: VolumeThresholds = Field(default_factory=VolumeThresholds)

    @model_validator(mode="after")
    def consistent(self) -> "IndicatorConfig":
        if tuple(sorted(set(self.ema_periods))) != self.ema_periods:
            raise ValueError("ema_periods must be unique and ascending")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be smaller than macd_slow")
        return self

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
