from market_data.hdfc_sky.provider import HDFCSkyProvider
from market_data.sharekhan.provider import SharekhanProvider
from market_data.upstox.provider import UpstoxProvider


def provider_catalog(settings):
    """Configuration is not evidence of successful authentication or market access."""
    definitions = (
        (UpstoxProvider, 'Upstox', settings.enable_upstox,
         bool(settings.upstox_client_id or settings.upstox_access_token.get_secret_value())),
        (SharekhanProvider, 'Mirae Asset Sharekhan', settings.enable_sharekhan,
         bool(settings.sharekhan_api_key.get_secret_value())),
        (HDFCSkyProvider, 'HDFC SKY', settings.enable_hdfc_sky, False),
    )
    return [dict(provider=adapter.code, display_name=label, enabled=enabled, configured=configured,
                 preferred=adapter.code == settings.default_market_data_provider,
                 authenticated='NOT_VERIFIED', capabilities=adapter.capabilities.model_dump(),
                 assessment=getattr(adapter, 'assessment', {}), rest_status='NOT_VERIFIED',
                 websocket_status='NOT_RUNNING', instrument_mappings=None,
                 last_successful_market_update=None, last_error_category=None)
            for adapter, label, enabled, configured in definitions]
