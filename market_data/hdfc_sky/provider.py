from market_data.providers.capabilities import CapabilityStatus, ProviderCapabilities
from market_data.providers.errors import ProviderError


class HDFCSkyProvider:
    code = 'hdfc_sky'
    capabilities = ProviderCapabilities()
    assessment = {name: CapabilityStatus.NOT_DOCUMENTED for name in
                  ('authentication', 'instrument_master', 'historical_candles', 'quotes',
                   'ltp', 'websocket_quotes', 'market_depth', 'open_interest')}

    def __getattr__(self, name):
        raise ProviderError('HDFC_SKY_CONTRACT_AND_ACCESS_UNVERIFIED')
