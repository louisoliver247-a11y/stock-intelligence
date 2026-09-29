from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from market_data.calendar import IST
from market_data.providers.models import Candle, DepthLevel, Instrument, Tick, Timeframe


def normalize_instrument(row: dict, exchange: str = 'NC') -> Instrument:
    if exchange != 'NC':
        raise ValueError('UNSUPPORTED_EXCHANGE')
    key = f'{exchange}{int(row["scripCode"])}'
    expiry = datetime.strptime(row['expiry'], '%d/%m/%Y').date() if row.get('expiry') else None
    return Instrument(instrument_id=str(uuid5(NAMESPACE_URL, f'sharekhan:{key}')),
        symbol=row['tradingSymbol'], trading_symbol=row['tradingSymbol'],
        name=row.get('companyName', ''), exchange='NSE', segment='NSE_EQ',
        instrument_type=row['instType'], isin=row.get('isinCode') or None,
        provider='sharekhan', provider_key=key, provider_metadata={**{k: row[k] for k in ('scripCode', 'tradingSymbol', 'tickSize', 'instType',
            'lotSize', 'companyName', 'isinCode', 'expiry', 'strike', 'optionType') if k in row}, 'exchange': exchange},
        expiry=expiry, strike=row.get('strike') if expiry else None,
        option_type=row.get('optionType') if expiry else None,
        lot_size=row.get('lotSize') or None, tick_size=row.get('tickSize') or None)


def normalize_candle(row, instrument, timeframe, calendar, as_of):
    day = datetime.strptime(row['tradeDate'], '%d/%m/%Y').date()
    clock = '00:00:00' if timeframe == Timeframe.D1 else row['tradeTime']
    timestamp = datetime.combine(day, datetime.strptime(clock, '%H:%M:%S').time(), IST)
    if as_of.tzinfo is None:
        raise ValueError('NAIVE_AS_OF')
    if timestamp > as_of:
        raise ValueError('FUTURE_CANDLE')
    flags = []
    complete = False
    try:
        start, end = calendar.bounds(instrument.exchange, timestamp, timeframe)
        if start != timestamp:
            flags.append('MISALIGNED_CANDLE')
        complete = end <= as_of and not flags
    except ValueError as exc:
        flags.append(str(exc))
    return Candle(instrument_id=instrument.instrument_id, symbol=instrument.symbol,
        exchange=instrument.exchange, timeframe=timeframe, timestamp=timestamp,
        open=row['open'], high=row['high'], low=row['low'], close=row['close'], volume=row['qty'],
        is_complete=complete, quality_flags=tuple(flags), source='sharekhan_history', provider='sharekhan',
        provider_instrument_id=instrument.provider_key, adjustment='unadjusted')


def normalize_quote(row, instrument):
    # Streaming dates are month/day/year, unlike historical tradeDate.
    timestamp = datetime.strptime(row.get('ltt') or row['lastUpdatedTime'], '%m/%d/%Y %H:%M:%S').replace(tzinfo=IST)
    depth = ()
    if all(k in row for k in ('bidPrice', 'bidQty', 'offPrice', 'offQty')):
        depth = (DepthLevel(bid_price=row['bidPrice'], bid_quantity=row['bidQty'],
                            ask_price=row['offPrice'], ask_quantity=row['offQty']),)
    return Tick(instrument_id=instrument.instrument_id, timestamp=timestamp, price=row['ltp'],
        previous_close=row.get('close'), cumulative_volume=row.get('qty'), depth=depth,
        source='sharekhan_feed', provider='sharekhan', open_interest=row.get('currentOI'))
