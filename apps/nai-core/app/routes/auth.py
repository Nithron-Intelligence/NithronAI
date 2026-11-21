"""
nAI Core Auth Routes
Authentication and user management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_config
from ..models.schemas import Token, User, UserCreate, UserLogin
from ..security import get_current_user, require_admin, require_auth
from ..services.auth import AuthService, get_auth_service
from ..utils.logging import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


def _auth_must_be_enabled(settings: Settings) -> None:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=400,
            detail="Authentication is disabled. Set NAI_AUTH_ENABLED=true to enable.",
        )


@router.get("/status")
def auth_status(settings: Settings = Depends(get_config)) -> dict:
    """Public: tells clients whether login is required and whether setup is pending."""
    if not settings.auth_enabled:
        return {"auth_enabled": False, "setup_required": False, "registration_open": False}
    auth = get_auth_service()
    setup_required = auth.count_users() == 0
    return {
        "auth_enabled": True,
        "setup_required": setup_required,
        "registration_open": setup_required or settings.auth_allow_registration,
    }


@router.post("/register", response_model=User)
def register(
    user_data: UserCreate,
    settings: Settings = Depends(get_config),
    current_user: User | None = Depends(get_current_user),
) -> User:
    """
    Register a user.

    - The very first user becomes an admin (initial setup).
    - Afterwards, only admins can create users, unless ``NAI_AUTH_ALLOW_REGISTRATION=true``.
    """
    _auth_must_be_enabled(settings)
    auth = get_auth_service()

    is_first_user = auth.count_users() == 0
    is_admin_request = current_user is not None and current_user.is_admin
    if not (is_first_user or is_admin_request or settings.auth_allow_registration):
        raise HTTPException(status_code=403, detail="Registration is closed. Ask an admin for an account.")

    user = auth.create_user(user_data, is_admin=is_first_user)
    if user is None:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    return user


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, settings: Settings = Depends(get_config)) -> Token:
    """Authenticate and get a JWT access token."""
    _auth_must_be_enabled(settings)
    auth = get_auth_service()
    user = auth.authenticate_user(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return auth.create_access_token(user)


@router.get("/me", response_model=User)
def get_me(user: User = Depends(require_auth)) -> User:
    """Current authenticated user."""
    return user


@router.get("/users", response_model=list[User])
def list_users(
    _admin: User = Depends(require_admin),
    auth: AuthService = Depends(get_auth_service),
) -> list[User]:
    """List all users (admin only)."""
    return auth.list_users()


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Delete a user (admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    if not auth.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": "User deleted"}


@router.post("/users/{user_id}/admin")
def set_admin(
    user_id: str,
    is_admin: bool,
    admin: User = Depends(require_admin),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Grant or revoke admin privileges (admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")
    user = auth.update_user(user_id, is_admin=is_admin)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "user": user}
