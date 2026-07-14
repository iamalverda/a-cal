"""A-Cal FastAPI routes — mounts into atom's app or runs standalone.

Exports the data/sync router, the agent/settings router, the swarm negotiation
router, the marketplace router, and the developer router. All share the
``/api/a-cal`` prefix.
"""

from a_cal.api.agent_routes import router as agent_router
from a_cal.api.swarm_routes import router as swarm_router
from a_cal.api.marketplace_routes import router as marketplace_router
from a_cal.api.developer_routes import router as developer_router
from a_cal.api.team_routes import router as team_router
from a_cal.api.graphql_routes import router as graphql_router
from a_cal.api.booking_routes import router as booking_router

from fastapi import APIRouter

router = APIRouter()
router.include_router(agent_router)
router.include_router(swarm_router)
router.include_router(marketplace_router)
router.include_router(developer_router)
router.include_router(team_router)
router.include_router(graphql_router)
router.include_router(booking_router)

__all__ = [
    "router",
    "agent_router",
    "swarm_router",
    "marketplace_router",
    "developer_router",
    "team_router",
    "graphql_router",
    "booking_router",
]
