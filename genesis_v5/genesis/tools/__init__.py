"""Genesis V5 Tool Fabric.

Centralized Tool Gateway: every tool has identity, capability, schema,
permission, risk level, execution policy, timeout, and produces audit events.
No model or agent may call a tool directly — all execution flows through the
Kernel -> Policy Check -> Permission Gate -> Tool Gateway -> Sandbox.
"""
from __future__ import annotations

from .registry import ToolSpec, ToolRegistry, ToolCategory, ToolImpl, ToolContext
from .sandbox import Sandbox, SandboxPolicy
from .gateway import ToolGateway, ToolRequest

__all__ = [
    "ToolSpec",
    "ToolRegistry",
    "ToolCategory",
    "ToolImpl",
    "ToolContext",
    "Sandbox",
    "SandboxPolicy",
    "ToolGateway",
    "ToolRequest",
]