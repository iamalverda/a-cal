"""Standalone FastAPI server for A-Cal (development without atom).

Mounts all A-Cal routes without requiring atom's database or services.
Includes in-memory data/sync routes (sub-accounts, providers, unified
calendar, sync rules) seeded with demo data, plus agent/settings, swarm,
marketplace, and developer endpoints.

Usage:
    .venv/bin/python -m a_cal.api.standalone
    # → serves at http://localhost:8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from a_cal.api.agent_routes import router as agent_router
from a_cal.api.swarm_routes import router as swarm_router
from a_cal.api.marketplace_routes import router as marketplace_router
from a_cal.api.developer_routes import router as developer_router
from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.api.oauth_routes import router as oauth_router
from a_cal.api.analytics_routes import router as analytics_router
from a_cal.auth.session import router as auth_router, AuthMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="A-Cal Standalone", version="0.7.0")

import os

# Configurable CORS origins for Docker / production deployments.
_default_origins = "http://localhost:3456,http://localhost:3000"
_cors_origins = [
    o.strip()
    for o in os.environ.get("A_CAL_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware (signed cookie) + auth context middleware.
# AuthMiddleware must run after SessionMiddleware so request.session is available.
_session_secret = os.environ.get(
    "A_CAL_SESSION_SECRET",
    "a-cal-dev-secret-change-in-production-do-not-use-in-prod",
)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
app.add_middleware(AuthMiddleware)

app.include_router(agent_router)
app.include_router(swarm_router)
app.include_router(marketplace_router)
app.include_router(developer_router)
app.include_router(standalone_data_router)
app.include_router(oauth_router)
app.include_router(analytics_router)
app.include_router(auth_router)


@app.get("/health")
def health():
    """Health check with database status.

    Returns the server mode and which database backend is in use so users
    can verify their PostgreSQL configuration is active.
    """
    from a_cal.db.models import get_database_url, _engine

    db_type = "sqlite"
    db_url_env = get_database_url()
    if db_url_env:
        db_type = "postgresql" if "postgresql" in db_url_env else "external"
    elif _engine is not None:
        db_type = _engine.dialect.name

    return {
        "status": "ok",
        "mode": "standalone",
        "version": "0.7.0",
        "database": db_type,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
