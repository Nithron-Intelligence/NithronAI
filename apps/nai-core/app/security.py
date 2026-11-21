"""
nAI Core Security Dependencies
FastAPI dependencies for authentication and authorization.

When ``NAI_AUTH_ENABLED=false`` every request runs as a built-in local admin
(``anonymous``), which keeps single-user homelab setups friction-free.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_config
from .models.schemas import User
from .services.auth import AuthService, get_auth_service

bearer_scheme = HTTPBearer(auto_error=False)

ANONYMOUS_USER = User(
    id="anonymous",
    username="anonymous",
    email="anonymous@local",
    is_active=True,
    is_admin=True,
    created_at="1970-01-01T00:00:00Z",
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_config),
) -> User | None:
    """The authenticated user, the anonymous admin when auth is disabled, or None."""
    if not settings.auth_enabled:
        return ANONYMOUS_USER
    if credentials is None:
        return None
    auth: AuthService = get_auth_service()
    return auth.get_current_user(credentials.credentials)


def require_auth(user: User | None = Depends(get_current_user)) -> User:
    """Require an authenticated user (401 otherwise)."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: User = Depends(require_auth)) -> User:
    """Require an admin user (403 otherwise)."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
