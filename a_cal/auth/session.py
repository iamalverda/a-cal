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
from datetime import datetime, timezone, UTC
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
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

    Falls back to ``"local-dev-user"`` when no session is active
    (standalone/dev mode without auth middleware installed).
    """
    return _current_user.get()


def set_current_user_id(user_id: str) -> contextvars.Token[str]:
    """Set the current user ID in the contextvar. Returns a token for reset."""
    return _current_user.set(user_id)


def reset_current_user_id(token: contextvars.Token[str]) -> None:
    """Reset the contextvar to its previous value after a request."""
    _current_user.reset(token)


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
from a_cal.db.models import User


# ---------------------------------------------------------------------------
# Auth router — register, login, logout, me.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/a-cal/auth", tags=["auth"])

# Session secret — generated per-installation, stored in env or DB.
_SESSION_SECRET = os.environ.get(
    "A_CAL_SESSION_SECRET",
    "a-cal-dev-secret-change-in-production-do-not-use-in-prod",
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
    Returns 409 if the email is already registered.
    """
    from sqlalchemy import select

    db = _get_db_session()
    try:
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
    Returns 401 for invalid credentials.
    """
    from sqlalchemy import select

    db = _get_db_session()
    try:
        user = db.execute(
            select(User).where(User.email == body.email)
        ).scalar_one_or_none()
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        request.session["user_id"] = user.id
        request.session["email"] = user.email

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
# Middleware — sets the contextvar from the session on every request.
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware


class AuthMiddleware(BaseHTTPMiddleware):
    """Sets the current user ID contextvar from the session cookie.

    Must be installed AFTER SessionMiddleware so that ``request.session``
    is available.
    """

    async def dispatch(self, request, call_next):
        """Extract user_id from session and set it in the contextvar."""
        user_id = "local-dev-user"
        try:
            session_user = request.session.get("user_id")
            if session_user:
                user_id = str(session_user)
        except Exception:
            pass

        token = set_current_user_id(user_id)
        try:
            response = await call_next(request)
        finally:
            reset_current_user_id(token)
        return response
