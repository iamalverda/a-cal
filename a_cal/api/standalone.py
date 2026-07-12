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

from a_cal.api.agent_routes import router as agent_router
from a_cal.api.swarm_routes import router as swarm_router
from a_cal.api.marketplace_routes import router as marketplace_router
from a_cal.api.developer_routes import router as developer_router
from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.api.oauth_routes import router as oauth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="A-Cal Standalone", version="0.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3456", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(swarm_router)
app.include_router(marketplace_router)
app.include_router(developer_router)
app.include_router(standalone_data_router)
app.include_router(oauth_router)


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok", "mode": "standalone"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
