from dataclasses import dataclass

from market_data.hdfc_sky.provider import HDFCSkyProvider
from market_data.providers.registry import ProviderRegistry
from market_data.sharekhan.http import SharekhanHTTP
from market_data.sharekhan.provider import SharekhanProvider
from market_data.sharekhan.websocket import SharekhanFeed
from market_data.upstox.auth import BrokerAuth
from market_data.upstox.http import UpstoxHTTP
from market_data.upstox.provider import UpstoxProvider
from market_data.websocket.feed import UpstoxFeed


@dataclass
class ProviderContext:
    engine: object
    redis: object


async def build_registry(settings, client, calendar, auth, connected=None, disconnected=None):
    registry = ProviderRegistry()
    if settings.enable_upstox:
        upstox_auth = BrokerAuth(settings, auth.engine, auth.redis)
        # Token lookup is deferred until the selected adapter is actually used.
        http = UpstoxHTTP(client, '', settings.http_retries)
        provider = UpstoxProvider(http, calendar)
        provider.token_supplier = upstox_auth.token
        if connected:
            provider.feed = UpstoxFeed(http, connected, disconnected, settings.max_subscriptions,
                                       token_supplier=upstox_auth.token)
        registry.register('upstox', lambda: provider)
    if settings.enable_sharekhan:
        from market_data.sharekhan.auth import SharekhanAuth
        sk_auth = SharekhanAuth(settings, auth.engine, auth.redis)
        sk_http = SharekhanHTTP(client, settings.sharekhan_api_key.get_secret_value(), '', settings.http_retries)
        sk_provider = SharekhanProvider(sk_http, calendar)
        sk_provider.token_supplier = sk_auth.token
        if connected:
            sk_provider.feed = SharekhanFeed(settings.sharekhan_api_key.get_secret_value(), sk_auth.token,
                connected, disconnected, settings.max_subscriptions)
        registry.register('sharekhan', lambda: sk_provider)
    if settings.enable_hdfc_sky:
        registry.register('hdfc_sky', HDFCSkyProvider)
    return registry


async def authorize(provider):
    token = await provider.token_supplier()
    provider.http.token = token
    return provider
