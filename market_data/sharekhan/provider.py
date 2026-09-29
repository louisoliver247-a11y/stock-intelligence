from market_data.calendar import IST
from market_data.providers.capabilities import ProviderCapabilities
from market_data.providers.errors import ProviderError
from market_data.providers.models import Timeframe
from market_data.sharekhan.normalize import normalize_candle, normalize_instrument


class SharekhanProvider:
    code = 'sharekhan'
    subscription_limit = 1000
    capabilities = ProviderCapabilities(instrument_master=True, historical_candles=True,
        websocket_quotes=True, websocket_ticks=True, open_interest=True)

    def __init__(self, http, calendar, feed=None):
        self.http, self.calendar, self.feed = http, calendar, feed

    async def get_instruments(self):
        try:
            rows = await self.http.get('/master/NC')
            result = [normalize_instrument(row) for row in rows]
            if not result or len({i.provider_key for i in result}) != len(result):
                raise ValueError()
            return result
        except (ValueError, KeyError, TypeError):
            raise ProviderError('INVALID_INSTRUMENT_MASTER') from None

    async def get_historical_candles(self, instrument, timeframe, start, end, as_of):
        intervals = {Timeframe.M1: '1minute', Timeframe.D1: 'daily'}
        if timeframe not in intervals or start > end:
            raise ProviderError('UNSUPPORTED_HISTORY_REQUEST')
        key = instrument.provider_key or ''
        if not key.startswith('NC') or not key[2:].isdigit():
            raise ProviderError('INVALID_PROVIDER_MAPPING')
        rows = await self.http.get(f'/historical/NC/{key[2:]}/{intervals[timeframe]}')
        try:
            result = []
            for row in rows:
                from datetime import datetime
                day = datetime.strptime(row['tradeDate'], '%d/%m/%Y').date()
                if start <= day <= end and day <= as_of.astimezone(IST).date():
                    result.append(normalize_candle(row, instrument, timeframe, self.calendar, as_of))
            return sorted(result, key=lambda c: c.timestamp)
        except (ValueError, KeyError, TypeError):
            raise ProviderError('INVALID_CANDLE_RESPONSE') from None

    async def get_intraday_candles(self, instrument, as_of):
        raise ProviderError('CAPABILITY_UNAVAILABLE')

    async def get_quote(self, instrument):
        raise ProviderError('REST_QUOTES_NOT_DOCUMENTED')

    async def get_ltp(self, instrument):
        raise ProviderError('REST_LTP_NOT_DOCUMENTED')

    def subscribe_quotes(self, instruments):
        return self.feed.stream(instruments)

    def subscribe_ticks(self, instruments):
        return self.feed.stream(instruments)

    def subscribe_market_depth(self, instruments):
        raise ProviderError('DEPTH_PAYLOAD_NOT_VERIFIED')

    async def unsubscribe(self, instrument_ids):
        await self.feed.unsubscribe(instrument_ids)
