"""Genesis V5 — Kernel-orchestrated multi-agent AI system.

Genesis V5 is a zero-trust, policy-controlled orchestration layer for AI
agents. It provides a Kernel that coordinates a full pipeline: memory
retrieval -> task classification -> planning -> model routing -> agent
coordination -> tool gateway (sandboxed) -> reflection -> independent QA ->
memory write -> audit event.

The system is designed to run fully offline with mock providers; real
provider adapters are configuration-driven and remain disabled until their
APIs are verified with real credentials.
"""

__version__ = "5.0.0"
