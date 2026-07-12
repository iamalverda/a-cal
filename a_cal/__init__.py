"""A-Cal — Calendar Data & Sync layer.

Sits on top of atom's agent/intelligence backbone and owns:
  * the sub-account hierarchy (one A-Cal identity, many linked providers),
  * the unified calendar provider abstraction,
  * the universal email gateway (OAuth + IMAP/SMTP),
  * the per-sub-account sync engine (mirror/filter, merge, federation,
    per-sub-agent).

Shares atom's SQLAlchemy database (same ``DATABASE_URL``) so sub-account
records join cleanly with atom's ``users`` / ``tenants`` tables. Importing this
package requires atom's ``backend`` on ``PYTHONPATH`` (as atom itself does).
"""

__version__ = "0.1.0"
