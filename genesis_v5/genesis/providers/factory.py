"""ProviderFactory registry.

Adapters register under a name; the factory constructs them from config.
Providers whose configuration is incomplete are marked DISABLED and never
fabricate success.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from genesis.config.settings import GenesisConfig

from .base import Provider, ProviderHealth

logger = logging.getLogger(__name__)

ProviderBuilder = Callable[..., Provider]


class ProviderFactory:
    def __init__(self) -> None:
        self._builders: dict[str, ProviderBuilder] = {}
        # Optional kwargs applied when constructing a named provider.
        self._kwargs: dict[str, dict] = {}

    def register(self, name: str, builder: ProviderBuilder, **kwargs: object) -> None:
        self._builders[name] = builder
        self._kwargs[name] = dict(kwargs)

    def names(self) -> list[str]:
        return sorted(self._builders)

    def create(self, name: str, cfg: GenesisConfig | None = None) -> Provider:
        if name not in self._builders:
            raise KeyError(f"unknown provider {name!r}")
        kwargs = dict(self._kwargs.get(name, {}))
        timeout = kwargs.pop("timeout_seconds", None)
        if timeout is None:
            # Do not override the adapter's own default with None; a None
            # timeout reaches with_wall_clock_timeout and raises at call time.
            return self._builders[name](**kwargs)
        return self._builders[name](timeout_seconds=timeout, **kwargs)

    def health(self, name: str, cfg: GenesisConfig | None = None) -> ProviderHealth:
        provider = self.create(name, cfg)
        return provider.health()


_factory: ProviderFactory | None = None


def get_factory() -> ProviderFactory:
    global _factory
    if _factory is None:
        _factory = ProviderFactory()
        from .mock import MockProvider

        _factory.register("mock", MockProvider)
    return _factory


def get_provider(name: str, cfg: GenesisConfig | None = None) -> Provider:
    return get_factory().create(name, cfg)
