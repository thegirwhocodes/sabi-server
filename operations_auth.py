"""
Authentication and Authorization for Operations Dashboard
Simple role-based access control for team members.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Header, Depends
from pydantic import BaseModel


class User(BaseModel):
    """Dashboard user."""
    
    id: str
    email: str
    name: str
    role: str
    permissions: list[str]


# Role definitions
ROLES = {
    "admin": [
        "view_dashboard",
        "manage_students",
        "manage_calls",
        "view_finance",
        "manage_finance",
        "manage_team",
        "view_research",
        "manage_communications",
        "manage_settings",
    ],
    "reviewer": [
        "view_dashboard",
        "manage_calls",
        "view_research",
    ],
    "researcher": [
        "view_dashboard",
        "view_research",
        "view_finance",
    ],
    "support": [
        "view_dashboard",
        "view_research",
    ],
}


def hash_password(password: str) -> str:
    """Hash a password with salt."""
    salt = os.getenv("SABI_PASSWORD_SALT", "default-salt")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == hashed


def generate_api_token() -> str:
    """Generate a secure API token."""
    return secrets.token_urlsafe(32)


def get_user_from_token(token: str) -> Optional[User]:
    """Get user from API token."""
    users_db = {
        "sabi-admin-token": User(
            id="user-1",
            email="admin@e4e.org",
            name="Administrator",
            role="admin",
            permissions=ROLES["admin"],
        ),
    }
    
    admin_key = os.getenv("SABI_API_KEY")
    if token == admin_key and admin_key:
        return users_db.get("sabi-admin-token")
    
    return users_db.get(token)


async def get_current_user(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> User:
    """Dependency to get current user from request."""
    token = x_api_key
    
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
        )
    
    return user


def require_permission(permission: str):
    """Dependency to require a specific permission."""
    
    async def check_permission(user: User = Depends(get_current_user)):
        if permission not in user.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required",
            )
        return user
    
    return check_permission


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return user
