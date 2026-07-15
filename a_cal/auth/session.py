"""Session-based user authentication for A-Cal.

Uses Starlette's SessionMiddleware (signed cookie) for session storage.
A contextvar holds the current user ID so that legacy ``_current_user_id()``
functions across route modules can read it without threading a ``Request``
parameter through every route signature.

Auth flow:
  1. POST /api/a-cal/auth/register → creates user, sets session
  2. POST /api/a-cal/auth/login → validates credentials, sets session
  3. POST /api/a-cal/auth/logout → clears session
  4. GET /api/a-cal/auth/me → returns current user info
  5. AuthMiddleware reads session on every request and sets the contextvar
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contextvar — set by AuthMiddleware, read by _current_user_id() everywhere.
# ---------------------------------------------------------------------------

_current_user: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_user", default="local-dev-user"
)


def get_current_user_id() -> str:
    """Return the current user's ID from the request context.

    Falls back to ``"local-dev-user"`` when no session is active. The auth
    wall (``AuthMiddleware``) blocks unauthenticated access to protected
    routes before they reach a handler, so this fallback only surfaces on
    public paths, in bare test apps without the middleware, and for
    internal/background callers. Handlers that need a guaranteed-authenticated
    user should use the ``require_user_id`` dependency instead.
    """
    return _current_user.get()


def set_current_user_id(user_id: str) -> contextvars.Token[str]:
    """Set the current user ID in the contextvar. Returns a token for reset."""
    return _current_user.set(user_id)


def reset_current_user_id(token: contextvars.Token[str]) -> None:
    """Reset the contextvar to its previous value after a request."""
    _current_user.reset(token)


# ---------------------------------------------------------------------------
# Brute-force lockout — DB-backed failed-attempt tracking with escalating
# windows. Works across restarts and (on PostgreSQL) across workers.
# ---------------------------------------------------------------------------

_LOCKOUT_TIERS = [15, 30, 60, 120, 240, 480, 900, 1800, 3600]


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a stored datetime to tz-aware UTC.

    SQLite stores ``DateTime`` columns as naive strings (timezone is
    stripped), while PostgreSQL preserves tz-aware values. Comparing a
    naive stored value against ``datetime.now(UTC)`` raises, so we attach
    UTC to naive values on read.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _lockout_seconds(fail_count: int) -> int:
    """Return the lockout duration (seconds) for a given failure count.

    No lockout until 5 failures; afterwards each additional 5 failures
    escalates to the next tier (15s, 30s, 60s, ... capped at 1h).
    """
    if fail_count < 5:
        return 0
    tier = (fail_count // 5) - 1
    if tier >= len(_LOCKOUT_TIERS):
        return _LOCKOUT_TIERS[-1]
    return _LOCKOUT_TIERS[tier]


def client_ip(request: Request) -> str:
    """Best-effort client IP for lockout keying.

    Uses the socket peer. When behind a trusted reverse proxy that sets
    ``X-Forwarded-For`` you should terminate/normalize headers at the proxy
    and not rely on this for the primary brute-force control — email-keyed
    lockout (login) carries that load; IP is used for registration spam.
    """
    return request.client.host if request.client else "unknown"


def _get_attempt(key: str) -> AuthAttempt | None:
    """Fetch an AuthAttempt row by key."""
    db = _get_db_session()
    try:
        return db.execute(select(AuthAttempt).where(AuthAttempt.key == key)).scalar_one_or_none()
    finally:
        db.close()


def check_lockout(key: str) -> tuple[bool, int]:
    """Return (is_locked, seconds_remaining) for a lockout key.

    An expired lock is treated as unlocked but the row is left in place so
    the failure counter keeps accumulating across the lockout window.
    """
    row = _get_attempt(key)
    if row is None or row.locked_until is None:
        return False, 0
    now = datetime.now(UTC)
    if _as_utc(row.locked_until) <= now:
        return False, 0
    remaining = int((_as_utc(row.locked_until) - now).total_seconds())
    return True, remaining


def record_failure(key: str) -> int:
    """Record a failed attempt and (re)lock if a tier is crossed.

    Returns the new failure count.
    """
    db = _get_db_session()
    try:
        row = db.execute(select(AuthAttempt).where(AuthAttempt.key == key)).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            row = AuthAttempt(key=key, fail_count=1, last_attempt_at=now)
            db.add(row)
        else:
            row.fail_count = (row.fail_count or 0) + 1
            row.last_attempt_at = now
        window = _lockout_seconds(row.fail_count)
        if window:
            row.locked_until = now + timedelta(seconds=window)
        db.commit()
        return row.fail_count
    finally:
        db.close()


def record_success(key: str) -> None:
    """Clear the failure counter for a key after a successful auth."""
    db = _get_db_session()
    try:
        row = db.execute(select(AuthAttempt).where(AuthAttempt.key == key)).scalar_one_or_none()
        if row is not None:
            row.fail_count = 0
            row.locked_until = None
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Registration rate limit (signup spam) — IP-keyed, reuses AuthAttempt.
# No new dependency: counts registrations per IP within a 1h rolling window
# and refuses further signups once the per-IP cap is exceeded.
# ---------------------------------------------------------------------------

# Signup-spam guard is configurable so operators can tune it for their
# traffic and tests/CI can raise the cap. Values are read lazily (not
# captured at import) so env changes take effect without a module reload;
# a non-positive max disables the cap entirely.
DEFAULT_REGISTER_WINDOW_HOURS = 1
DEFAULT_REGISTER_MAX_PER_IP = 10


def _register_window() -> timedelta:
    """Resolve the rolling registration window from the environment."""
    return timedelta(hours=int(os.environ.get("A_CAL_REGISTER_WINDOW_HOURS", str(DEFAULT_REGISTER_WINDOW_HOURS))))


def _register_max_per_ip() -> int:
    """Resolve the per-IP registration cap from the environment."""
    return int(os.environ.get("A_CAL_REGISTER_MAX_PER_IP", str(DEFAULT_REGISTER_MAX_PER_IP)))


def check_register_rate(ip: str) -> tuple[bool, int]:
    """Return (limited, retry_after_seconds) for an IP's signup rate.

    Counts registrations in the rolling 1h window. Resets the counter when
    the window elapses so a legitimate shared-IP user isn't permanently
    blocked.
    """
    key = f"register:{ip}"
    db = _get_db_session()
    try:
        row = db.execute(select(AuthAttempt).where(AuthAttempt.key == key)).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            return False, 0
        # Roll the window: if the last attempt is older than the window,
        # the count no longer counts against this IP.
        last = _as_utc(row.last_attempt_at)
        window = _register_window()
        if last is not None and (now - last) > window:
            row.fail_count = 0
            row.locked_until = None
            db.commit()
            return False, 0
        if row.fail_count >= _register_max_per_ip():
            # Lock until the oldest attempt in the window ages out.
            retry = int(window.total_seconds())
            if row.last_attempt_at is not None:
                retry = max(1, int((last + window - now).total_seconds()))
            return True, retry
        return False, 0
    finally:
        db.close()


def record_registration(ip: str) -> None:
    """Record one successful registration against an IP's windowed cap."""
    key = f"register:{ip}"
    db = _get_db_session()
    try:
        row = db.execute(select(AuthAttempt).where(AuthAttempt.key == key)).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            row = AuthAttempt(key=key, fail_count=1, last_attempt_at=now)
            db.add(row)
        else:
            if _as_utc(row.last_attempt_at) is not None and (now - _as_utc(row.last_attempt_at)) > _register_window():
                row.fail_count = 0
            row.fail_count = (row.fail_count or 0) + 1
            row.last_attempt_at = now
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Password hashing — simple but secure (PBKDF2-HMAC-SHA256).
# No external dependency needed; uses hashlib from the stdlib.
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 200_000
_SALT_LEN = 16
_HASH_LEN = 32


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256.

    Returns a string in the format ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.

    Args:
        password: The plaintext password to hash.

    Returns:
        The hashed password string.
    """
    salt = secrets.token_bytes(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS, _HASH_LEN
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        password: The plaintext password to check.
        stored: The stored hash string (from ``hash_password``).

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations_int, len(expected)
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# User model lives in a_cal.db.models to avoid duplicate table registration.
from a_cal.db.models import AuthAttempt, User


# ---------------------------------------------------------------------------
# Auth router — register, login, logout, me.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/a-cal/auth", tags=["auth"])

# Session secret — used to sign session cookies AND stateless OAuth state
# tokens. The dev default is intentionally insecure; startup enforcement
# (see ``assert_secure_session_secret``) refuses to boot with it unless the
# operator explicitly opts in via ``A_CAL_ALLOW_INSECURE_DEV_SECRET=1``.
INSECURE_DEV_SECRET = "a-cal-dev-secret-change-in-production-do-not-use-in-prod"


def get_session_secret() -> str:
    """Resolve the session-cookie signing secret from the environment.

    Falls back to the insecure dev default when ``A_CAL_SESSION_SECRET`` is
    unset. Callers that require a strong secret should use
    ``assert_secure_session_secret`` at startup to enforce it.
    """
    return os.environ.get("A_CAL_SESSION_SECRET", INSECURE_DEV_SECRET)


def is_insecure_dev_secret() -> bool:
    """True when the configured secret is the known-insecure dev default."""
    return get_session_secret() == INSECURE_DEV_SECRET


def assert_secure_session_secret() -> None:
    """Refuse to start if the session secret is the insecure dev default.

    This is the enforcement point for the cookie-forgery blocker: a signed
    cookie is only as strong as its secret, and the dev secret is public in
    the source tree. Operators must set ``A_CAL_SESSION_SECRET`` to a random
    value before exposing the server. Tests / local dev opt in with
    ``A_CAL_ALLOW_INSECURE_DEV_SECRET=1``.
    """
    if is_insecure_dev_secret() and os.environ.get("A_CAL_ALLOW_INSECURE_DEV_SECRET") != "1":
        raise RuntimeError(
            "A_CAL_SESSION_SECRET is unset or set to the insecure dev default. "
            "Set it to a random value before starting the server, or set "
            "A_CAL_ALLOW_INSECURE_DEV_SECRET=1 to override (tests/local dev only)."
        )


class RegisterRequest(BaseModel):
    """Payload for user registration."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    """Payload for user login."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User info returned to the frontend."""
    id: str
    email: str
    display_name: str | None = None
    is_active: bool = True


def _get_db_session():
    """Get a SQLAlchemy session for auth operations."""
    from a_cal.db.models import _get_engine_and_session
    _, SessionLocal = _get_engine_and_session()
    return SessionLocal()


@router.post("/register", response_model=UserResponse)
def register(body: RegisterRequest, request: Request) -> UserResponse:
    """Register a new user account.

    Creates the user in the database and sets a session cookie.
    Returns 409 if the email is already registered, 429 if the IP has hit
    the per-IP registration cap (signup-spam guard).
    """
    from sqlalchemy import select

    db = _get_db_session()
    try:
        # Per-IP signup-spam guard.
        ip = client_ip(request)
        limited, retry = check_register_rate(ip)
        if limited:
            raise HTTPException(
                status_code=429,
                detail="Too many registrations from this address. Try again later.",
                headers={"Retry-After": str(retry)},
            )
        existing = db.execute(
            select(User).where(User.email == body.email)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            email=body.email,
            display_name=body.display_name or body.email.split("@")[0],
            password_hash=hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Set session
        request.session["user_id"] = user.id
        request.session["email"] = user.email

        logger.info("registered new user: %s (%s)", user.id, body.email)

        # Count this registration against the IP's windowed cap.
        record_registration(ip)
        return UserResponse(
            id=user.id, email=user.email, display_name=user.display_name,
            is_active=user.is_active,
        )
    finally:
        db.close()


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, request: Request) -> UserResponse:
    """Log in an existing user.

    Validates credentials and sets a session cookie.
    Returns 401 for invalid credentials, 429 when the account is locked
    after repeated failures (brute-force guard).
    """
    from sqlalchemy import select

    db = _get_db_session()
    try:
        # Brute-force lockout keyed by email so credential stuffing one
        # account doesn't burn attempts for everyone.
        lock_key = f"login:{body.email}"
        locked, remaining = check_lockout(lock_key)
        if locked:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(remaining)},
            )
        user = db.execute(
            select(User).where(User.email == body.email)
        ).scalar_one_or_none()
        if not user or not verify_password(body.password, user.password_hash):
            record_failure(lock_key)
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        request.session["user_id"] = user.id
        request.session["email"] = user.email

        record_success(lock_key)
        logger.info("user logged in: %s (%s)", user.id, body.email)
        return UserResponse(
            id=user.id, email=user.email, display_name=user.display_name,
            is_active=user.is_active,
        )
    finally:
        db.close()


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    """Log out the current user by clearing the session."""
    request.session.clear()
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse | None)
def me(request: Request) -> UserResponse | None:
    """Return the current logged-in user, or null if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    from sqlalchemy import select

    db = _get_db_session()
    try:
        user = db.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()
        if not user:
            request.session.clear()
            return None
        return UserResponse(
            id=user.id, email=user.email, display_name=user.display_name,
            is_active=user.is_active,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth wall — public-path allowlist + middleware enforcement.
#
# This is the single chokepoint for "every route must be guarded": any path
# not in ``_PUBLIC_PATHS`` requires an authenticated session, and the
# middleware returns 401 before the app runs. Adding a new public route
# means adding it here — there is no other way to bypass the wall.
# ---------------------------------------------------------------------------

import json as _json
import re as _re

# (methods, path regex). methods == {"*"} matches any HTTP method.
_PUBLIC_PATHS: list[tuple[set[str], _re.Pattern[str]]] = [
    ({"*"}, _re.compile(r"^/health$")),
    ({"*"}, _re.compile(r"^/openapi\.json$")),
    ({"*"}, _re.compile(r"^/docs/?$")),
    ({"*"}, _re.compile(r"^/redoc/?$")),
    # Auth self-service: register, login, logout, session check, demo login.
    ({"GET", "POST"}, _re.compile(r"^/api/a-cal/auth/(register|login|logout|me|demo-login)$")),
    # Public booking page: view event type, fetch slots, create a booking.
    ({"GET", "POST"}, _re.compile(r"^/api/a-cal/booking/[^/]+/?$")),
    ({"GET"}, _re.compile(r"^/api/a-cal/booking/[^/]+/slots$")),
    # OAuth callback is a redirect target from the provider; the session
    # cookie may not be present. The HMAC-signed state is validated in the
    # callback handler itself.
    ({"GET"}, _re.compile(r"^/api/a-cal/providers/[^/]+/oauth/callback$")),
    # Public marketplace browsing only. Installs/rates/flags stay protected.
    ({"GET"}, _re.compile(r"^/api/a-cal/marketplace/items/?$")),
    ({"GET"}, _re.compile(r"^/api/a-cal/marketplace/items/[^/]+$")),
    ({"GET"}, _re.compile(r"^/api/a-cal/marketplace/search$")),
]


def is_public_path(method: str, path: str) -> bool:
    """True if a request may proceed without an authenticated session.

    Args:
        method: HTTP method (e.g. ``"GET"``).
        path: Request path (no query string).

    Returns:
        True if the path is on the public allowlist.
    """
    for methods, pattern in _PUBLIC_PATHS:
        if "*" in methods or method in methods:
            if pattern.match(path):
                return True
    return False


def require_user_id(request: Request) -> str:
    """FastAPI dependency yielding the current user ID or raising 401.

    Use on handlers that want a typed, non-optional user. The middleware
    wall already blocks unauthenticated access to non-public paths, so this
    is a typed convenience rather than the gate.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(user_id)


class AuthMiddleware:
    """Pure-ASGI middleware: enforces the auth wall + sets the user contextvar.

    Implemented as raw ASGI (not Starlette's ``BaseHTTPMiddleware``) on
    purpose: ``BaseHTTPMiddleware`` runs the downstream app in a separate
    task, so a contextvar set inside its ``dispatch`` does NOT propagate to
    the endpoint. A pure-ASGI middleware calls the app in the same task, so
    the contextvar is visible to route handlers and the store's ``_uid()``.

    Must be installed INNER of ``SessionMiddleware`` (added first so it is
    innermost) so that ``scope["session"]`` is already populated when this
    runs.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session = scope.get("session")
        session_user = session.get("user_id") if session else None
        method = scope.get("method", "")
        path = scope.get("path", "")

        # Hard auth wall: reject non-public requests without a session
        # before any route handler runs.
        if not session_user and not is_public_path(method, path):
            body = _json.dumps({"detail": "Not authenticated"}).encode("utf-8")
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ]
            await send({"type": "http.response.start", "status": 401, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        # Anonymous requests can only reach here on public paths (the wall
        # 401s protected paths above); use the dev fallback so public
        # handlers and bare-app tests behave as before the hardening.
        token = set_current_user_id(str(session_user) if session_user else "local-dev-user")
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user_id(token)
