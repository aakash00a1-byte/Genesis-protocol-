"""Back-compat shim for the historical ``genesis_protocol.gluttony_os`` path.

The package now lives at ``genesis_protocol.gluten_os``. This shim re-exports
its public surface so old imports keep working.
"""

import warnings

from genesis_protocol.gluten_os import *  # noqa: F401,F403
from genesis_protocol.gluten_os import __all__ as _gluten_os_all

warnings.warn(
    "genesis_protocol.gluttony_os is deprecated; use genesis_protocol.gluten_os",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = list(_gluten_os_all)
