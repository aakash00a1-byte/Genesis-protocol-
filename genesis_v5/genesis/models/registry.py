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


def default_registry() -> ModelRegistry:
    reg = ModelRegistry()
    reg.register(
        ModelSpec(
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
            reliability=1.0,
            enabled=True,
        )
    )
    return reg