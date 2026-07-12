"""Pytest config — make the a_cal package importable without atom installed.

Sets A_CAL_DB_PATH=:memory: so tests use an in-memory SQLite database
instead of the persistent file-based database.
"""
import os
import sys

# Use in-memory database for tests
os.environ["A_CAL_DB_PATH"] = ":memory:"

_pkg_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)
