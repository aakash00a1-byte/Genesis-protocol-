"""Back-compat shim for the historical ``genesis_protocol.gluttony`` path.

The entity was renamed GLUTTONY -> GLUTEN; the package now lives at
``genesis_protocol.gluten``. This shim keeps old imports working.
"""

import warnings

from genesis_protocol.gluten import (  # noqa: F401
    EVOLUTION_CHAIN,
    GlutenEntity,
    GluttonyEntity,
    Identity,
    NAME,
    NICKNAME,
    get_gluten,
    get_gluttony,
    get_identity,
)

warnings.warn(
    "genesis_protocol.gluttony is deprecated; use genesis_protocol.gluten",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    'GlutenEntity', 'get_gluten',
    'GluttonyEntity', 'get_gluttony',
    'Identity', 'get_identity',
    'EVOLUTION_CHAIN', 'NAME', 'NICKNAME',
]
