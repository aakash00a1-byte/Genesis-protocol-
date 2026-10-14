"""ModelRouter: selects the best provider for a task.

Flow: Task -> capability analysis -> available models -> cost/latency/
reliability -> best provider -> controlled fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from genesis.core import ModelResult
from genesis.exceptions import ProviderError, RetryLimitExceeded
from genesis.models.registry import ModelRegistry
from genesis.providers.base import ModelCapability, Provider

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    """The outcome of routing: the chosen model, or the chain of failures."""

    model: str | None = None
    provider: str | None = None
    fallback_used: bool = False
    attempts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        factory: Callable[[str], Provider],
        *,
        default_provider: str = "mock",
        max_fallback_depth: int = 3,
    ) -> None:
        self.registry = registry
        self._factory = factory
        self.default_provider = default_provider
        self.max_fallback_depth = max_fallback_depth

    # ------------------------------------------------------------------
    def route(
        self,
        capability: ModelCapability,
        *,
        offline: bool = True,
    ) -> RouteDecision:
        """Choose the best model for a capability (no completion)."""
        decision = RouteDecision()
        specs = [
            s
            for s in self.registry.find_by_capability(capability)
            if s.enabled and (not offline or self._is_offline(s.provider))
        ]
        specs.sort(key=lambda s: (s.cost_per_1k_tokens, -s.reliability))
        for spec in specs:
            decision.attempts.append(spec.name)
            try:
                provider = self._factory(spec.provider)
                health = provider.health()
            except Exception as exc:  # noqa: BLE001 - normalize at boundary
                decision.errors.append(f"{spec.provider}: {exc}")
                continue
            if not health.ok:
                decision.errors.append(
                    f"{spec.provider}: unhealthy ({health.message})"
                )
                continue
            decision.model = spec.name
            decision.provider = spec.provider
            break
        return decision

    # ------------------------------------------------------------------
    def complete(
        self,
        prompt: str,
        capability: ModelCapability,
        *,
        offline: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ModelResult:
        """Run a completion with controlled, bounded fallback."""
        from genesis.exceptions import (
            ProviderRateLimited,
            ProviderTimeout,
            ProviderUnavailable,
        )

        decision = RouteDecision()
        specs = [
            s
            for s in self.registry.find_by_capability(capability)
            if s.enabled and (not offline or self._is_offline(s.provider))
        ]
        specs.sort(key=lambda s: (s.cost_per_1k_tokens, -s.reliability))

        max_depth = self.max_fallback_depth or 1
        for depth in range(max_depth):
            if depth >= len(specs):
                break
            spec = specs[depth]
            decision.attempts.append(spec.name)
            try:
                provider = self._factory(spec.provider)
                result = provider.complete(
                    prompt,
                    model=spec.name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if depth > 0:
                    result.status = "fallback"
                    decision.fallback_used = True
                decision.model = spec.name
                decision.provider = spec.provider
                return result
            except ProviderRateLimited:
                logger.warning("rate limited on %s", spec.provider)
                decision.errors.append(f"{spec.provider}: rate_limited")
                continue
            except ProviderTimeout:
                logger.warning("timeout on %s", spec.provider)
                decision.errors.append(f"{spec.provider}: timeout")
                continue
            except ProviderUnavailable:
                logger.warning("unavailable on %s", spec.provider)
                decision.errors.append(f"{spec.provider}: unavailable")
                continue
            except ProviderError as exc:
                decision.errors.append(f"{spec.provider}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                decision.errors.append(f"{spec.provider}: {exc}")
                continue

        decision_errors = "; ".join(decision.errors or ["no models available"])
        raise RetryLimitExceeded(
            f"all fallbacks exhausted for {capability.value}: {decision_errors}"
        )

    def _is_offline(self, provider: str) -> bool:
        try:
            return self._factory(provider).offline
        except Exception:  # noqa: BLE001
            return False