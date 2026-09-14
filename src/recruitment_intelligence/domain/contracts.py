"""Backward-compatible contract import module.

Consumers may import either ``domain`` or ``domain.contracts``; definitions
remain centralized in :mod:`domain.models`.
"""

from .models import *  # noqa: F401,F403

