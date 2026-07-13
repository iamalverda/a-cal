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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from a_cal.api.agent_routes import router as agent_router
from a_cal.api.swarm_routes import router as swarm_router
from a_cal.api.marketplace_routes import router as marketplace_router
from a_cal.api.developer_routes import router as developer_router
from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.api.oauth_routes import router as oauth_router
from a_cal.api.analytics_routes import router as analytics_router
from a_cal.auth.session import (
    router as auth_router,
    AuthMiddleware,
    hash_password,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="A-Cal Standalone", version="0.7.0")

# ---------------------------------------------------------------------------
# Demo user — auto-created in standalone mode so the app works without
# manual registration. In production (with atom), real auth is required.
# ---------------------------------------------------------------------------
_DEMO_EMAIL = "demo@acal.local"
_DEMO_PASSWORD = "demodemo"
_DEMO_USER_ID: str | None = None


def _ensure_demo_user() -> str:
    """Create the demo user if it doesn't exist, return its ID."""
    global _DEMO_USER_ID
    if _DEMO_USER_ID:
        return _DEMO_USER_ID

    from sqlalchemy import select
    from a_cal.db.models import User, get_session

    db = get_session()
    try:
        existing = db.execute(
            select(User).where(User.email == _DEMO_EMAIL)
        ).scalar_one_or_none()
        if existing:
            _DEMO_USER_ID = existing.id
        else:
            user = User(
                email=_DEMO_EMAIL,
                password_hash=hash_password(_DEMO_PASSWORD),
                display_name="Demo User",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            _DEMO_USER_ID = user.id
            logger.info("Created demo user: %s (id=%s)", _DEMO_EMAIL, _DEMO_USER_ID)
        return _DEMO_USER_ID
    finally:
        db.close()


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


@app.post("/api/a-cal/auth/demo-login")
def demo_login(request: Request):
    """Log in as the demo user (standalone mode only)."""
    demo_id = _ensure_demo_user()
    request.session["user_id"] = demo_id

    from sqlalchemy import select
    from a_cal.db.models import User, get_session

    db = get_session()
    try:
        user = db.execute(
            select(User).where(User.id == demo_id)
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=500, detail="Demo user not found")
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_active": user.is_active,
        }
    finally:
        db.close()


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
