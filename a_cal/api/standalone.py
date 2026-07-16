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
from contextlib import asynccontextmanager

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from a_cal.api.agent_routes import router as agent_router
from a_cal.api.nervous_system_routes import router as nervous_system_router
from a_cal.api.swarm_routes import router as swarm_router
from a_cal.api.marketplace_routes import router as marketplace_router
from a_cal.api.developer_routes import router as developer_router
from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.api.oauth_routes import router as oauth_router
from a_cal.api.analytics_routes import router as analytics_router
from a_cal.api.booking_routes import router as booking_router
from a_cal.api.team_routes import router as team_router
from a_cal.api.graphql_routes import router as graphql_router
from a_cal.auth.session import (
    router as auth_router,
    AuthMiddleware,
    hash_password,
    get_session_secret,
    assert_secure_session_secret,
    is_insecure_dev_secret,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup/shutdown lifespan.

    Enforces a strong session secret at startup: the session cookie and
    OAuth state tokens are signed with it, and the dev default is public
    in the source tree, so booting with it would let anyone forge a cookie.
    Operators must set A_CAL_SESSION_SECRET (or opt in for tests/local dev
    with A_CAL_ALLOW_INSECURE_DEV_SECRET=1).
    """
    assert_secure_session_secret()
    yield


app = FastAPI(title="A-Cal Standalone", version="0.7.0", lifespan=_lifespan)

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
            _seed_demo_sub_accounts(user.id)
        return _DEMO_USER_ID
    finally:
        db.close()


def _seed_demo_sub_accounts(demo_id: str) -> None:
    """Seed default sub-accounts for a fresh demo user.

    The demo experience needs sub-accounts visible in the sidebar so
    E2E tests and manual demo sessions have meaningful data to interact
    with (Main Calendar, Work Google, Personal, Email Inbox).
    """
    from a_cal.db.models import SubAccount, get_session

    import uuid as _uuid
    _uid = _uuid.uuid4().hex[:8]
    defaults = [
        {"id": f"sa-demo-main-{_uid}", "name": "Main Calendar", "kind": "unified",
         "is_main": True, "sync_mode": "mirror_filter", "agent_enabled": True,
         "settings": {"color": "#6366f1", "visible": True}},
        {"id": f"sa-demo-work-{_uid}", "name": "Work Google", "kind": "calendar",
         "is_main": False, "sync_mode": "mirror_filter", "agent_enabled": False,
         "settings": {"color": "#3b82f6", "visible": True}},
        {"id": f"sa-demo-personal-{_uid}", "name": "Personal", "kind": "calendar",
         "is_main": False, "sync_mode": "intelligent_merge", "agent_enabled": True,
         "settings": {"color": "#10b981", "visible": True}},
        {"id": f"sa-demo-email-{_uid}", "name": "Email Inbox", "kind": "email",
         "is_main": False, "sync_mode": "mirror_filter", "agent_enabled": False,
         "settings": {"color": "#f59e0b", "visible": True}},
    ]

    db = get_session()
    try:
        existing = db.query(SubAccount).filter(
            SubAccount.user_id == demo_id
        ).count()
        if existing > 0:
            return
        for d in defaults:
            db.add(SubAccount(user_id=demo_id, **d))
        db.commit()
        logger.info("Seeded %d demo sub-accounts for %s", len(defaults), demo_id)
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

# Session secret — resolved centrally so the same value signs session
# cookies AND stateless OAuth state tokens. Startup enforcement refuses
# to boot with the public dev default unless the operator opts in with
# A_CAL_ALLOW_INSECURE_DEV_SECRET=1 (tests/local dev).
_session_secret = get_session_secret()

# Mark the session cookie Secure (https-only) when the backend is served
# over https so cookies never travel over plain HTTP in production.
_base_url = os.environ.get("A_CAL_BASE_URL", "http://localhost:8000")
_cookie_secure = _base_url.startswith("https://")

if is_insecure_dev_secret():
    logger.warning(
        "A_CAL_SESSION_SECRET is unset — using the built-in dev secret. Session "
        "cookies are forgeable; set A_CAL_SESSION_SECRET to a random value before "
        "exposing this server to real users."
    )

# Middleware stack, outermost -> innermost: CORS -> Session -> Auth -> app.
# Starlette makes the LAST-added middleware the OUTERMOST, so these are added
# in reverse: AuthMiddleware first (innermost), then SessionMiddleware, then
# CORS last (outermost). SessionMiddleware MUST be outer of AuthMiddleware so
# that scope["session"] is populated before AuthMiddleware reads it to set the
# current-user contextvar.
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=_session_secret, https_only=_cookie_secure)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(nervous_system_router)
app.include_router(swarm_router)
app.include_router(marketplace_router)
app.include_router(developer_router)
app.include_router(standalone_data_router)
app.include_router(oauth_router)
app.include_router(analytics_router)
app.include_router(booking_router)
app.include_router(team_router)
app.include_router(graphql_router)
app.include_router(auth_router)



if os.environ.get("A_CAL_ENABLE_DEMO") == "1":
    # Known demo credentials are a backdoor; only mount the route when the
    # operator explicitly enables it (local dev/demo only).
    @app.post("/api/a-cal/auth/demo-login")
    def demo_login(request: Request):
        """Log in as the demo user (demo mode only)."""
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

    # Honour the Dockerfile's A_CAL_PORT/A_CAL_HOST instead of hardcoding
    # port 8000. For real traffic run behind gunicorn/uvicorn workers + a
    # reverse proxy; this is the single-process dev entrypoint.
    _host = os.environ.get("A_CAL_HOST", "0.0.0.0")
    _port = int(os.environ.get("A_CAL_PORT", "8000"))
    uvicorn.run(app, host=_host, port=_port)
