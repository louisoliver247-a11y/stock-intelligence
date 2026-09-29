from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CapabilityStatus(StrEnum):
    IMPLEMENTED = "SUPPORTED_AND_IMPLEMENTED"
    NOT_IMPLEMENTED = "SUPPORTED_BUT_NOT_IMPLEMENTED"
    UNVERIFIED = "DOCUMENTED_BUT_ACCESS_UNVERIFIED"
    NOT_DOCUMENTED = "NOT_DOCUMENTED"
    UNAVAILABLE = "UNAVAILABLE"


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    instrument_master: bool = False
    historical_candles: bool = False
    intraday_candles: bool = False
    quotes: bool = False
    ltp: bool = False
    websocket_quotes: bool = False
    websocket_ticks: bool = False
    market_depth: bool = False
    open_interest: bool = False
    option_chain: bool = False
    orders: bool = False

    def supports(self, capability: str) -> bool:
        if capability not in type(self).model_fields:
            raise ValueError("UNKNOWN_CAPABILITY")
        return bool(getattr(self, capability))
