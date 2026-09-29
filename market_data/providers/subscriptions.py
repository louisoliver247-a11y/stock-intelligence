from dataclasses import dataclass, field

from market_data.providers.models import Instrument


@dataclass
class SubscriptionConnection:
    provider: str
    connection_id: str
    limit: int
    requested: list[Instrument]
    priority: int
    active: set[str] = field(default_factory=set)
    resubscribing: bool = True


def plan_subscriptions(provider: str, requests: list[tuple[int, Instrument]], limit: int,
                       max_connections: int = 1) -> list[SubscriptionConnection]:
    """Stable, bounded pools; lower numeric priority is served first."""
    if limit < 1 or max_connections < 1:
        raise ValueError('INVALID_SUBSCRIPTION_LIMIT')
    unique = {}
    for priority, instrument in sorted(requests, key=lambda pair: (pair[0], pair[1].instrument_id)):
        if instrument.provider != provider or not instrument.provider_key:
            raise ValueError('PROVIDER_MAPPING_REQUIRED')
        unique.setdefault(instrument.instrument_id, (priority, instrument))
    ordered = list(unique.values())
    if len(ordered) > limit * max_connections:
        raise ValueError('SUBSCRIPTION_CAPACITY_EXCEEDED')
    return [SubscriptionConnection(provider, f'{provider}:{start // limit}', limit,
                                   [i for _, i in ordered[start:start + limit]], ordered[start][0])
            for start in range(0, len(ordered), limit)]
