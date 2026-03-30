from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from app.db import execute, fetch_all, fetch_one, log_event, utc_now
from app.models import ROLES, UserIdentity


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived_key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(derived_key).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    algorithm, encoded_salt, encoded_hash = password_hash.split("$", 2)
    if algorithm != "scrypt":
        return False
    salt = base64.b64decode(encoded_salt.encode())
    expected = base64.b64decode(encoded_hash.encode())
    candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate, expected)


def create_user(username: str, password: str, role: str, is_active: bool = True) -> None:
    if role not in ROLES:
        raise ValueError(f"Unsupported role: {role}")
    timestamp = utc_now()
    execute(
        """
        INSERT INTO users(username, password_hash, role, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, hash_password(password), role, int(is_active), timestamp, timestamp),
    )
    log_event("INFO", "auth", f"Created user {username} with role {role}")


def update_user_password(username: str, password: str) -> None:
    execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
        (hash_password(password), utc_now(), username),
    )
    log_event("INFO", "auth", f"Password updated for user {username}")


def set_user_active(user_id: int, is_active: bool) -> None:
    execute(
        "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
        (int(is_active), utc_now(), user_id),
    )


def delete_user(user_id: int) -> None:
    user = fetch_one("SELECT username FROM users WHERE id = ?", (user_id,))
    if not user:
        raise ValueError("User not found.")
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    log_event("INFO", "auth", f"Deleted user {user['username']}")


def update_user(user_id: int, *, role: str, is_active: bool, password: str | None = None) -> None:
    if role not in ROLES:
        raise ValueError(f"Unsupported role: {role}")
    timestamp = utc_now()
    if password:
        execute(
            "UPDATE users SET password_hash = ?, role = ?, is_active = ?, updated_at = ? WHERE id = ?",
            (hash_password(password), role, int(is_active), timestamp, user_id),
        )
    else:
        execute(
            "UPDATE users SET role = ?, is_active = ?, updated_at = ? WHERE id = ?",
            (role, int(is_active), timestamp, user_id),
        )


def list_users() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, username, role, is_active, created_at, updated_at, last_login_at
        FROM users
        ORDER BY username
        """
    )
    return [dict(row) for row in rows]


def get_user_by_username(username: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, username, password_hash, role, is_active
        FROM users
        WHERE username = ?
        """,
        (username,),
    )
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> UserIdentity | None:
    row = fetch_one(
        "SELECT id, username, role, is_active FROM users WHERE id = ?",
        (user_id,),
    )
    if not row:
        return None
    return UserIdentity(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        is_active=bool(row["is_active"]),
    )


def get_user_record_by_id(user_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, username, role, is_active, created_at, updated_at, last_login_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> UserIdentity | None:
    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return UserIdentity(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        is_active=bool(user["is_active"]),
    )


def mark_user_login(user_id: int) -> None:
    execute(
        "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
        (utc_now(), utc_now(), user_id),
    )


def ensure_admin_user(username: str, password: str) -> bool:
    existing = get_user_by_username(username)
    if existing:
        return False
    create_user(username=username, password=password, role="admin", is_active=True)
    return True
