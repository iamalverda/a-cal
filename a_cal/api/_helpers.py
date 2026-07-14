"""Shared helpers for A-Cal route modules."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _fire_plugin_hook(hook_name: str, *args) -> None:
    """Fire a plugin runtime hook, swallowing all errors.

    Plugin hook failures must never crash event operations. This helper
    isolates plugin code from the core data path.

    Args:
        hook_name: Name of the hook to fire (e.g. "on_event_created").
        *args: Positional arguments to pass to the hook.
    """
    try:
        from a_cal.developer.plugin_runtime import get_runtime
        runtime = get_runtime()
        getattr(runtime, hook_name)(*args)
    except Exception as exc:
        logger.debug("plugin hook %s failed: %s", hook_name, exc)
