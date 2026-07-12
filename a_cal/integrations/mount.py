"""Mount point for atom to include A-Cal routes in its FastAPI app.

When atom is running, it calls ``mount_a_cal(app)`` to add all A-Cal
endpoints (sub-accounts, providers, calendar, agents, email, marketplace,
developer, OAuth) to atom's main FastAPI application. This gives atom
users access to A-Cal's agentic calendar features without running a
separate server.

Usage in atom's main.py::

    from a_cal.integrations.mount import mount_a_cal
    mount_a_cal(app)  # adds /api/a-cal/* routes

In standalone mode (no atom), A-Cal runs its own server via
``a_cal.api.standalone`` and doesn't need this module.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def mount_a_cal(app: Any, prefix: str = "") -> None:
    """Mount all A-Cal routers into a FastAPI application.

    Args:
        app: The FastAPI application instance.
        prefix: Optional URL prefix (e.g., "/v1"). Routes are mounted
            under ``{prefix}/api/a-cal``.
    """
    from a_cal.api.standalone_data import router as standalone_data_router
    from a_cal.api.agent_routes import router as agent_router
    from a_cal.api.swarm_routes import router as swarm_router
    from a_cal.api.marketplace_routes import router as marketplace_router
    from a_cal.api.developer_routes import router as developer_router
    from a_cal.api.oauth_routes import router as oauth_router

    routers = [
        standalone_data_router,
        agent_router,
        swarm_router,
        marketplace_router,
        developer_router,
        oauth_router,
    ]

    for router in routers:
        if prefix:
            # FastAPI doesn't support changing a router prefix after creation,
            # so we mount with a custom path via include_router's prefix arg.
            app.include_router(router, prefix=prefix)
        else:
            app.include_router(router)

    logger.info("A-Cal routes mounted (%d routers, prefix='%s')", len(routers), prefix)
