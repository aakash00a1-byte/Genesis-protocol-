"""Runtime identity and capability reporting for GLUTEN.

Reports what the process actually has: the configured providers and their exact
model names, which providers are unavailable, which tools exist and their
permission levels, and the active limits. It never guesses a model and never
prints a secret value - only whether a credential is present.

The prior self-description came from ``identity_router``, which is hardcoded and
says nothing about the model actually answering. This module reads the live
provider chain instead.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Fields that must never be serialised out of a provider status.
_SECRET_FIELDS = {"api_key", "key", "token", "secret", "password", "authorization"}


def _strip_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("<present>" if k.lower() in _SECRET_FIELDS else _strip_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_strip_secrets(v) for v in obj]
    return obj


def _provider_snapshot(chain: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Read a provider chain. Builds the global one if none is given."""
    if chain is None:
        try:
            from genesis_protocol.ai.provider_chain import get_provider_chain
        except Exception:
            return []
        try:
            chain = get_provider_chain()
        except Exception:
            return []
    out: List[Dict[str, Any]] = []
    for name, provider in getattr(chain, "_providers", {}).items():
        if provider is None:
            out.append({"name": name, "available": False, "reason": "not constructed"})
            continue
        try:
            configured = bool(provider.is_configured())
        except Exception:
            configured = False
        entry: Dict[str, Any] = {
            "name": name,
            "available": configured,
            "model": provider.get_default_model() if configured else None,
        }
        if not configured:
            entry["reason"] = "no credential configured"
        out.append(entry)
    return out


def _tools_snapshot() -> List[Dict[str, Any]]:
    try:
        from genesis_protocol.tools.tool_registry import get_tool_registry
        registry = get_tool_registry()
        tools = getattr(registry, "_tools", None)
        if tools is None:
            tools = getattr(registry, "tools", {})
        out = []
        for name, tool in dict(tools).items():
            perm = getattr(tool, "permission", None)
            out.append(
                {
                    "name": name,
                    "category": getattr(tool, "category", "general"),
                    "permission": getattr(perm, "value", str(perm)) if perm else "unknown",
                }
            )
        return out
    except Exception:
        return []


def describe_runtime(chain: Optional[Any] = None) -> Dict[str, Any]:
    """Return an accurate, secret-free description of the running system."""
    providers = _provider_snapshot(chain)
    available = [p for p in providers if p.get("available")]
    unavailable = [p for p in providers if not p.get("available")]

    # This is the first configured provider, i.e. the chain's default. The
    # scoring engine may pick a different provider per query, so the provider
    # that answered a specific request is reported by that request's response.
    default = available[0] if available else None

    return {
        "entity": "GLUTEN",
        "identity_source": "runtime_configuration",
        "default_provider": default["name"] if default else None,
        "default_model": default["model"] if default else None,
        "providers": providers,
        "providers_available": [p["name"] for p in available],
        "providers_unavailable": [
            {"name": p["name"], "reason": p.get("reason", "unavailable")} for p in unavailable
        ],
        "tools": _tools_snapshot(),
        "limits": {
            "code_execution_timeout_s": _limit("sandbox", "DEFAULT_TIMEOUT"),
            "code_execution_memory_mb": _limit("sandbox", "DEFAULT_MEMORY_MB"),
            "code_execution_cpu_s": _limit("sandbox", "DEFAULT_CPU_SECONDS"),
        },
        "owner_configured": _owner_configured(),
        "notes": [
            "owner_configured is True when GLUTEN_OWNER_IDS lists at least one "
            "user id. Restricted tools and code execution are denied to everyone "
            "when it is False (fail closed).",
            "Provider and model names are read from the live configuration, never guessed.",
            "default_provider is the chain default; the scoring engine may choose a "
            "different configured provider per query. The provider that answered a "
            "given request is returned in that request's response.",
            "Unavailable providers are listed with a reason.",
            "Credential values are never included; only availability is reported.",
        ],
    }


def _owner_configured() -> bool:
    """Whether any owner id is configured (no ids are revealed).

    Reads the environment directly instead of the policy singleton: building
    the singleton here would cache it before a later caller sets the owner
    env, leaving a stale, owner-less policy behind.
    """
    try:
        from genesis_protocol.agentic.policy import owner_ids_from_env

        return bool(owner_ids_from_env())
    except Exception:
        return False


def _limit(module: str, name: str):
    try:
        mod = __import__(f"genesis_protocol.agentic.{module}", fromlist=[name])
        return getattr(mod, name)
    except Exception:
        return None
