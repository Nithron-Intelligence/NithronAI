"""
nAI Core Authentication Service
JWT-based authentication with SQLite-backed user management.
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import bcrypt
import jwt

from ..config import Settings, get_settings
from ..db import Database, get_db
from ..models.schemas import ApiKeyCreated, ApiKeyInfo, Token, TokenData, User, UserCreate
from ..utils.logging import get_logger
from ..utils.timeutil import utc_now, utc_now_iso

logger = get_logger(__name__)

API_KEY_PREFIX = "nai_"
LAST_USED_RESOLUTION = timedelta(minutes=5)  # don't write to the DB on every request

# Used to keep login timing similar whether or not the username exists.
_DUMMY_HASH = bcrypt.hashpw(b"nai-dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _row_to_user(row: Any, groups: list[str] | None = None) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        is_active=bool(row["is_active"]),
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
        groups=groups or [],
    )


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _row_to_key(row: Any) -> ApiKeyInfo:
    return ApiKeyInfo(
        id=row["id"],
        name=row["name"],
        prefix=row["prefix"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )


class ApiKeyMixin:
    """API keys: random ``nai_...`` tokens, stored as SHA-256 hashes, acting as their user."""

    db: Database

    def create_api_key(self, user_id: str, name: str) -> ApiKeyCreated:
        key = API_KEY_PREFIX + secrets.token_urlsafe(32)
        key_id = secrets.token_hex(8)
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO api_keys(id, user_id, name, prefix, key_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (key_id, user_id, name.strip(), key[:12], _hash_api_key(key), now),
            )
        logger.info(f"Created API key '{name}' for user {user_id}")
        return ApiKeyCreated(id=key_id, name=name.strip(), prefix=key[:12], created_at=now, key=key)

    def list_api_keys(self, user_id: str) -> list[ApiKeyInfo]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at", (user_id,)
            ).fetchall()
        return [_row_to_key(r) for r in rows]

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
        return cur.rowcount > 0

    def user_id_for_api_key(self, key: str) -> str | None:
        """The owner of an API key (None if unknown). Records when the key was last used."""
        if not key.startswith(API_KEY_PREFIX):
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, last_used_at FROM api_keys WHERE key_hash = ?", (_hash_api_key(key),)
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            last = (
                datetime.fromisoformat(row["last_used_at"].replace("Z", "+00:00"))
                if row["last_used_at"]
                else None
            )
            if last is None or now - last > LAST_USED_RESOLUTION:
                conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (utc_now_iso(), row["id"]))
        return row["user_id"]


class AuthService(ApiKeyMixin):
    """Authentication and user management."""

    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self._secret_key = self._resolve_secret_key()

    def _resolve_secret_key(self) -> str:
        if self.settings.auth_secret_key:
            return self.settings.auth_secret_key

        key_file = os.path.join(self.settings.data_path, ".secret_key")
        if os.path.exists(key_file):
            with open(key_file, encoding="utf-8") as f:
                key = f.read().strip()
            if key:
                return key

        os.makedirs(self.settings.data_path, exist_ok=True)
        key = secrets.token_urlsafe(48)
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key)
        logger.info(f"Generated JWT secret key at {key_file}")
        return key

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def count_users(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def create_user(self, user_data: UserCreate, is_admin: bool = False) -> User | None:
        """Create a user. Returns None if the username or email already exists."""
        user_id = secrets.token_hex(8)
        now = utc_now_iso()
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "INSERT INTO users(id, username, email, password_hash, is_active, is_admin, created_at) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (
                        user_id,
                        user_data.username,
                        user_data.email,
                        hash_password(user_data.password),
                        int(is_admin),
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            logger.warning(f"Username or email already exists: {user_data.username}")
            return None

        logger.info(f"Created user: {user_data.username}{' (admin)' if is_admin else ''}")
        return User(
            id=user_id,
            username=user_data.username,
            email=user_data.email,
            is_active=True,
            is_admin=is_admin,
            created_at=now,
        )

    def authenticate_user(self, username: str, password: str) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if row is None:
            verify_password(password, _DUMMY_HASH)
            logger.warning("Login failed: unknown user")
            return None
        if not verify_password(password, row["password_hash"]):
            logger.warning(f"Login failed: wrong password for {row['username']}")
            return None
        if not row["is_active"]:
            logger.warning(f"Login failed: inactive user {row['username']}")
            return None
        return _row_to_user(row)

    def get_user_by_id(self, user_id: str) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row, self.get_groups(user_id)) if row else None

    def get_groups(self, user_id: str) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT group_name FROM user_groups WHERE user_id = ? ORDER BY group_name", (user_id,)
            ).fetchall()
        return [r["group_name"] for r in rows]

    def set_groups(self, user_id: str, groups: list[str]) -> User | None:
        """Replace a user's groups."""
        if self.get_user_by_id(user_id) is None:
            return None
        with self.db.connect() as conn:
            conn.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO user_groups(user_id, group_name) VALUES (?, ?)",
                [(user_id, g) for g in groups],
            )
        return self.get_user_by_id(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
            group_rows = conn.execute(
                "SELECT user_id, group_name FROM user_groups ORDER BY group_name"
            ).fetchall()
        groups: dict[str, list[str]] = {}
        for g in group_rows:
            groups.setdefault(g["user_id"], []).append(g["group_name"])
        return [_row_to_user(r, groups.get(r["id"])) for r in rows]

    def delete_user(self, user_id: str) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0

    def update_user(
        self,
        user_id: str,
        email: str | None = None,
        password: str | None = None,
        is_active: bool | None = None,
        is_admin: bool | None = None,
    ) -> User | None:
        fields: dict[str, Any] = {}
        if email is not None:
            fields["email"] = email
        if password is not None:
            fields["password_hash"] = hash_password(password)
        if is_active is not None:
            fields["is_active"] = int(is_active)
        if is_admin is not None:
            fields["is_admin"] = int(is_admin)

        if fields:
            assignments = ", ".join(f"{k} = ?" for k in fields)
            with self.db.connect() as conn:
                conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*fields.values(), user_id))
        return self.get_user_by_id(user_id)

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------

    def create_access_token(self, user: User) -> Token:
        now = utc_now()
        payload = {
            "sub": user.id,
            "username": user.username,
            "iat": now,
            "exp": now + timedelta(minutes=self.settings.auth_token_expire_minutes),
            "type": "access",
        }
        token = jwt.encode(payload, self._secret_key, algorithm=self.settings.auth_algorithm)
        return Token(
            access_token=token,
            token_type="bearer",
            expires_in=self.settings.auth_token_expire_minutes * 60,
        )

    def verify_token(self, token: str) -> TokenData | None:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self.settings.auth_algorithm])
        except jwt.PyJWTError as e:
            logger.info(f"Token verification failed: {e}")
            return None
        if payload.get("type") != "access" or not payload.get("sub"):
            return None
        return TokenData(user_id=payload["sub"], username=payload.get("username"), exp=payload.get("exp"))

    def get_current_user(self, token: str) -> User | None:
        """User for a JWT or API key; None if invalid or the user is gone/inactive."""
        if token.startswith(API_KEY_PREFIX):
            user_id = self.user_id_for_api_key(token)
        else:
            token_data = self.verify_token(token)
            user_id = token_data.user_id if token_data else None
        if user_id is None:
            return None
        user = self.get_user_by_id(user_id)
        if user is None or not user.is_active:
            return None
        return user


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    """Get the auth service singleton."""
    return AuthService(get_settings(), get_db())
