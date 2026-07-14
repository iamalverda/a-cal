"""Composition stub for standalone A-Cal data routes.

The actual route handlers live in three sub-modules:

- ``a_cal.api.sub_account_routes`` — sub-account, provider, sync, sync-rule CRUD
- ``a_cal.api.calendar_routes`` — unified calendar timeline and event CRUD
- ``a_cal.api.email_routes`` — unified inbox, email actions, advanced email

This file composes them under a single ``APIRouter`` with the ``/api/a-cal``
prefix so that every file that imports ``from a_cal.api.standalone_data
import router`` continues to work without changes.

The sub-routers carry no prefix of their own; the prefix is applied here
via ``include_router``, which causes the sub-router routes to inherit it.
Adding a prefix to a sub-router would double the path (e.g.
``/api/a-cal/api/a-cal/sub-accounts``).
"""

from __future__ import annotations

from fastapi import APIRouter

from a_cal.api.sub_account_routes import router as _sub_router
from a_cal.api.calendar_routes import router as _calendar_router
from a_cal.api.email_routes import router as _email_router

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-data"])
router.include_router(_sub_router)
router.include_router(_calendar_router)
router.include_router(_email_router)
