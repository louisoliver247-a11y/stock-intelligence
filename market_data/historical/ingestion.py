from datetime import datetime, timedelta
from statistics import median

from market_data.calendar import IST, SessionCalendar
from market_data.providers.base import MarketDataProvider
from market_data.providers.errors import ProviderError
from market_data.providers.models import Candle, Instrument, QualityIssue, Timeframe
from market_data.repository import MarketRepository


def validate_batch(
    candles: list[Candle],
    instrument: Instrument,
    timeframe: Timeframe,
    calendar: SessionCalendar,
    start,
    end,
    as_of: datetime,
    volume_baseline_period: int = 20,
    abnormal_volume_multiple: float = 20,
) -> tuple[list[Candle], list[QualityIssue]]:
    issues: list[QualityIssue] = []
    unique: dict[datetime, Candle] = {}
    conflicts: set[datetime] = set()
    for c in candles:
        if c.instrument_id != instrument.instrument_id or c.timeframe != timeframe:
            raise ValueError("MISMATCHED_CANDLE_IDENTITY")
        if not start <= c.timestamp.astimezone(IST).date() <= end or c.timestamp > as_of:
            issues.append(
                QualityIssue(code="OUT_OF_RANGE_CANDLE", instrument_id=c.instrument_id, timestamp=c.timestamp)
            )
            continue
        if c.timestamp in unique:
            conflict = unique[c.timestamp] != c
            issues.append(
                QualityIssue(
                    code="CONFLICTING_DUPLICATE" if conflict else "DUPLICATE_CANDLE",
                    instrument_id=c.instrument_id,
                    timestamp=c.timestamp,
                )
            )
            if conflict:
                conflicts.add(c.timestamp)
        else:
            unique[c.timestamp] = c
        for flag in c.quality_flags:
            issues.append(QualityIssue(code=flag, instrument_id=c.instrument_id, timestamp=c.timestamp))
    for ts in conflicts:
        unique.pop(ts, None)
    trailing_volumes: list[int] = []
    for ts in sorted(unique):
        c = unique[ts]
        if len(trailing_volumes) >= volume_baseline_period:
            baseline = median(trailing_volumes[-volume_baseline_period:])
            if baseline > 0 and c.volume > baseline * abnormal_volume_multiple:
                issues.append(
                    QualityIssue(
                        code="ABNORMAL_VOLUME",
                        instrument_id=c.instrument_id,
                        timestamp=ts,
                        details={
                            "volume": c.volume,
                            "baseline": baseline,
                            "multiple": abnormal_volume_multiple,
                        },
                    )
                )
                unique[ts] = c.model_copy(
                    update={
                        "is_complete": False,
                        "quality_flags": tuple(sorted(set(c.quality_flags) | {"ABNORMAL_VOLUME"})),
                    }
                )
        trailing_volumes.append(c.volume)
    if timeframe == Timeframe.M1:
        day = start
        while day <= end:
            try:
                expected = calendar.expected_minutes(instrument.exchange, day, day)
            except ValueError:
                issues.append(
                    QualityIssue(
                        code="UNKNOWN_SESSION",
                        instrument_id=instrument.instrument_id,
                        details={"date": day.isoformat()},
                    )
                )
                expected = []
            missing = [
                ts.isoformat() for ts in expected if ts + timedelta(minutes=1) <= as_of and ts not in unique
            ]
            if missing:
                issues.append(
                    QualityIssue(
                        code="MISSING_CANDLES",
                        instrument_id=instrument.instrument_id,
                        details={"date": day.isoformat(), "timestamps": missing},
                    )
                )
            day += timedelta(days=1)
    return sorted(unique.values(), key=lambda c: c.timestamp), issues


class HistoricalIngestion:
    def __init__(
        self,
        provider: MarketDataProvider,
        repository: MarketRepository,
        calendar: SessionCalendar,
        chunk_days: int = 28,
        volume_baseline_period: int = 20,
        abnormal_volume_multiple: float = 20,
    ):
        self.provider, self.repository, self.calendar, self.chunk_days = (
            provider,
            repository,
            calendar,
            chunk_days,
        )
        self.volume_baseline_period, self.abnormal_volume_multiple = (
            volume_baseline_period,
            abnormal_volume_multiple,
        )

    async def ingest(self, instrument: Instrument, timeframe: Timeframe, start, end, as_of: datetime) -> dict:
        if start > end or end > as_of.astimezone(IST).date():
            raise ValueError("INVALID_HISTORY_RANGE")
        totals = {"inserted": 0, "corrected": 0, "unchanged": 0, "issues": 0}
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=self.chunk_days - 1))
            try:
                candles = await self.provider.get_historical_candles(
                    instrument, timeframe, cursor, chunk_end, as_of
                )
                valid, issues = validate_batch(
                    candles,
                    instrument,
                    timeframe,
                    self.calendar,
                    cursor,
                    chunk_end,
                    as_of,
                    self.volume_baseline_period,
                    self.abnormal_volume_multiple,
                )
                counts = await self.repository.persist(valid, issues)
                for key in totals:
                    totals[key] += counts[key]
            except ProviderError as exc:
                await self.repository.persist(
                    [], [QualityIssue(code=exc.code, instrument_id=instrument.instrument_id)]
                )
                raise
            cursor = chunk_end + timedelta(days=1)
        return totals
