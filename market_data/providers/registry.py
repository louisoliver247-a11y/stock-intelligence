from collections.abc import Callable

from market_data.providers.base import MarketDataProvider
from market_data.providers.errors import ProviderError


class ProviderRegistry:
    """One composition point; unsupported/disabled adapters cannot be selected."""

    def __init__(self):
        self._factories: dict[str, Callable[[], MarketDataProvider]] = {}

    def register(self, code: str, factory: Callable[[], MarketDataProvider]):
        if code in self._factories:
            raise ValueError("DUPLICATE_PROVIDER")
        self._factories[code] = factory

    def get(self, code: str) -> MarketDataProvider:
        if code not in self._factories:
            raise ProviderError("PROVIDER_DISABLED_OR_UNKNOWN")
        return self._factories[code]()

    def candidates(self, preference: list[str], capability: str) -> list[MarketDataProvider]:
        return [provider for code in dict.fromkeys(preference) if code in self._factories
                if (provider := self.get(code)).capabilities.supports(capability)]
