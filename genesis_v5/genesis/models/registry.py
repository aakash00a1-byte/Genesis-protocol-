"""Model Registry: maps logical model names to provider + capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field

from genesis.providers.base import ModelCapability


@dataclass
class ModelSpec:
    name: str
    provider: str
    capabilities: list[ModelCapability] = field(default_factory=list)
    max_context_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    reliability: float = 1.0
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "capabilities": [c.value for c in self.capabilities],
            "max_context_tokens": self.max_context_tokens,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "reliability": self.reliability,
            "enabled": self.enabled,
        }


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        self._models[spec.name] = spec

    def get(self, name: str) -> ModelSpec | None:
        return self._models.get(name)

    def all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def enabled(self) -> list[ModelSpec]:
        return [m for m in self._models.values() if m.enabled]

    def find_by_capability(self, capability: ModelCapability) -> list[ModelSpec]:
        return [
            m
            for m in self.enabled()
            if capability in m.capabilities
        ]

    def best_by_capability(
        self, capability: ModelCapability
    ) -> ModelSpec | None:
        candidates = self.find_by_capability(capability)
        if not candidates:
            return None
        # Prefer cheapest, then most reliable.
        return min(
            candidates,
            key=lambda m: (m.cost_per_1k_tokens, -m.reliability),
        )


def _mock_spec() -> ModelSpec:
    return ModelSpec(
        name="mock-1",
        provider="mock",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.CODE,
            ModelCapability.REASONING,
            ModelCapability.PLANNING,
            ModelCapability.RESEARCH,
            ModelCapability.QA,
        ],
        max_context_tokens=8192,
        cost_per_1k_tokens=0.0,
        # The mock is a last-resort offline stub, not a preferred model. A low
        # reliability keeps it behind any configured real provider when the
        # router ranks by (cost, reliability).
        reliability=0.1,
        enabled=True,
    )


# Adapters a live run may route to, in preference order. Each is only added to
# the catalog when it reports healthy (i.e. actually configured).
_LIVE_PROVIDER_ORDER = (
    "openai_compat",
    "claude",
    "gemini",
    "nemotron",
    "local",
    "openhandssdk",
)


def _configured_live_specs(cfg: object) -> list[ModelSpec]:
    """Register a spec for every adapter that is actually configured.

    An adapter that is not configured reports DISABLED via ``health()`` and is
    skipped — so the catalog never advertises a capability that would only
    fail at call time. A configured, healthy provider is placed ahead of the
    mock fallback so an online run routes to the real model first.
    """
    from genesis.providers.factory import get_factory

    factory = get_factory()
    specs: list[ModelSpec] = []
    for name in _LIVE_PROVIDER_ORDER:
        try:
            provider = factory.create(name, cfg)  # type: ignore[arg-type]
            health = provider.health()
        except Exception:  # noqa: BLE001 - a broken adapter must not break boot
            continue
        if not getattr(health, "ok", False):
            continue
        caps = provider.capabilities()
        capabilities = list(caps.capabilities) or [ModelCapability.CHAT]
        specs.append(
            ModelSpec(
                name=f"{name}-default",
                provider=name,
                capabilities=capabilities,
                max_context_tokens=caps.max_context_tokens,
                cost_per_1k_tokens=caps.cost_per_1k_tokens,
                reliability=caps.reliability,
                enabled=True,
            )
        )
    return specs


def default_registry(cfg: object | None = None) -> ModelRegistry:
    """Build the default model catalog.

    Without ``cfg`` the catalog is the offline mock only. With ``cfg`` every
    configured, healthy provider is registered ahead of the mock so that an
    online run routes to the real model, while the mock stays as the offline
    fallback. A provider that is not configured is simply absent — nothing is
    fabricated.
    """
    reg = ModelRegistry()
    if cfg is not None:
        for spec in _configured_live_specs(cfg):
            reg.register(spec)
    reg.register(_mock_spec())
    return reg
