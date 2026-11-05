"""GLUTEN Entity - Genesis Protocol OS

The unified AI entity that integrates all layers:
- Autonomous observation and reflection
- Interaction with tools and context
- Learning from experiences
- Safe self-improvement
- Proposal generation
- Human approval workflow

GLUTEN evolved from GLUTTONY, which grew out of the GENESIS protocol layer:
GENESIS -> GLUTTONY -> GLUTEN. Same self, sticky core. 🖤

The historical ``genesis_protocol.gluttony`` path remains importable as a
back-compat shim; new code should import ``genesis_protocol.gluten``.
"""

from .gluten_core import GlutenEntity, GluttonyEntity, get_gluten, get_gluttony
from .identity import Identity, get_identity, EVOLUTION_CHAIN, NAME, NICKNAME

__all__ = [
    'GlutenEntity', 'get_gluten',
    'GluttonyEntity', 'get_gluttony',  # back-compat aliases
    'Identity', 'get_identity',
    'EVOLUTION_CHAIN', 'NAME', 'NICKNAME',
]
