"""GLUTTONY Entity - Genesis Protocol v2.0

The unified AI entity that integrates all layers:
- Autonomous observation and reflection
- Interaction with tools and context
- Learning from experiences
- Safe self-improvement
- Proposal generation
- Human approval workflow

GLUTTONY: Endless hunger for knowledge and evolution.
But always with human trust and approval. 🖤
"""

from .gluttony_core import GluttonyEntity, get_gluttony
from .identity import Identity, get_identity

__all__ = ['GluttonyEntity', 'get_gluttony', 'Identity', 'get_identity']
