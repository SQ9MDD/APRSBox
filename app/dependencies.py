from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.auth import get_user_by_id
from app.models import UserIdentity


def get_current_user(request: Request) -> UserIdentity:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    user = get_user_by_id(int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_roles(*roles: str) -> Callable[[UserIdentity], UserIdentity]:
    def dependency(current_user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency

