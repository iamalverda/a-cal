"""Shared PersistentStore singleton for all A-Cal route modules.

Importing this module gives every route module the same store instance,
which means tests only need to patch one location (``a_cal.api.store._store``)
to swap the database for an in-memory instance.

In production, the store uses SQLite (default) or PostgreSQL (when
configured via environment variables). In tests, the ``A_CAL_DB_PATH=:memory:``
env var (set in ``conftest.py``) makes it use an in-memory SQLite database.
"""
from __future__ import annotations

from a_cal.db.store import PersistentStore

# Single shared instance. All route modules import this, never instantiate
# their own PersistentStore().
_store = PersistentStore()


def get_store() -> PersistentStore:
    """Return the shared PersistentStore instance.

    Tests patch ``a_cal.api.store._store`` to swap the database. Route modules
    should either import ``_store`` directly (for module-level use) or call
    this function (for use inside route handlers where a fresh reference is
    clearer).
    """
    return _store
